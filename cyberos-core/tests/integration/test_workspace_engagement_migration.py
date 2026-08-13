from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from cyberos.config.models import DatabaseSettings
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.migrations.loader import checksum_sql
from cyberos.persistence.migrations.runner import MigrationRunner

MIGRATIONS_DIR = Path(__file__).parents[2] / "src/cyberos/persistence/migrations/versions"


def make_runner(tmp_path: Path, migration_dir: Path = MIGRATIONS_DIR) -> MigrationRunner:
    factory = SQLiteConnectionFactory(DatabaseSettings(path=tmp_path / "cyberos.sqlite3"))
    return MigrationRunner(factory, migration_dir)


def migrated_database(tmp_path: Path) -> sqlite3.Connection:
    make_runner(tmp_path).run()
    connection = sqlite3.connect(tmp_path / "cyberos.sqlite3")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def workspace_row(
    workspace_id: str,
    name: str = "Workspace",
    *,
    status: str = "active",
    archived_at: str | None = None,
    version: int = 1,
) -> tuple[object, ...]:
    return (
        workspace_id,
        name,
        "description",
        status,
        "2026-08-13T12:00:00+00:00",
        "2026-08-13T12:00:00+00:00",
        archived_at,
        version,
    )


def engagement_row(
    engagement_id: str,
    workspace_id: str,
    name: str = "Engagement",
    *,
    kind: str = "learning",
    status: str = "draft",
    authorization_reference: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
    archived_at: str | None = None,
    version: int = 1,
) -> tuple[object, ...]:
    return (
        engagement_id,
        workspace_id,
        name,
        kind,
        status,
        "description",
        authorization_reference,
        start_at,
        end_at,
        "2026-08-13T12:00:00+00:00",
        "2026-08-13T12:00:00+00:00",
        archived_at,
        version,
    )


