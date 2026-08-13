from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.engagement.model import Engagement, EngagementKind, EngagementStatus


def make_draft(kind: EngagementKind = EngagementKind.LEARNING) -> Engagement:
    return Engagement.create(uuid4(), "  API Security Lab  ", kind, "  practice  ")


def test_create_normalizes_fields_and_generates_uuid4() -> None:
    now = datetime(2026, 8, 13, 12, tzinfo=UTC)
    workspace_id = uuid4()
    engagement = Engagement.create(
        workspace_id,
        "  Lab  ",
        EngagementKind.LEARNING,
        "  Description  ",
        now=now,
    )
    assert isinstance(engagement.id, UUID)
    assert engagement.id.version == 4
    assert engagement.workspace_id == workspace_id
    assert engagement.name == "Lab"
    assert engagement.description == "Description"
    assert engagement.status is EngagementStatus.DRAFT
    assert engagement.created_at == now
    assert engagement.updated_at == now
    assert engagement.version == 1


@pytest.mark.parametrize("name", ["", "   ", "x" * 161])
def test_invalid_name_is_typed_domain_error(name: str) -> None:
    with pytest.raises(CyberOSError) as captured:
        Engagement.create(uuid4(), name, EngagementKind.LEARNING)
    assert captured.value.code == ErrorCode.DOMAIN_VALIDATION_FAILED


def test_authorization_reference_is_normalized_and_bounded() -> None:
    engagement = Engagement.create(
        uuid4(),
        "Assessment",
        EngagementKind.AUTHORIZED_ASSESSMENT,
        authorization_reference="  ticket-123  ",
    )
    assert engagement.authorization_reference == "ticket-123"
    with pytest.raises(CyberOSError) as captured:
        Engagement.create(
            uuid4(), "Assessment", EngagementKind.LEARNING, authorization_reference="x" * 1001
        )
    assert captured.value.code == ErrorCode.DOMAIN_VALIDATION_FAILED


def test_uuid4_workspace_and_engagement_ids_are_required() -> None:
    with pytest.raises(ValidationError):
        Engagement(
            id="00000000-0000-1000-8000-000000000000",
            workspace_id=uuid4(),
            name="x",
            kind="learning",
        )
    with pytest.raises(ValidationError):
        Engagement(
            id=uuid4(),
            workspace_id="00000000-0000-1000-8000-000000000000",
            name="x",
            kind="learning",
        )


def test_end_at_cannot_precede_start_at() -> None:
    start = datetime(2026, 8, 13, 12, tzinfo=UTC)
    with pytest.raises(CyberOSError) as captured:
        Engagement.create(
            uuid4(), "Lab", EngagementKind.LEARNING, start_at=start, now=start
        ).transition(EngagementStatus.ACTIVE).transition(
            EngagementStatus.COMPLETED, end_at=start - timedelta(minutes=1)
        )
    assert captured.value.code == ErrorCode.DOMAIN_VALIDATION_FAILED


def test_learning_engagement_can_follow_draft_active_paused_active() -> None:
    engagement = make_draft()
    active = engagement.transition(EngagementStatus.ACTIVE)
    paused = active.transition(EngagementStatus.PAUSED)
    resumed = paused.transition(EngagementStatus.ACTIVE)
    assert active.version == 2
    assert paused.version == 3
    assert resumed.status is EngagementStatus.ACTIVE
    assert resumed.version == 4
    assert engagement.status is EngagementStatus.DRAFT


def test_completion_requires_end_at_and_then_sets_it() -> None:
    active = make_draft().transition(EngagementStatus.ACTIVE)
    with pytest.raises(CyberOSError) as captured:
        active.transition(EngagementStatus.COMPLETED)
    assert captured.value.code == ErrorCode.ENGAGEMENT_COMPLETION_REQUIRES_END_AT
    end_at = datetime(2026, 8, 13, 13, tzinfo=UTC)
    completed = active.transition(EngagementStatus.COMPLETED, end_at=end_at)
    assert completed.status is EngagementStatus.COMPLETED
    assert completed.end_at == end_at
    assert completed.version == 3


def test_authorized_assessment_requires_reference_before_activation() -> None:
    assessment = make_draft(EngagementKind.AUTHORIZED_ASSESSMENT)
    with pytest.raises(CyberOSError) as captured:
        assessment.transition(EngagementStatus.ACTIVE)
    assert captured.value.code == ErrorCode.ENGAGEMENT_AUTHORIZATION_REQUIRED
    authorized = Engagement.create(
        assessment.workspace_id,
        assessment.name,
        assessment.kind,
        authorization_reference="approval-42",
    )
    assert authorized.transition(EngagementStatus.ACTIVE).status is EngagementStatus.ACTIVE


def test_forbidden_transition_is_rejected() -> None:
    with pytest.raises(CyberOSError) as captured:
        make_draft().transition(EngagementStatus.PAUSED)
    assert captured.value.code == ErrorCode.ENGAGEMENT_INVALID_TRANSITION


def test_archive_is_allowed_from_draft_and_is_terminal() -> None:
    created = datetime(2026, 8, 13, 12, tzinfo=UTC)
    archived = Engagement.create(uuid4(), "Lab", EngagementKind.LEARNING, now=created).archive(
        at=datetime(2026, 8, 13, 14, tzinfo=UTC)
    )
    assert archived.status is EngagementStatus.ARCHIVED
    assert archived.archived_at == archived.updated_at
    assert archived.version == 2
    with pytest.raises(CyberOSError) as captured:
        archived.transition(EngagementStatus.ACTIVE)
    assert captured.value.code == ErrorCode.ENGAGEMENT_ALREADY_ARCHIVED


def test_completed_can_only_be_archived() -> None:
    end_at = datetime(2026, 8, 13, 13, tzinfo=UTC)
    completed = (
        make_draft()
        .transition(EngagementStatus.ACTIVE)
        .transition(EngagementStatus.COMPLETED, end_at=end_at)
    )
    archived = completed.archive()
    assert archived.status is EngagementStatus.ARCHIVED
    with pytest.raises(CyberOSError) as captured:
        completed.transition(EngagementStatus.ACTIVE)
    assert captured.value.code == ErrorCode.ENGAGEMENT_INVALID_TRANSITION


def test_model_is_immutable() -> None:
    engagement = make_draft()
    with pytest.raises(ValidationError):
        engagement.name = "Changed"  # type: ignore[misc]
