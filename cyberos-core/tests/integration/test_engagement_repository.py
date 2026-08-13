from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from cyberos.config.models import DatabaseSettings
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.engagement.model import Engagement, EngagementKind, EngagementStatus
from cyberos.domain.workspace.model import Workspace
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.engagement_repository import SQLiteEngagementRepository
from cyberos.persistence.migrations.runner import MigrationRunner
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork
from cyberos.persistence.workspace_repository import SQLiteWorkspaceRepository

MIGRATIONS_DIR = Path(__file__).parents[2] / "src/cyberos/persistence/migrations/versions"


def factory_for(tmp_path: Path) -> SQLiteConnectionFactory:
    factory = SQLiteConnectionFactory(DatabaseSettings(path=tmp_path / "cyberos.sqlite3"))
    MigrationRunner(factory, MIGRATIONS_DIR).run()
    return factory


def active_workspace(factory: SQLiteConnectionFactory, name: str = "Workspace") -> Workspace:
    workspace = Workspace.create(name)
    with SQLiteUnitOfWork(factory) as unit:
        SQLiteWorkspaceRepository(unit).add(workspace)
        unit.commit()
    return workspace


def archive_workspace(factory: SQLiteConnectionFactory, workspace: Workspace) -> None:
    with SQLiteUnitOfWork(factory) as unit:
        SQLiteWorkspaceRepository(unit).archive(workspace.id, expected_version=1)
        unit.commit()


def persist(factory: SQLiteConnectionFactory, engagement: Engagement) -> Engagement:
    with SQLiteUnitOfWork(factory) as unit:
        saved = SQLiteEngagementRepository(unit).add(engagement)
        unit.commit()
        return saved


def fetch(factory: SQLiteConnectionFactory, engagement_id) -> Engagement | None:
    with SQLiteUnitOfWork(factory) as unit:
        result = SQLiteEngagementRepository(unit).get(engagement_id)
        unit.rollback()
        return result


