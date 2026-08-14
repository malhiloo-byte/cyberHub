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
TS = "2026-08-13T12:00:00+00:00"


def make_runner(tmp_path: Path, migration_dir: Path = MIGRATIONS_DIR) -> MigrationRunner:
    factory = SQLiteConnectionFactory(DatabaseSettings(path=tmp_path / "cyberos.sqlite3"))
    return MigrationRunner(factory, migration_dir)


def migrated_database(tmp_path: Path) -> sqlite3.Connection:
    make_runner(tmp_path).run()
    connection = sqlite3.connect(tmp_path / "cyberos.sqlite3")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def insert_workspace(
    connection: sqlite3.Connection, workspace_id: str, name: str = "Workspace"
) -> None:
    connection.execute(
        "INSERT INTO workspaces VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (workspace_id, name, "description", "active", TS, TS, None, 1),
    )


def insert_engagement(
    connection: sqlite3.Connection,
    engagement_id: str,
    workspace_id: str,
    name: str = "Engagement",
) -> None:
    connection.execute(
        "INSERT INTO engagements VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            engagement_id,
            workspace_id,
            name,
            "learning",
            "draft",
            "description",
            None,
            None,
            None,
            TS,
            TS,
            None,
            1,
        ),
    )


def insert_scope(
    connection: sqlite3.Connection,
    scope_id: str,
    engagement_id: str,
    name: str = "API Scope",
    *,
    status: str = "draft",
    authorization_reference: str | None = None,
    validated_at: str | None = None,
    authorized_at: str | None = None,
    expires_at: str | None = None,
    archived_at: str | None = None,
    version: int = 1,
) -> None:
    connection.execute(
        "INSERT INTO scopes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            scope_id,
            engagement_id,
            name,
            "description",
            status,
            authorization_reference,
            validated_at,
            authorized_at,
            expires_at,
            TS,
            TS,
            archived_at,
            version,
        ),
    )


def insert_target(
    connection: sqlite3.Connection,
    target_id: str,
    scope_id: str,
    *,
    rule: str = "include",
    kind: str = "fqdn",
    value: str = "api.example.com",
    status: str = "active",
    archived_at: str | None = None,
    version: int = 1,
) -> None:
    connection.execute(
        "INSERT INTO targets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (target_id, scope_id, rule, kind, value, status, TS, TS, archived_at, version),
    )


def test_migration_0003_schema_and_checksum(tmp_path: Path) -> None:
    result = make_runner(tmp_path).run()
    connection = sqlite3.connect(tmp_path / "cyberos.sqlite3")
    row = connection.execute(
        "SELECT version, name, checksum FROM schema_migrations WHERE version = 3"
    ).fetchone()
    tables = {
        item[0] for item in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    connection.close()

    migration_path = MIGRATIONS_DIR / "0003_target_scope.sql"
    assert [migration.version for migration in result.applied] == [1, 2, 3, 4, 5, 6]
    assert row == (3, "target_scope", checksum_sql(migration_path.read_text(encoding="utf-8")))
    assert tables == {
        "schema_migrations",
        "workspaces",
        "engagements",
        "scopes",
        "targets",
        "tasks",
        "assets",
        "asset_observations",
        "subdomain_records",
        "port_service_records",
        "http_endpoint_records",
        "evidence_records",
    }


def test_migration_0003_is_idempotent_and_forward_only(tmp_path: Path) -> None:
    first = make_runner(tmp_path).run()
    second = make_runner(tmp_path).run()
    source = (MIGRATIONS_DIR / "0003_target_scope.sql").read_text(encoding="utf-8")

    assert [migration.version for migration in first.applied] == [1, 2, 3, 4, 5, 6]
    assert second.applied == ()
    assert second.current_version == 6
    assert "IF NOT EXISTS" not in source.upper()
    assert "BEGIN" not in source.upper()
    assert "COMMIT" not in source.upper()


def test_schema_health_and_foreign_key_check_are_clean(tmp_path: Path) -> None:
    make_runner(tmp_path).run()
    factory = SQLiteConnectionFactory(DatabaseSettings(path=tmp_path / "cyberos.sqlite3"))
    with factory.connect() as managed:
        report = managed.health()
        assert report.healthy is True
        assert report.schema_version == 6
        assert managed.raw.execute("PRAGMA foreign_key_check").fetchall() == []
        assert managed.raw.execute("PRAGMA quick_check").fetchone()[0] == "ok"


def test_scope_and_target_unique_indexes_are_enforced(tmp_path: Path) -> None:
    connection = migrated_database(tmp_path)
    workspace_id = str(uuid4())
    engagement_id = str(uuid4())
    scope_id = str(uuid4())
    insert_workspace(connection, workspace_id)
    insert_engagement(connection, engagement_id, workspace_id)
    insert_scope(connection, scope_id, engagement_id, "External API")

    with pytest.raises(sqlite3.IntegrityError):
        insert_scope(connection, str(uuid4()), engagement_id, "external api")

    insert_target(connection, str(uuid4()), scope_id)
    with pytest.raises(sqlite3.IntegrityError):
        insert_target(connection, str(uuid4()), scope_id)
    connection.close()


def test_scope_name_can_repeat_in_different_engagements(tmp_path: Path) -> None:
    connection = migrated_database(tmp_path)
    workspace_id = str(uuid4())
    first_engagement = str(uuid4())
    second_engagement = str(uuid4())
    insert_workspace(connection, workspace_id)
    insert_engagement(connection, first_engagement, workspace_id, "First")
    insert_engagement(connection, second_engagement, workspace_id, "Second")
    insert_scope(connection, str(uuid4()), first_engagement, "Shared Name")
    insert_scope(connection, str(uuid4()), second_engagement, "Shared Name")
    assert connection.execute("SELECT count(*) FROM scopes").fetchone()[0] == 2
    connection.close()


@pytest.mark.parametrize(
    "operation",
    [
        lambda connection, scope_id, engagement_id: insert_scope(
            connection, str(uuid4()), engagement_id, status="unknown"
        ),
        lambda connection, scope_id, engagement_id: insert_scope(
            connection, str(uuid4()), engagement_id, status="validated"
        ),
        lambda connection, scope_id, engagement_id: insert_scope(
            connection,
            str(uuid4()),
            engagement_id,
            status="authorized",
            authorization_reference=None,
            validated_at=TS,
            authorized_at=TS,
        ),
        lambda connection, scope_id, engagement_id: insert_scope(
            connection,
            str(uuid4()),
            engagement_id,
            status="authorized",
            authorization_reference="approval",
            validated_at=TS,
            authorized_at=TS,
            expires_at=TS,
        ),
        lambda connection, scope_id, engagement_id: insert_scope(
            connection, str(uuid4()), engagement_id, version=0
        ),
    ],
)
def test_scope_constraints_reject_invalid_state(operation, tmp_path: Path) -> None:
    connection = migrated_database(tmp_path)
    workspace_id = str(uuid4())
    engagement_id = str(uuid4())
    insert_workspace(connection, workspace_id)
    insert_engagement(connection, engagement_id, workspace_id)
    with pytest.raises(sqlite3.IntegrityError):
        operation(connection, str(uuid4()), engagement_id)
    connection.close()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"rule": "unknown"},
        {"kind": "unknown"},
        {"status": "unknown"},
        {"status": "active", "archived_at": TS},
        {"value": ""},
        {"version": 0},
    ],
)
def test_target_constraints_reject_invalid_values(
    kwargs: dict[str, object], tmp_path: Path
) -> None:
    connection = migrated_database(tmp_path)
    workspace_id = str(uuid4())
    engagement_id = str(uuid4())
    scope_id = str(uuid4())
    insert_workspace(connection, workspace_id)
    insert_engagement(connection, engagement_id, workspace_id)
    insert_scope(connection, scope_id, engagement_id)
    with pytest.raises(sqlite3.IntegrityError):
        insert_target(connection, str(uuid4()), scope_id, **kwargs)
    connection.close()