def test_migration_applies_schema_and_records_checksum(tmp_path: Path) -> None:
    result = make_runner(tmp_path).run()
    migration_path = MIGRATIONS_DIR / "0002_workspace_engagement.sql"
    connection = sqlite3.connect(tmp_path / "cyberos.sqlite3")
    row = connection.execute(
        "SELECT version, name, checksum FROM schema_migrations WHERE version = 2"
    ).fetchone()
    tables = {
        item[0] for item in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    connection.close()
    assert [migration.version for migration in result.applied] == [1, 2]
    assert row == (
        2,
        "workspace_engagement",
        checksum_sql(migration_path.read_text(encoding="utf-8")),
    )
    assert tables == {"schema_migrations", "workspaces", "engagements"}


def test_migration_is_idempotent(tmp_path: Path) -> None:
    first = make_runner(tmp_path).run()
    second = make_runner(tmp_path).run()
    assert [migration.version for migration in first.applied] == [1, 2]
    assert second.applied == ()
    assert second.current_version == 2


def test_schema_health_and_foreign_key_check_are_clean(tmp_path: Path) -> None:
    make_runner(tmp_path).run()
    factory = SQLiteConnectionFactory(DatabaseSettings(path=tmp_path / "cyberos.sqlite3"))
    with factory.connect() as managed:
        report = managed.health()
        foreign_keys = managed.raw.execute("PRAGMA foreign_keys").fetchone()[0]
        foreign_key_errors = managed.raw.execute("PRAGMA foreign_key_check").fetchall()
        assert report.healthy is True
        assert report.schema_version == 2
        assert report.quick_check.details["result"] == "ok"
        assert report.pragma_state["journal_mode"] == "wal"
        assert foreign_keys == 1
        assert foreign_key_errors == []


def test_workspace_and_engagement_creation_schema(tmp_path: Path) -> None:
    connection = migrated_database(tmp_path)
    workspace_id = str(uuid4())
    engagement_id = str(uuid4())
    connection.execute(
        "INSERT INTO workspaces VALUES (?, ?, ?, ?, ?, ?, ?, ?)", workspace_row(workspace_id)
    )
    connection.execute(
        "INSERT INTO engagements VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        engagement_row(engagement_id, workspace_id),
    )
    stored = connection.execute(
        "SELECT workspace_id, kind, status, version FROM engagements"
    ).fetchone()
    connection.close()
    assert stored == (workspace_id, "learning", "draft", 1)


def test_workspace_name_is_unique_case_insensitively(tmp_path: Path) -> None:
    connection = migrated_database(tmp_path)
    connection.execute(
        "INSERT INTO workspaces VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        workspace_row(str(uuid4()), "Web Security"),
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO workspaces VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            workspace_row(str(uuid4()), "WEB SECURITY"),
        )
    connection.close()


def test_engagement_name_is_unique_inside_workspace_but_not_across_workspaces(
    tmp_path: Path,
) -> None:
    connection = migrated_database(tmp_path)
    workspace_a = str(uuid4())
    workspace_b = str(uuid4())
    connection.execute(
        "INSERT INTO workspaces VALUES (?, ?, ?, ?, ?, ?, ?, ?)", workspace_row(workspace_a, "A")
    )
    connection.execute(
        "INSERT INTO workspaces VALUES (?, ?, ?, ?, ?, ?, ?, ?)", workspace_row(workspace_b, "B")
    )
    connection.execute(
        "INSERT INTO engagements VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        engagement_row(str(uuid4()), workspace_a, "API Lab"),
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO engagements VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            engagement_row(str(uuid4()), workspace_a, "API LAB"),
        )
    connection.execute(
        "INSERT INTO engagements VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        engagement_row(str(uuid4()), workspace_b, "API Lab"),
    )
    count = connection.execute("SELECT count(*) FROM engagements").fetchone()[0]
    connection.close()
    assert count == 2


@pytest.mark.parametrize(
    "row, insert_sql",
    [
        (
            lambda workspace_id: workspace_row(str(uuid4()), status="invalid"),
            "INSERT INTO workspaces VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ),
        (
            lambda workspace_id: workspace_row(str(uuid4()), archived_at=None, status="archived"),
            "INSERT INTO workspaces VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ),
    ],
)
def test_workspace_status_and_archive_constraints(row, insert_sql: str, tmp_path: Path) -> None:
    connection = migrated_database(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(insert_sql, row(str(uuid4())))
    connection.close()


@pytest.mark.parametrize(
    "row",
    [
        lambda workspace_id: engagement_row(str(uuid4()), workspace_id, kind="invalid"),
        lambda workspace_id: engagement_row(str(uuid4()), workspace_id, status="invalid"),
        lambda workspace_id: engagement_row(str(uuid4()), workspace_id, status="archived"),
        lambda workspace_id: engagement_row(
            str(uuid4()), workspace_id, kind="authorized_assessment", status="active"
        ),
        lambda workspace_id: engagement_row(str(uuid4()), workspace_id, status="completed"),
        lambda workspace_id: engagement_row(
            str(uuid4()),
            workspace_id,
            start_at="2026-08-13T13:00:00+00:00",
            end_at="2026-08-13T12:00:00+00:00",
        ),
        lambda workspace_id: engagement_row(str(uuid4()), workspace_id, version=0),
    ],
)
def test_engagement_checks_reject_invalid_rows(row, tmp_path: Path) -> None:
    connection = migrated_database(tmp_path)
    workspace_id = str(uuid4())
    connection.execute(
        "INSERT INTO workspaces VALUES (?, ?, ?, ?, ?, ?, ?, ?)", workspace_row(workspace_id)
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO engagements VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            row(workspace_id),
        )
    connection.close()


def test_foreign_key_and_restrict_policies(tmp_path: Path) -> None:
    connection = migrated_database(tmp_path)
    workspace_id = str(uuid4())
    connection.execute(
        "INSERT INTO workspaces VALUES (?, ?, ?, ?, ?, ?, ?, ?)", workspace_row(workspace_id)
    )
    connection.execute(
        "INSERT INTO engagements VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        engagement_row(str(uuid4()), workspace_id),
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE workspaces SET id = ? WHERE id = ?", (str(uuid4()), workspace_id)
        )
    connection.close()


def test_atomic_rollback_leaves_no_partial_domain_tables(tmp_path: Path) -> None:
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    shutil.copy(
        MIGRATIONS_DIR / "0001_persistence_kernel.sql",
        migration_dir / "0001_persistence_kernel.sql",
    )
    source = (MIGRATIONS_DIR / "0002_workspace_engagement.sql").read_text(encoding="utf-8")
    (migration_dir / "0002_workspace_engagement.sql").write_text(
        source + "\nCREATE TABLE broken_table (\n", encoding="utf-8"
    )
    with pytest.raises(CyberOSError) as captured:
        make_runner(tmp_path, migration_dir).run()
    connection = sqlite3.connect(tmp_path / "cyberos.sqlite3")
    tables = {
        item[0] for item in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    connection.close()
    assert captured.value.code == ErrorCode.MIGRATION_FAILED
    assert tables == set()


def test_checksum_mismatch_after_apply_is_rejected(tmp_path: Path) -> None:
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    shutil.copy(
        MIGRATIONS_DIR / "0001_persistence_kernel.sql",
        migration_dir / "0001_persistence_kernel.sql",
    )
    migration_path = migration_dir / "0002_workspace_engagement.sql"
    migration_path.write_text(
        (MIGRATIONS_DIR / "0002_workspace_engagement.sql").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    make_runner(tmp_path, migration_dir).run()
    migration_path.write_text(
        migration_path.read_text(encoding="utf-8") + "\n-- changed after apply\n", encoding="utf-8"
    )
    with pytest.raises(CyberOSError) as captured:
        make_runner(tmp_path, migration_dir).run()
    assert captured.value.code == ErrorCode.MIGRATION_CHECKSUM_MISMATCH


def test_no_future_domain_tables_are_created(tmp_path: Path) -> None:
    connection = migrated_database(tmp_path)
    tables = {
        item[0] for item in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    connection.close()
    assert not tables.intersection(
        {"targets", "scopes", "findings", "evidence", "scans", "jobs", "reports"}
    )