def test_round_trip_preserves_optional_fields_enums_and_utc_timestamps(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    workspace = active_workspace(factory)
    created = datetime(2026, 8, 13, 12, tzinfo=UTC)
    start = created + timedelta(minutes=10)
    engagement = Engagement.create(
        workspace.id,
        "  Authorized API Review  ",
        EngagementKind.AUTHORIZED_ASSESSMENT,
        "  precise mapping  ",
        "  approval-123  ",
        start_at=start,
        now=created,
    )
    persisted = persist(factory, engagement)
    loaded = fetch(factory, engagement.id)
    assert persisted == engagement
    assert loaded == engagement
    assert loaded is not None
    assert loaded.kind is EngagementKind.AUTHORIZED_ASSESSMENT
    assert loaded.status is EngagementStatus.DRAFT
    assert loaded.authorization_reference == "approval-123"
    assert loaded.start_at == start
    assert loaded.end_at is None
    assert loaded.created_at == created
    assert loaded.version == 1


def test_add_requires_existing_active_workspace(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    missing_workspace_id = uuid4()
    engagement = Engagement.create(missing_workspace_id, "Missing Parent", EngagementKind.LEARNING)
    with SQLiteUnitOfWork(factory) as unit:
        with pytest.raises(CyberOSError) as captured:
            SQLiteEngagementRepository(unit).add(engagement)
        assert captured.value.code == ErrorCode.WORKSPACE_NOT_FOUND
        unit.rollback()

    workspace = active_workspace(factory, "Will Archive")
    archive_workspace(factory, workspace)
    archived_engagement = Engagement.create(workspace.id, "Blocked", EngagementKind.LEARNING)
    with SQLiteUnitOfWork(factory) as unit:
        with pytest.raises(CyberOSError) as captured:
            SQLiteEngagementRepository(unit).add(archived_engagement)
        assert captured.value.code == ErrorCode.WORKSPACE_ARCHIVED
        unit.rollback()


def test_activation_requires_workspace_to_remain_active(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    workspace = active_workspace(factory)
    engagement = persist(
        factory, Engagement.create(workspace.id, "Delayed Activation", EngagementKind.LEARNING)
    )
    archive_workspace(factory, workspace)
    with SQLiteUnitOfWork(factory) as unit:
        with pytest.raises(CyberOSError) as captured:
            SQLiteEngagementRepository(unit).transition(
                engagement.id,
                EngagementStatus.ACTIVE,
                expected_version=1,
            )
        assert captured.value.code == ErrorCode.WORKSPACE_ARCHIVED
        unit.rollback()


def test_list_by_workspace_and_status_is_deterministic(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    workspace = active_workspace(factory)
    created = datetime(2026, 8, 13, 12, tzinfo=UTC)
    older = Engagement.create(workspace.id, "Older", EngagementKind.LEARNING, now=created)
    newer = Engagement.create(
        workspace.id, "Newer", EngagementKind.RESEARCH, now=created + timedelta(hours=1)
    )
    persist(factory, older)
    persist(factory, newer)
    with SQLiteUnitOfWork(factory) as unit:
        repository = SQLiteEngagementRepository(unit)
        listed = repository.list_by_workspace(workspace.id)
        assert [item.name for item in listed] == ["Newer", "Older"]
        assert [
            item.name
            for item in repository.list_by_workspace(workspace.id, status=EngagementStatus.DRAFT)
        ] == [
            "Newer",
            "Older",
        ]
        unit.rollback()


def test_duplicate_engagement_name_is_scoped_and_typed(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    workspace_a = active_workspace(factory, "A")
    workspace_b = active_workspace(factory, "B")
    persist(factory, Engagement.create(workspace_a.id, "API Lab", EngagementKind.LEARNING))
    with SQLiteUnitOfWork(factory) as unit:
        with pytest.raises(CyberOSError) as captured:
            SQLiteEngagementRepository(unit).add(
                Engagement.create(workspace_a.id, "api LAB", EngagementKind.RESEARCH)
            )
        assert captured.value.code == ErrorCode.ENGAGEMENT_NAME_CONFLICT
        assert "sqlite" not in captured.value.message.lower()
        unit.rollback()
    persist(factory, Engagement.create(workspace_b.id, "API Lab", EngagementKind.RESEARCH))
    with SQLiteUnitOfWork(factory) as unit:
        assert len(SQLiteEngagementRepository(unit).list_by_workspace(workspace_b.id)) == 1
        unit.rollback()


def test_transition_persists_status_timestamp_and_version(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    workspace = active_workspace(factory)
    created = datetime(2026, 8, 13, 12, tzinfo=UTC)
    engagement = persist(
        factory,
        Engagement.create(workspace.id, "Transition", EngagementKind.LEARNING, now=created),
    )
    transition_at = datetime(2026, 8, 13, 13, tzinfo=UTC)
    with SQLiteUnitOfWork(factory) as unit:
        transitioned = SQLiteEngagementRepository(unit).transition(
            engagement.id,
            EngagementStatus.ACTIVE,
            expected_version=1,
            at=transition_at,
        )
        assert transitioned.status is EngagementStatus.ACTIVE
        assert transitioned.updated_at == transition_at
        assert transitioned.version == 2
        unit.commit()
    loaded = fetch(factory, engagement.id)
    assert loaded == transitioned


def test_authorized_assessment_transition_keeps_domain_guard(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    workspace = active_workspace(factory)
    engagement = persist(
        factory, Engagement.create(workspace.id, "Assessment", EngagementKind.AUTHORIZED_ASSESSMENT)
    )
    with SQLiteUnitOfWork(factory) as unit:
        with pytest.raises(CyberOSError) as captured:
            SQLiteEngagementRepository(unit).transition(
                engagement.id,
                EngagementStatus.ACTIVE,
                expected_version=1,
            )
        assert captured.value.code == ErrorCode.ENGAGEMENT_AUTHORIZATION_REQUIRED
        unit.rollback()


def test_stale_version_rejects_transition_without_modification(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    workspace = active_workspace(factory)
    engagement = persist(
        factory, Engagement.create(workspace.id, "Concurrent", EngagementKind.LEARNING)
    )
    with SQLiteUnitOfWork(factory) as unit:
        SQLiteEngagementRepository(unit).transition(
            engagement.id,
            EngagementStatus.ACTIVE,
            expected_version=1,
        )
        unit.commit()
    with SQLiteUnitOfWork(factory) as unit:
        with pytest.raises(CyberOSError) as captured:
            SQLiteEngagementRepository(unit).transition(
                engagement.id,
                EngagementStatus.PAUSED,
                expected_version=1,
            )
        assert captured.value.code == ErrorCode.CONCURRENCY_CONFLICT
        unit.rollback()
    loaded = fetch(factory, engagement.id)
    assert loaded is not None
    assert loaded.status is EngagementStatus.ACTIVE
    assert loaded.version == 2


def test_archive_persists_archived_at_and_version(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    workspace = active_workspace(factory)
    engagement = persist(
        factory, Engagement.create(workspace.id, "Archive", EngagementKind.LEARNING)
    )
    with SQLiteUnitOfWork(factory) as unit:
        archived = SQLiteEngagementRepository(unit).archive(engagement.id, expected_version=1)
        assert archived.status is EngagementStatus.ARCHIVED
        assert archived.archived_at == archived.updated_at
        assert archived.version == 2
        unit.commit()
    loaded = fetch(factory, engagement.id)
    assert loaded is not None
    assert loaded.status is EngagementStatus.ARCHIVED
    assert loaded.archived_at is not None
    assert loaded.version == 2


def test_exception_inside_unit_of_work_rolls_back_engagement(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    workspace = active_workspace(factory)
    engagement = Engagement.create(workspace.id, "Rollback", EngagementKind.LEARNING)
    with pytest.raises(RuntimeError, match="force rollback"):
        with SQLiteUnitOfWork(factory) as unit:
            SQLiteEngagementRepository(unit).add(engagement)
            raise RuntimeError("force rollback")
    assert fetch(factory, engagement.id) is None


def test_repository_returns_domain_objects_not_sqlite_rows(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    workspace = active_workspace(factory)
    engagement = persist(
        factory, Engagement.create(workspace.id, "No Row Leak", EngagementKind.LEARNING)
    )
    with SQLiteUnitOfWork(factory) as unit:
        repository = SQLiteEngagementRepository(unit)
        loaded = repository.get(engagement.id)
        listed = repository.list_by_workspace(workspace.id)
        unit.rollback()
    assert isinstance(loaded, Engagement)
    assert all(isinstance(item, Engagement) for item in listed)
    assert not isinstance(loaded, tuple)
