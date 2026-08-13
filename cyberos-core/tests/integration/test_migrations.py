import sqlite3
from pathlib import Path

import pytest

from cyberos.config.models import DatabaseSettings
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.migrations.loader import checksum_sql, load_migrations
from cyberos.persistence.migrations.runner import MigrationRunner


def write_migration(directory: Path, filename: str, sql: str) -> None:
    (directory / filename).write_text(sql, encoding="utf-8")


def make_runner(tmp_path: Path, migration_dir: Path) -> MigrationRunner:
    settings = DatabaseSettings(path=tmp_path / "cyberos.sqlite3")
    return MigrationRunner(SQLiteConnectionFactory(settings), migration_dir)


def test_kernel_migration_creates_metadata_only(tmp_path: Path) -> None:
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    write_migration(
        migration_dir,
        "0001_persistence_kernel.sql",
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            execution_ms INTEGER NOT NULL
        );
        """,
    )
    result = make_runner(tmp_path, migration_dir).run()
    assert result.current_version == 1
    assert [migration.version for migration in result.applied] == [1]
    connection = sqlite3.connect(tmp_path / "cyberos.sqlite3")
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    connection.close()
    assert tables == {"schema_migrations"}


def test_runner_is_idempotent_and_records_checksum(tmp_path: Path) -> None:
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    sql = """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        checksum TEXT NOT NULL,
        applied_at TEXT NOT NULL,
        execution_ms INTEGER NOT NULL
    );
    """
    write_migration(migration_dir, "0001_persistence_kernel.sql", sql)
    first = make_runner(tmp_path, migration_dir).run()
    second = make_runner(tmp_path, migration_dir).run()
    assert len(first.applied) == 1
    assert second.applied == ()
    connection = sqlite3.connect(tmp_path / "cyberos.sqlite3")
    row = connection.execute("SELECT version, checksum FROM schema_migrations").fetchone()
    connection.close()
    assert row == (1, checksum_sql(sql))


def test_failed_second_migration_rolls_back_first_and_metadata(tmp_path: Path) -> None:
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    write_migration(
        migration_dir, "0001_first.sql", "CREATE TABLE first_table (id INTEGER PRIMARY KEY);"
    )
    write_migration(migration_dir, "0002_broken.sql", "CREATE TABLE broken_table (")
    with pytest.raises(CyberOSError) as captured:
        make_runner(tmp_path, migration_dir).run()
    assert captured.value.code == ErrorCode.MIGRATION_FAILED
    connection = sqlite3.connect(tmp_path / "cyberos.sqlite3")
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    connection.close()
    assert tables == set()


def test_checksum_mismatch_is_rejected_after_previous_apply(tmp_path: Path) -> None:
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    path = migration_dir / "0001_first.sql"
    path.write_text("CREATE TABLE first_table (id INTEGER PRIMARY KEY);", encoding="utf-8")
    make_runner(tmp_path, migration_dir).run()
    path.write_text(
        "CREATE TABLE first_table (id INTEGER PRIMARY KEY, changed TEXT);", encoding="utf-8"
    )
    with pytest.raises(CyberOSError) as captured:
        make_runner(tmp_path, migration_dir).run()
    assert captured.value.code == ErrorCode.MIGRATION_CHECKSUM_MISMATCH


def test_invalid_gap_is_rejected_before_database_change(tmp_path: Path) -> None:
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    write_migration(migration_dir, "0001_first.sql", "SELECT 1;")
    write_migration(migration_dir, "0003_third.sql", "SELECT 3;")
    with pytest.raises(CyberOSError) as captured:
        make_runner(tmp_path, migration_dir).run()
    assert captured.value.code == ErrorCode.MIGRATION_ORDER_INVALID
    assert not (tmp_path / "cyberos.sqlite3").exists()


def test_duplicate_versions_are_rejected(tmp_path: Path) -> None:
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    write_migration(migration_dir, "0001_first.sql", "SELECT 1;")
    write_migration(migration_dir, "0001_second.sql", "SELECT 2;")
    with pytest.raises(CyberOSError) as captured:
        load_migrations(migration_dir)
    assert captured.value.code == ErrorCode.MIGRATION_ORDER_INVALID


def test_invalid_filename_is_rejected(tmp_path: Path) -> None:
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    write_migration(migration_dir, "first.sql", "SELECT 1;")
    with pytest.raises(CyberOSError) as captured:
        load_migrations(migration_dir)
    assert captured.value.code == ErrorCode.MIGRATION_ORDER_INVALID
