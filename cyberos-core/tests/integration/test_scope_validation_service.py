from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cyberos.application.scope_validation import (
    ScopeValidationService,
    TargetCandidate,
)
from cyberos.config.models import DatabaseSettings
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.ids import new_id
from cyberos.domain.engagement.model import Engagement
from cyberos.domain.scope.matcher import MatchDecision
from cyberos.domain.scope.model import Scope
from cyberos.domain.target.model import Target
from cyberos.domain.target.primitives import TargetKind, TargetRule
from cyberos.domain.workspace.model import Workspace
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.engagement_repository import SQLiteEngagementRepository
from cyberos.persistence.migrations.runner import MigrationRunner
from cyberos.persistence.scope_repository import SQLiteScopeRepository
from cyberos.persistence.target_repository import SQLiteTargetRepository
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork
from cyberos.persistence.workspace_repository import SQLiteWorkspaceRepository

MIGRATIONS_DIR = Path(__file__).parents[2] / "src/cyberos/persistence/migrations/versions"
NOW = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)


def factory_for(tmp_path: Path) -> SQLiteConnectionFactory:
    factory = SQLiteConnectionFactory(DatabaseSettings(path=tmp_path / "cyberos.sqlite3"))
    MigrationRunner(factory, MIGRATIONS_DIR).run()
    return factory


def setup_scope(
    factory: SQLiteConnectionFactory,
    *,
    expires_at: datetime | None = None,
    include_value: str = "api.example.com",
    include_kind: TargetKind = TargetKind.FQDN,
    include_rule: TargetRule = TargetRule.INCLUDE,
    add_exclude: bool = False,
) -> tuple[Scope, Target]:
    workspace = Workspace.create("Validation Workspace", now=NOW)
    engagement = Engagement.create(workspace.id, "Validation Engagement", "learning", now=NOW)
    scope = Scope.create(engagement.id, "Validation Scope", now=NOW)
    include = Target.create(scope.id, include_rule, include_kind, include_value, now=NOW)
    targets = [include]
    if add_exclude:
        targets.append(
            Target.create(
                scope.id,
                TargetRule.EXCLUDE,
                TargetKind.FQDN,
                "admin.example.com",
                now=NOW,
            )
        )
    with SQLiteUnitOfWork(factory) as unit:
        SQLiteWorkspaceRepository(unit).add(workspace)
        SQLiteEngagementRepository(unit).add(engagement)
        SQLiteScopeRepository(unit).add(scope)
        for target in targets:
            SQLiteTargetRepository(unit).add(target)
        authorized = scope.add_target(include)
        if add_exclude:
            authorized = authorized.add_target(targets[1])
        authorized = authorized.mark_validated(at=NOW).authorize(
            "service-approval",
            at=NOW,
            expires_at=expires_at,
        )
        SQLiteScopeRepository(unit).update(authorized, expected_version=1)
        unit.commit()
    return authorized, include


def test_authorized_included_candidate_returns_auditable_execution_authorization(
    tmp_path: Path,
) -> None:
    factory = factory_for(tmp_path)
    scope, target = setup_scope(factory)
    service = ScopeValidationService(factory)
    candidate = TargetCandidate("API.EXAMPLE.COM.", TargetKind.FQDN)

    evaluation = service.evaluate_candidate(scope.id, candidate, evaluated_at=NOW)
    authorization = service.authorize_execution(scope.id, candidate, evaluated_at=NOW)

    assert evaluation.decision is MatchDecision.INCLUDED
    assert evaluation.scope_id == scope.id
    assert evaluation.matched_target_id == target.id
    assert evaluation.matching_rule is TargetRule.INCLUDE
    assert evaluation.reason == "included_by_authorized_rule"
    assert evaluation.evaluated_at == NOW
    assert authorization.scope_id == scope.id
    assert authorization.matched_target_id == target.id
    assert authorization.matching_rule is TargetRule.INCLUDE
    assert authorization.authorized_at == NOW
    assert authorization.reason == "execution_authorized_by_scope"


