from datetime import UTC, datetime, timedelta

import pytest

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.scope.primitives import new_scope_id
from cyberos.domain.target.model import Target
from cyberos.domain.target.primitives import TargetKind, TargetRule

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_target_create_canonicalizes_and_preserves_utc_invariants() -> None:
    target = Target.create(
        new_scope_id(),
        TargetRule.INCLUDE,
        TargetKind.FQDN,
        " EXAMPLE.COM. ",
        now=NOW,
    )

    assert target.value == "example.com"
    assert target.status == "active"
    assert target.version == 1
    assert target.created_at == NOW
    assert target.updated_at == NOW
    assert target.created_at.tzinfo is UTC


def test_target_archive_updates_timestamp_and_version() -> None:
    target = Target.create(
        new_scope_id(),
        TargetRule.EXCLUDE,
        TargetKind.IPV4,
        "192.168.1.10",
        now=NOW,
    )

    archived = target.archive(at=NOW + timedelta(hours=1))

    assert archived.status == "archived"
    assert archived.archived_at == NOW + timedelta(hours=1)
    assert archived.updated_at == archived.archived_at
    assert archived.version == 2


def test_archived_target_cannot_be_modified_or_archived_again() -> None:
    archived = Target.create(
        new_scope_id(), TargetRule.INCLUDE, TargetKind.FQDN, "example.com", now=NOW
    ).archive(at=NOW + timedelta(hours=1))

    with pytest.raises(CyberOSError) as update_error:
        archived.with_value("api.example.com", now=NOW + timedelta(hours=2))
    assert update_error.value.code is ErrorCode.TARGET_ALREADY_ARCHIVED

    with pytest.raises(CyberOSError) as archive_error:
        archived.archive(at=NOW + timedelta(hours=2))
    assert archive_error.value.code is ErrorCode.TARGET_ALREADY_ARCHIVED


def test_target_update_is_immutable_and_increments_version() -> None:
    target = Target.create(
        new_scope_id(), TargetRule.INCLUDE, TargetKind.URL, "https://example.com", now=NOW
    )

    updated = target.with_value("https://example.com/api", now=NOW + timedelta(minutes=1))

    assert target.value == "https://example.com/"
    assert updated.value == "https://example.com/api"
    assert updated.version == 2
    assert updated.id == target.id
    assert updated.created_at == target.created_at
