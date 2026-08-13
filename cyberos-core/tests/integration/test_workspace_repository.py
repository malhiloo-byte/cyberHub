from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from cyberos.config.models import DatabaseSettings
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.workspace.model import Workspace, WorkspaceStatus
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.migrations.runner import MigrationRunner
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork
from cyberos.persistence.workspace_repository import SQLiteWorkspaceRepository

MIGRATIONS_DIR = Path(__file__).parents[2] / "src/cyberos/persistence/migrations/versions"


def factory_for(tmp_path: Path) -> SQLiteConnectionFactory:
    factory = SQLiteConnectionFactory(DatabaseSettings(path=tmp_path / "cyberos.sqlite3"))
    MigrationRunner(factory, MIGRATIONS_DIR).run()
    return factory


def persist(factory: SQLiteConnectionFactory, workspace: Workspace) -> Workspace:
    with SQLiteUnitOfWork(factory) as unit:
        saved = SQLiteWorkspaceRepository(unit).add(workspace)
        unit.commit()
        return saved


def fetch(factory: SQLiteConnectionFactory, workspace_id) -> Workspace | None:
    with SQLiteUnitOfWork(factory) as unit:
        result = SQLiteWorkspaceRepository(unit).get(workspace_id)
        unit.rollback()
        return result


def test_round_trip_mapping_preserves_uuid_utc_and_all_fields(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    created = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
    workspace = Workspace.create(
        "  Mapping Workspace  ",
        "  Exact round trip  ",
        now=created,
    )
    persisted = persist(factory, workspace)
    loaded = fetch(factory, workspace.id)
    assert persisted == workspace
    assert loaded == workspace
    assert loaded is not None
    assert loaded.id == workspace.id
    assert loaded.created_at == created
    assert loaded.updated_at == created
    assert loaded.version == 1
    assert isinstance(loaded, Workspace)


def test_repository_crud_exists_list_and_default_ordering(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    base = datetime(2026, 8, 13, 12, tzinfo=UTC)
    older = Workspace.create("Older", now=base)
    newer = Workspace.create("Newer", now=base + timedelta(hours=1))
    tie_a = Workspace.create("Tie A", now=base + timedelta(hours=2))
    tie_b = Workspace.create("Tie B", now=base + timedelta(hours=2))
    for workspace in (older, newer, tie_b, tie_a):
        persist(factory, workspace)
    with SQLiteUnitOfWork(factory) as unit:
        repository = SQLiteWorkspaceRepository(unit)
        assert repository.exists(newer.id) is True
        assert repository.exists(uuid4()) is False
        listed = repository.list()
        # For equal timestamps, the SQL contract uses id ASC; assert the exact tuple order.
        expected = sorted(
            (older, newer, tie_a, tie_b),
            key=lambda item: (-item.created_at.timestamp(), str(item.id)),
        )
        assert [item.id for item in listed] == [item.id for item in expected]
        assert [item.id for item in repository.list(status=WorkspaceStatus.ACTIVE)] == [
            item.id for item in expected
        ]
        unit.rollback()


def test_update_uses_expected_version_and_increments_version(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    workspace = persist(factory, Workspace.create("Before"))
    changed = workspace.model_copy(
        update={"name": "After", "updated_at": workspace.created_at + timedelta(minutes=1)}
    )
    with SQLiteUnitOfWork(factory) as unit:
        updated = SQLiteWorkspaceRepository(unit).update(changed, expected_version=1)
        assert updated.name == "After"
        assert updated.version == 2
        unit.commit()
    assert fetch(factory, workspace.id) == updated


def test_stale_version_raises_concurrency_conflict_without_modification(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    workspace = persist(factory, Workspace.create("Stable"))
    changed = workspace.model_copy(
        update={"name": "Changed", "updated_at": workspace.created_at + timedelta(minutes=1)}
    )
    with SQLiteUnitOfWork(factory) as unit:
        SQLiteWorkspaceRepository(unit).update(changed, expected_version=1)
        unit.commit()
    stale = workspace.model_copy(
        update={"name": "Stale", "updated_at": workspace.created_at + timedelta(minutes=2)}
    )
    with SQLiteUnitOfWork(factory) as unit:
        with pytest.raises(CyberOSError) as captured:
            SQLiteWorkspaceRepository(unit).update(stale, expected_version=1)
        assert captured.value.code == ErrorCode.CONCURRENCY_CONFLICT
        unit.rollback()
    assert fetch(factory, workspace.id).name == "Changed"


def test_archive_persists_timestamp_and_version_increment(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    workspace = persist(factory, Workspace.create("To Archive"))
    with SQLiteUnitOfWork(factory) as unit:
        archived = SQLiteWorkspaceRepository(unit).archive(workspace.id, expected_version=1)
        assert archived.status is WorkspaceStatus.ARCHIVED
        assert archived.archived_at is not None
        assert archived.archived_at == archived.updated_at
        assert archived.version == 2
        unit.commit()
    loaded = fetch(factory, workspace.id)
    assert loaded is not None
    assert loaded.status is WorkspaceStatus.ARCHIVED
    assert loaded.archived_at is not None
    assert loaded.version == 2


def test_duplicate_name_translates_to_typed_error_without_sql_leakage(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    persist(factory, Workspace.create("Unique Name"))
    with SQLiteUnitOfWork(factory) as unit:
        with pytest.raises(CyberOSError) as captured:
            SQLiteWorkspaceRepository(unit).add(Workspace.create("UNIQUE NAME"))
        assert captured.value.code == ErrorCode.WORKSPACE_NAME_CONFLICT
        assert "sqlite" not in captured.value.message.lower()
        assert "unique constraint" not in captured.value.message.lower()
        assert "workspaces" not in captured.value.message.lower()
        unit.rollback()


def test_exception_inside_unit_of_work_rolls_back_all_workspace_changes(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    workspace = Workspace.create("Must Roll Back")
    with pytest.raises(RuntimeError, match="force rollback"):
        with SQLiteUnitOfWork(factory) as unit:
            SQLiteWorkspaceRepository(unit).add(workspace)
            raise RuntimeError("force rollback")
    assert fetch(factory, workspace.id) is None


def test_repository_never_returns_sqlite_row(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    workspace = persist(factory, Workspace.create("No Row Leak"))
    with SQLiteUnitOfWork(factory) as unit:
        repository = SQLiteWorkspaceRepository(unit)
        loaded = repository.get(workspace.id)
        listed = repository.list()
        unit.rollback()
    assert isinstance(loaded, Workspace)
    assert all(isinstance(item, Workspace) for item in listed)
    assert not isinstance(loaded, tuple)