def test_draft_scope_is_evaluated_and_authorization_is_rejected(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    workspace = Workspace.create("Draft Workspace", now=NOW)
    engagement = Engagement.create(workspace.id, "Draft Engagement", "learning", now=NOW)
    scope = Scope.create(engagement.id, "Draft Scope", now=NOW)
    target = Target.create(
        scope.id,
        TargetRule.INCLUDE,
        TargetKind.FQDN,
        "draft.example.com",
        now=NOW,
    )
    with SQLiteUnitOfWork(factory) as unit:
        SQLiteWorkspaceRepository(unit).add(workspace)
        SQLiteEngagementRepository(unit).add(engagement)
        SQLiteScopeRepository(unit).add(scope)
        SQLiteTargetRepository(unit).add(target)
        unit.commit()
    service = ScopeValidationService(factory)
    candidate = TargetCandidate("draft.example.com", TargetKind.FQDN)

    evaluation = service.evaluate_candidate(scope.id, candidate, evaluated_at=NOW)
    with pytest.raises(CyberOSError) as captured:
        service.authorize_execution(scope.id, candidate, evaluated_at=NOW)

    assert evaluation.decision is MatchDecision.DENIED_OUT_OF_SCOPE
    assert evaluation.reason == "scope_not_authorized"
    assert captured.value.code is ErrorCode.SCOPE_NOT_AUTHORIZED


def test_archived_scope_is_rejected_with_archived_reason(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    workspace = Workspace.create("Archived Workspace", now=NOW)
    engagement = Engagement.create(workspace.id, "Archived Engagement", "learning", now=NOW)
    scope = Scope.create(engagement.id, "Archived Scope", now=NOW)
    with SQLiteUnitOfWork(factory) as unit:
        SQLiteWorkspaceRepository(unit).add(workspace)
        SQLiteEngagementRepository(unit).add(engagement)
        SQLiteScopeRepository(unit).add(scope)
        SQLiteScopeRepository(unit).archive(scope.id, expected_version=1)
        unit.commit()
    service = ScopeValidationService(factory)
    candidate = TargetCandidate("archived.example.com", TargetKind.FQDN)

    with pytest.raises(CyberOSError) as captured:
        service.authorize_execution(scope.id, candidate, evaluated_at=NOW)

    assert captured.value.code is ErrorCode.SCOPE_ARCHIVED


def test_expired_scope_is_rejected_before_execution_authorization(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    scope, _ = setup_scope(factory, expires_at=NOW + timedelta(minutes=1))
    service = ScopeValidationService(factory)
    candidate = TargetCandidate("api.example.com", TargetKind.FQDN)

    evaluation = service.evaluate_candidate(
        scope.id,
        candidate,
        evaluated_at=NOW + timedelta(minutes=2),
    )
    with pytest.raises(CyberOSError) as captured:
        service.authorize_execution(
            scope.id,
            candidate,
            evaluated_at=NOW + timedelta(minutes=2),
        )

    assert evaluation.reason == "scope_expired"
    assert captured.value.code is ErrorCode.SCOPE_EXPIRED


def test_excluded_candidate_is_never_authorized(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    scope, _ = setup_scope(factory, add_exclude=True, include_value="admin.example.com")
    service = ScopeValidationService(factory)
    candidate = TargetCandidate("admin.example.com", TargetKind.FQDN)

    evaluation = service.evaluate_candidate(scope.id, candidate, evaluated_at=NOW)
    with pytest.raises(CyberOSError) as captured:
        service.authorize_execution(scope.id, candidate, evaluated_at=NOW)

    assert evaluation.decision is MatchDecision.EXCLUDED
    assert evaluation.reason == "excluded_by_explicit_rule"
    assert captured.value.code is ErrorCode.TARGET_EXCLUDED


def test_candidate_dto_is_immutable_and_rejects_empty_or_unknown_values() -> None:
    candidate = TargetCandidate("example.com", TargetKind.FQDN)
    with pytest.raises((AttributeError, TypeError)):
        candidate.raw_value = "changed"  # type: ignore[misc]
    with pytest.raises(CyberOSError) as empty:
        TargetCandidate("   ", TargetKind.FQDN)
    assert empty.value.code is ErrorCode.TARGET_VALUE_INVALID
    with pytest.raises(CyberOSError) as unknown:
        TargetCandidate("example.com", "unknown")  # type: ignore[arg-type]
    assert unknown.value.code is ErrorCode.TARGET_KIND_INVALID


def test_missing_scope_is_rejected_without_sql_leakage(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    service = ScopeValidationService(factory)
    with pytest.raises(CyberOSError) as captured:
        service.evaluate_candidate(
            new_id(), TargetCandidate("missing.example.com", TargetKind.FQDN)
        )
    assert captured.value.code is ErrorCode.SCOPE_NOT_FOUND
    assert "sqlite" not in captured.value.message.lower()
    assert "select" not in captured.value.message.lower()
