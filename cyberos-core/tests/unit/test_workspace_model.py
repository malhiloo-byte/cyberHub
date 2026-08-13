from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.workspace.model import Workspace, WorkspaceStatus


def test_create_workspace_generates_uuid4_and_utc_timestamps() -> None:
    now = datetime(2026, 8, 13, 12, tzinfo=UTC)
    workspace = Workspace.create("  Web Pentest Learning  ", "  Practice track  ", now=now)
    assert isinstance(workspace.id, UUID)
    assert workspace.id.version == 4
    assert workspace.name == "Web Pentest Learning"
    assert workspace.description == "Practice track"
    assert workspace.status is WorkspaceStatus.ACTIVE
    assert workspace.created_at == now
    assert workspace.updated_at == now
    assert workspace.archived_at is None
    assert workspace.version == 1


def test_create_workspace_accepts_explicit_uuid4() -> None:
    workspace_id = uuid4()
    workspace = Workspace.create("Workspace", workspace_id=workspace_id)
    assert workspace.id == workspace_id


@pytest.mark.parametrize("name", ["", "   ", "x" * 121])
def test_invalid_workspace_name_raises_typed_domain_error(name: str) -> None:
    with pytest.raises(CyberOSError) as captured:
        Workspace.create(name)
    assert captured.value.code == ErrorCode.DOMAIN_VALIDATION_FAILED


def test_description_limit_is_enforced() -> None:
    with pytest.raises(CyberOSError) as captured:
        Workspace.create("Workspace", "x" * 4001)
    assert captured.value.code == ErrorCode.DOMAIN_VALIDATION_FAILED


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError, match="Naive datetime"):
        Workspace.create("Workspace", now=datetime(2026, 1, 1))


def test_non_uuid4_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Workspace(id="00000000-0000-1000-8000-000000000000", name="Workspace")


def test_updated_at_cannot_precede_created_at() -> None:
    created = datetime(2026, 1, 2, tzinfo=UTC)
    earlier = created - timedelta(seconds=1)
    with pytest.raises(ValidationError, match="updated_at"):
        Workspace(name="Workspace", created_at=created, updated_at=earlier)


def test_archive_sets_status_timestamp_and_increments_version() -> None:
    created = datetime(2026, 8, 13, 12, tzinfo=UTC)
    archived_at = created + timedelta(hours=2)
    workspace = Workspace.create("Workspace", now=created)
    archived = workspace.archive(archived_at=archived_at)
    assert archived.status is WorkspaceStatus.ARCHIVED
    assert archived.archived_at == archived_at
    assert archived.updated_at == archived_at
    assert archived.version == 2
    assert workspace.status is WorkspaceStatus.ACTIVE


def test_archiving_twice_is_rejected() -> None:
    archived = Workspace.create("Workspace").archive()
    with pytest.raises(CyberOSError) as captured:
        archived.archive()
    assert captured.value.code == ErrorCode.WORKSPACE_ALREADY_ARCHIVED


def test_model_is_immutable() -> None:
    workspace = Workspace.create("Workspace")
    with pytest.raises(ValidationError):
        workspace.name = "Changed"  # type: ignore[misc]


def test_active_and_archived_invariants_are_enforced() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValidationError, match="active workspace"):
        Workspace(name="Workspace", archived_at=timestamp)
    with pytest.raises(ValidationError, match="archived workspace"):
        Workspace(name="Workspace", status=WorkspaceStatus.ARCHIVED)
