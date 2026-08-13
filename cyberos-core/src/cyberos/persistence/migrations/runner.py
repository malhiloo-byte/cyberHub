from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.time import utc_now
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.health import run_quick_check
from cyberos.persistence.migrations.loader import load_migrations
from cyberos.persistence.migrations.models import AppliedMigration, Migration, MigrationRunResult

METADATA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    execution_ms INTEGER NOT NULL CHECK (execution_ms >= 0)
)
"""


def _execute_sql_script(connection: sqlite3.Connection, sql: str, migration: Migration) -> None:
    """Execute a trusted SQL file statement-by-statement without implicit commits."""

    statement_buffer = ""
    try:
        for line in sql.splitlines(keepends=True):
            statement_buffer += line
            if sqlite3.complete_statement(statement_buffer):
                statement = statement_buffer.strip()
                if statement:
                    connection.execute(statement)
                statement_buffer = ""
        if statement_buffer.strip():
            raise sqlite3.OperationalError("incomplete SQL statement")
    except sqlite3.DatabaseError as exc:
        raise CyberOSError(
            ErrorCode.MIGRATION_FAILED,
            "A migration SQL statement failed.",
            details={"version": migration.version, "name": migration.name},
        ) from exc


class MigrationRunner:
    """Applies ordered SQL migrations atomically to a hardened SQLite database."""

    def __init__(self, factory: SQLiteConnectionFactory, directory: Path) -> None:
        self.factory = factory
        self.directory = directory

    def run(self) -> MigrationRunResult:
        migrations = load_migrations(self.directory)
        migration_by_version = {migration.version: migration for migration in migrations}
        applied_now: list[Migration] = []
        with self.factory.connect() as managed:
            connection = managed.raw
            began = False
            try:
                connection.execute("BEGIN IMMEDIATE")
                began = True
                connection.execute(METADATA_SQL)
                applied = self._load_applied(connection)
                self._validate_history(applied, migration_by_version)
                for migration in migrations:
                    previous = applied.get(migration.version)
                    if previous is not None:
                        if (
                            previous.checksum != migration.checksum
                            or previous.name != migration.name
                        ):
                            raise CyberOSError(
                                ErrorCode.MIGRATION_CHECKSUM_MISMATCH,
                                "An applied migration no longer matches its recorded checksum.",
                                details={"version": migration.version, "name": migration.name},
                            )
                        continue
                    started_at = time.perf_counter()
                    _execute_sql_script(connection, migration.sql, migration)
                    execution_ms = max(0, round((time.perf_counter() - started_at) * 1000))
                    connection.execute(
                        "INSERT INTO schema_migrations "
                        "(version, name, checksum, applied_at, execution_ms) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            migration.version,
                            migration.name,
                            migration.checksum,
                            utc_now().isoformat(),
                            execution_ms,
                        ),
                    )
                    applied_now.append(migration)
                integrity = run_quick_check(connection)
                if not integrity.healthy:
                    raise CyberOSError(
                        ErrorCode.DATABASE_INTEGRITY_FAILED,
                        "SQLite integrity check failed during migration.",
                        details=integrity.details,
                    )
                connection.commit()
                began = False
            except CyberOSError:
                if began:
                    connection.rollback()
                raise
            except sqlite3.DatabaseError as exc:
                if began:
                    connection.rollback()
                raise CyberOSError(
                    ErrorCode.MIGRATION_FAILED, "The migration transaction failed."
                ) from exc
            current_version = max((migration.version for migration in migrations), default=0)
            return MigrationRunResult(applied=tuple(applied_now), current_version=current_version)

    @staticmethod
    def _load_applied(connection: sqlite3.Connection) -> dict[int, AppliedMigration]:
        try:
            rows = connection.execute(
                "SELECT version, name, checksum, applied_at, execution_ms "
                "FROM schema_migrations ORDER BY version"
            ).fetchall()
        except sqlite3.DatabaseError as exc:
            raise CyberOSError(
                ErrorCode.MIGRATION_HISTORY_INVALID, "Migration history could not be read."
            ) from exc
        return {
            int(row[0]): AppliedMigration(
                version=int(row[0]),
                name=str(row[1]),
                checksum=str(row[2]),
                applied_at=str(row[3]),
                execution_ms=int(row[4]),
            )
            for row in rows
        }

    @staticmethod
    def _validate_history(
        applied: dict[int, AppliedMigration], available: dict[int, Migration]
    ) -> None:
        if not applied:
            return
        versions = sorted(applied)
        expected = list(range(1, versions[-1] + 1))
        if versions != expected or any(version not in available for version in versions):
            raise CyberOSError(
                ErrorCode.MIGRATION_HISTORY_INVALID,
                "Applied migration history is not contiguous or contains an unavailable version.",
                details={"versions": versions},
            )
