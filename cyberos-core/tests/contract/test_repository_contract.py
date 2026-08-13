from pathlib import Path
from uuid import UUID, uuid4

from cyberos.config.models import DatabaseSettings
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork


class ContractRecord:
    def __init__(self, entity_id: UUID, value: str) -> None:
        self.entity_id = entity_id
        self.value = value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ContractRecord) and (self.entity_id, self.value) == (
            other.entity_id,
            other.value,
        )


class SQLiteContractRepository:
    def __init__(self, connection) -> None:
        self.connection = connection

    def get(self, entity_id: UUID) -> ContractRecord | None:
        row = self.connection.execute(
            "SELECT entity_id, value FROM contract_records WHERE entity_id = ?", (str(entity_id),)
        ).fetchone()
        return ContractRecord(UUID(str(row[0])), str(row[1])) if row else None

    def add(self, record: ContractRecord) -> ContractRecord:
        self.connection.execute(
            "INSERT INTO contract_records (entity_id, value) VALUES (?, ?)",
            (str(record.entity_id), record.value),
        )
        return record

    def update(self, record: ContractRecord) -> ContractRecord:
        self.connection.execute(
            "UPDATE contract_records SET value = ? WHERE entity_id = ?",
            (record.value, str(record.entity_id)),
        )
        return record

    def delete(self, entity_id: UUID) -> bool:
        cursor = self.connection.execute(
            "DELETE FROM contract_records WHERE entity_id = ?", (str(entity_id),)
        )
        return cursor.rowcount == 1

    def exists(self, entity_id: UUID) -> bool:
        return self.get(entity_id) is not None


def factory_for(tmp_path: Path) -> SQLiteConnectionFactory:
    return SQLiteConnectionFactory(DatabaseSettings(path=tmp_path / "cyberos.sqlite3"))


def initialize_table(factory: SQLiteConnectionFactory) -> None:
    with factory.connect() as managed:
        managed.raw.execute(
            "CREATE TABLE contract_records (entity_id TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )


def test_repository_contract_covers_add_get_exists_update_delete(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    initialize_table(factory)
    record = ContractRecord(uuid4(), "first")
    with SQLiteUnitOfWork(factory) as unit:
        repository = SQLiteContractRepository(unit.raw)
        assert repository.exists(record.entity_id) is False
        assert repository.add(record) == record
        assert repository.get(record.entity_id) == record
        changed = ContractRecord(record.entity_id, "updated")
        assert repository.update(changed) == changed
        assert repository.get(record.entity_id) == changed
        assert repository.delete(record.entity_id) is True
        assert repository.delete(record.entity_id) is False
        assert repository.exists(record.entity_id) is False
        unit.commit()