def test_scope_and_target_foreign_keys_use_restrict(tmp_path: Path) -> None:
    connection = migrated_database(tmp_path)
    workspace_id = str(uuid4())
    engagement_id = str(uuid4())
    scope_id = str(uuid4())
    insert_workspace(connection, workspace_id)
    insert_engagement(connection, engagement_id, workspace_id)
    insert_scope(connection, scope_id, engagement_id)
    insert_target(connection, str(uuid4()), scope_id)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("DELETE FROM engagements WHERE id = ?", (engagement_id,))
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE engagements SET id = ? WHERE id = ?", (str(uuid4()), engagement_id)
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("DELETE FROM scopes WHERE id = ?", (scope_id,))
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("UPDATE scopes SET id = ? WHERE id = ?", (str(uuid4()), scope_id))
    connection.close()


def test_migration_0003_atomic_failure_rolls_back_all_schema_changes(tmp_path: Path) -> None:
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    for version in ("0001_persistence_kernel.sql", "0002_workspace_engagement.sql"):
        shutil.copy(MIGRATIONS_DIR / version, migration_dir / version)
    source = (MIGRATIONS_DIR / "0003_target_scope.sql").read_text(encoding="utf-8")
    (migration_dir / "0003_target_scope.sql").write_text(
        source + "\nCREATE TABLE broken_table (\n", encoding="utf-8"
    )

    with pytest.raises(CyberOSError) as captured:
        make_runner(tmp_path, migration_dir).run()

    connection = sqlite3.connect(tmp_path / "cyberos.sqlite3")
    tables = {
        item[0] for item in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    connection.close()
    assert captured.value.code is ErrorCode.MIGRATION_FAILED
    assert tables == set()


def test_migration_0003_checksum_mismatch_is_rejected_after_apply(tmp_path: Path) -> None:
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    versions = (
        "0001_persistence_kernel.sql",
        "0002_workspace_engagement.sql",
        "0003_target_scope.sql",
    )
    for version in versions:
        shutil.copy(MIGRATIONS_DIR / version, migration_dir / version)
    make_runner(tmp_path, migration_dir).run()
    migration_path = migration_dir / "0003_target_scope.sql"
    migration_path.write_text(
        migration_path.read_text(encoding="utf-8") + "\n-- changed after apply\n",
        encoding="utf-8",
    )

    with pytest.raises(CyberOSError) as captured:
        make_runner(tmp_path, migration_dir).run()

    assert captured.value.code is ErrorCode.MIGRATION_CHECKSUM_MISMATCH
