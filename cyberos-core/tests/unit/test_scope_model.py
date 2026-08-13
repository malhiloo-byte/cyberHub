from datetime import UTC, datetime, timedelta

import pytest

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.ids import new_id
from cyberos.domain.scope.model import Scope
from cyberos.domain.scope.primitives import ScopeStatus
from cyberos.domain.target.model import Target
from cyberos.domain.target.primitives import TargetKind, TargetRule

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def make_scope() -> Scope:
    return Scope.create(new_id(), "API Scope", now=NOW)


def make_target(scope: Scope, value: str = "api.example.com") -> Target:
    return Target.create(scope.id, TargetRule.INCLUDE, TargetKind.FQDN, value, now=NOW)


def test_scope_lifecycle_is_explicit_and_versioned() -> None:
    scope = make_scope()
    validated = scope.mark_validated(at=NOW + timedelta(minutes=1))
    authorized = validated.authorize(
        "approval-1",
        at=NOW + timedelta(minutes=2),
        expires_at=NOW + timedelta(days=1),
    )
    archived = authorized.archive(at=NOW + timedelta(minutes=3))

    assert scope.status is ScopeStatus.DRAFT
    assert validated.status is ScopeStatus.VALIDATED
    assert validated.validated_at == NOW + timedelta(minutes=1)
    assert authorized.status is ScopeStatus.AUTHORIZED
    assert authorized.authorization_reference == "approval-1"
    assert authorized.authorized_at == NOW + timedelta(minutes=2)
    assert archived.status is ScopeStatus.ARCHIVED
    assert archived.archived_at == NOW + timedelta(minutes=3)
    assert archived.version == 4


def test_scope_rejects_authorization_without_reference() -> None:
    with pytest.raises(CyberOSError) as captured:
        make_scope().mark_validated(at=NOW).authorize("   ", at=NOW + timedelta(minutes=1))

    assert captured.value.code is ErrorCode.SCOPE_AUTHORIZATION_REQUIRED


def test_scope_requires_explicit_validation_before_authorization() -> None:
    with pytest.raises(CyberOSError) as captured:
        make_scope().authorize("approval-1", at=NOW)

    assert captured.value.code is ErrorCode.INVALID_SCOPE_TRANSITION


def test_scope_rejects_direct_authorized_to_validated_transition() -> None:
    authorized = (
        make_scope().mark_validated(at=NOW).authorize("approval-1", at=NOW + timedelta(minutes=1))
    )

    with pytest.raises(CyberOSError) as captured:
        authorized.mark_validated(at=NOW + timedelta(minutes=2))

    assert captured.value.code is ErrorCode.INVALID_SCOPE_TRANSITION


def test_scope_can_explicitly_return_to_draft_before_target_mutation() -> None:
    authorized = (
        make_scope().mark_validated(at=NOW).authorize("approval-1", at=NOW + timedelta(minutes=1))
    )

    draft = authorized.return_to_draft(at=NOW + timedelta(minutes=2))
    updated = draft.add_target(make_target(draft))

    assert draft.status is ScopeStatus.DRAFT
    assert draft.authorization_reference is None
    assert updated.status is ScopeStatus.DRAFT
    assert len(updated.targets) == 1


def test_authorized_scope_rejects_target_add_update_and_archive() -> None:
    scope = make_scope()
    target = make_target(scope)
    authorized = scope.add_target(target).mark_validated(at=NOW).authorize("approval-1", at=NOW)

    operations = [
        lambda: authorized.add_target(make_target(authorized, "admin.example.com")),
        lambda: authorized.update_target(target.id, "api2.example.com", at=NOW),
        lambda: authorized.archive_target(target.id, at=NOW),
    ]
    for operation in operations:
        with pytest.raises(CyberOSError) as captured:
            operation()
        assert captured.value.code is ErrorCode.AUTHORIZED_SCOPE_IMMUTABLE


def test_archived_scope_rejects_changes_and_target_mutations() -> None:
    archived = make_scope().archive(at=NOW)

    with pytest.raises(CyberOSError) as captured:
        archived.return_to_draft(at=NOW + timedelta(minutes=1))
    assert captured.value.code is ErrorCode.SCOPE_ARCHIVED

    with pytest.raises(CyberOSError) as target_error:
        archived.add_target(make_target(archived))
    assert target_error.value.code is ErrorCode.SCOPE_ARCHIVED


def test_scope_rejects_target_from_another_scope() -> None:
    scope = make_scope()
    foreign = make_target(make_scope())

    with pytest.raises(CyberOSError) as captured:
        scope.add_target(foreign)

    assert captured.value.code is ErrorCode.TARGET_SCOPE_MISMATCH


def test_scope_target_update_and_archive_are_immutable_and_versioned() -> None:
    scope = make_scope()
    target = make_target(scope)
    with_target = scope.add_target(target)
    updated = with_target.update_target(target.id, "new.example.com", at=NOW + timedelta(minutes=1))
    archived = updated.archive_target(target.id, at=NOW + timedelta(minutes=2))

    assert with_target.version == 2
    assert updated.version == 3
    assert archived.version == 4
    assert with_target.targets[0].value == "api.example.com"
    assert updated.targets[0].value == "new.example.com"
    assert archived.targets[0].status == "archived"
