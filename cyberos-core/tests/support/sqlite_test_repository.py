from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TestRecord:
    entity_id: UUID
    value: str


class SQLiteTestRecordRepository:
    """Test-only repository used to exercise the production Repository port."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def ensure_table(self) -> None:
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS test_records "
            "(entity_id TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )

    def get(self, entity_id: UUID) -> TestRecord | None:
        row = self.connection.execute(
            "SELECT entity_id, value FROM test_records WHERE entity_id = ?", (str(entity_id),)
        ).fetchone()
        return TestRecord(entity_id=UUID(str(row[0])), value=str(row[1])) if row else None

    def add(self, record: TestRecord) -> TestRecord:
        self.connection.execute(
            "INSERT INTO test_records (entity_id, value) VALUES (?, ?)",
            (str(record.entity_id), record.value),
        )
        return record

    def update(self, record: TestRecord) -> TestRecord:
        self.connection.execute(
            "UPDATE test_records SET value = ? WHERE entity_id = ?",
            (record.value, str(record.entity_id)),
        )
        return record

    def delete(self, entity_id: UUID) -> bool:
        cursor = self.connection.execute(
            "DELETE FROM test_records WHERE entity_id = ?", (str(entity_id),)
        )
        return cursor.rowcount == 1

    def exists(self, entity_id: UUID) -> bool:
        return self.get(entity_id) is not None
