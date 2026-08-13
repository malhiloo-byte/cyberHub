from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from cyberos.application.services.engagement import EngagementService
from cyberos.application.services.workspace import WorkspaceService
from cyberos.config.models import DatabaseSettings
from cyberos.core.context import OperationContext
from cyberos.core.errors import ErrorCode
from cyberos.domain.engagement.model import EngagementKind, EngagementStatus
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.migrations.runner import MigrationRunner

MIGRATIONS_DIR = Path(__file__).parents[2] / "src/cyberos/persistence/migrations/versions"


def factory_for(tmp_path: Path) -> SQLiteConnectionFactory:
    factory = SQLiteConnectionFactory(DatabaseSettings(path=tmp_path / "cyberos.sqlite3"))
    MigrationRunner(factory, MIGRATIONS_DIR).run()
    return factory


def test_workspace_service_create_list_show_archive(tmp_path: Path) -> None:
    service = WorkspaceService(factory_for(tmp_path))
    context = OperationContext()
    created = service.create("Service Workspace", "service", context=context)
    assert created.ok is True
    assert created.data is not None
    assert created.meta.correlation_id == str(context.correlation_id)
    workspace = created.data
    listed = service.list()
    assert listed.ok is True
    assert [item.id for item in listed.data or []] == [workspace.id]
    shown = service.show(workspace.id)
    assert shown.ok is True
    assert shown.data == workspace
    archived = service.archive(workspace.id, expected_version=1)
    assert archived.ok is True
    assert archived.data is not None
    assert archived.data.status.value == "archived"
    assert archived.data.version == 2


def test_engagement_service_authorization_guard_is_service_logic(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    workspace = WorkspaceService(factory).create("Service Workspace").data
    assert workspace is not None
    service = EngagementService(factory)
    created = service.create(workspace.id, "Assessment", EngagementKind.AUTHORIZED_ASSESSMENT)
    assert created.ok is True
    assert created.data is not None
    missing = service.transition(created.data.id, EngagementStatus.ACTIVE, expected_version=1)
    assert missing.ok is False
    assert missing.error is not None
    assert missing.error.code == ErrorCode.ENGAGEMENT_AUTHORIZATION_REQUIRED.value


def test_engagement_service_completed_sets_end_at(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    workspace = WorkspaceService(factory).create("Service Workspace").data
    assert workspace is not None
    service = EngagementService(factory)
    created = service.create(
        workspace.id,
        "Learning",
        EngagementKind.LEARNING,
        context=OperationContext(),
    )
    assert created.ok is True
    assert created.data is not None
    at = created.data.created_at + timedelta(hours=1)
    active = service.transition(created.data.id, EngagementStatus.ACTIVE, expected_version=1, at=at)
    assert active.ok is True
    completed = service.transition(
        created.data.id,
        EngagementStatus.COMPLETED,
        expected_version=2,
        at=at + timedelta(hours=1),
    )
    assert completed.ok is True
    assert completed.data is not None
    assert completed.data.end_at == at + timedelta(hours=1)
    assert completed.data.version == 3
