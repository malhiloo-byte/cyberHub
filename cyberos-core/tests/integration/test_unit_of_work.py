import sqlite3
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from cyberos.config.models import DatabaseSettings
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork, TransactionState


@dataclass(frozen=True, slots=True)
class RepositoryTestRecord:
    entity_id: UUID
    value: str


class SQLiteTestRecordRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def get(self, entity_id: UUID) -> RepositoryTestRecord | None:
        row = self.connection.execute(
            "SELECT entity_id, value FROM test_records WHERE entity_id = ?", (str(entity_id),)
        ).fetchone()
        return RepositoryTestRecord(UUID(str(row[0])), str(row[1])) if row else None

    def add(self, record: RepositoryTestRecord) -> RepositoryTestRecord:
        self.connection.execute(
            "INSERT INTO test_records (entity_id, value) VALUES (?, ?)",
            (str(record.entity_id), record.value),
        )
        return record


def factory_for(tmp_path: Path) -> SQLiteConnectionFactory:
    return SQLiteConnectionFactory(DatabaseSettings(path=tmp_path / "cyberos.sqlite3"))


def initialize_test_table(factory: SQLiteConnectionFactory) -> None:
    with factory.connect() as managed:
        managed.raw.execute(
            "CREATE TABLE test_records (entity_id TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )


def test_commit_persists_repository_data(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    initialize_test_table(factory)
    record = RepositoryTestRecord(uuid4(), "committed")
    with SQLiteUnitOfWork(factory) as uow:
        repository = SQLiteTestRecordRepository(uow.raw)
        repository.add(record)
        uow.commit()
        assert uow.state is TransactionState.COMMITTED
    with SQLiteUnitOfWork(factory) as reader:
        assert SQLiteTestRecordRepository(reader.raw).get(record.entity_id) == record
        reader.rollback()


def test_exception_rolls_back_repository_data(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    initialize_test_table(factory)
    record = RepositoryTestRecord(uuid4(), "rolled-back")
    with pytest.raises(RuntimeError):
        with SQLiteUnitOfWork(factory) as uow:
            SQLiteTestRecordRepository(uow.raw).add(record)
            raise RuntimeError("force rollback")
    with SQLiteUnitOfWork(factory) as reader:
        assert SQLiteTestRecordRepository(reader.raw).get(record.entity_id) is None
        reader.rollback()


def test_second_reader_cannot_see_uncommitted_data(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    initialize_test_table(factory)
    record = RepositoryTestRecord(uuid4(), "isolated")
    writer = SQLiteUnitOfWork(factory)
    reader = SQLiteUnitOfWork(factory)
    with writer, reader:
        SQLiteTestRecordRepository(writer.raw).add(record)
        reader_repository = SQLiteTestRecordRepository(reader.raw)
        assert reader_repository.get(record.entity_id) is None
        writer.commit()
        assert reader_repository.get(record.entity_id) is None
        reader.rollback()
    with SQLiteUnitOfWork(factory) as verifier:
        assert SQLiteTestRecordRepository(verifier.raw).get(record.entity_id) == record
        verifier.rollback()


def test_invalid_lifecycle_operations_are_typed(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    unit = SQLiteUnitOfWork(factory)
    with pytest.raises(CyberOSError) as before_enter:
        unit.commit()
    assert before_enter.value.code == ErrorCode.TRANSACTION_NOT_ACTIVE
    with unit:
        unit.commit()
        with pytest.raises(CyberOSError) as after_commit:
            unit.rollback()
        assert after_commit.value.code == ErrorCode.TRANSACTION_ALREADY_COMMITTED


def test_manual_rollback_is_idempotently_closed_by_context(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    with SQLiteUnitOfWork(factory) as unit:
        unit.rollback()
        assert unit.state is TransactionState.ROLLED_BACK
    assert unit.is_closed is True
