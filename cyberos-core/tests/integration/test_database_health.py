import sqlite3
from pathlib import Path

from cyberos.config.models import DatabaseSettings
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.migrations.runner import MigrationRunner

KERNEL_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    execution_ms INTEGER NOT NULL CHECK (execution_ms >= 0)
);
"""


def test_health_reports_pragmas_and_uninitialized_schema(tmp_path: Path) -> None:
    factory = SQLiteConnectionFactory(DatabaseSettings(path=tmp_path / "cyberos.sqlite3"))
    with factory.connect() as managed:
        report = managed.health()
        assert report.healthy is False
        assert report.schema_version == 0
        assert report.schema_initialized is False
        assert report.quick_check.healthy is True
        assert report.pragma_state["journal_mode"] == "wal"
        assert report.pragma_state["synchronous"] == "full"


def test_health_reports_schema_version_after_migration(tmp_path: Path) -> None:
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    (migration_dir / "0001_persistence_kernel.sql").write_text(KERNEL_SQL, encoding="utf-8")
    factory = SQLiteConnectionFactory(DatabaseSettings(path=tmp_path / "cyberos.sqlite3"))
    MigrationRunner(factory, migration_dir).run()
    with factory.connect() as managed:
        report = managed.health()
        assert report.healthy is True
        assert report.schema_version == 1
        assert report.schema_initialized is True
        assert report.details["history_contiguous"] is True


def test_health_detects_non_contiguous_schema_history(tmp_path: Path) -> None:
    factory = SQLiteConnectionFactory(DatabaseSettings(path=tmp_path / "cyberos.sqlite3"))
    with factory.connect() as managed:
        managed.raw.execute(
            "CREATE TABLE schema_migrations ("
            "version INTEGER PRIMARY KEY, name TEXT NOT NULL, checksum TEXT NOT NULL, "
            "applied_at TEXT NOT NULL, execution_ms INTEGER NOT NULL)"
        )
        managed.raw.executemany(
            "INSERT INTO schema_migrations VALUES (?, ?, ?, ?, ?)",
            [(1, "one", "a", "now", 1), (3, "three", "b", "now", 1)],
        )
        report = managed.health()
        assert report.healthy is False
        assert report.schema_version == 3
        assert report.details["history_contiguous"] is False


def test_health_does_not_add_domain_tables(tmp_path: Path) -> None:
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    (migration_dir / "0001_persistence_kernel.sql").write_text(KERNEL_SQL, encoding="utf-8")
    factory = SQLiteConnectionFactory(DatabaseSettings(path=tmp_path / "cyberos.sqlite3"))
    MigrationRunner(factory, migration_dir).run()
    connection = sqlite3.connect(tmp_path / "cyberos.sqlite3")
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    connection.close()
    assert tables == {"schema_migrations"}
