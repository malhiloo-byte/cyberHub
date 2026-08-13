"""Application DTOs and service for fail-closed Scope execution authorization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.time import ensure_utc, utc_now
from cyberos.domain.scope.matcher import MatchDecision, ScopeMatcher
from cyberos.domain.scope.model import Scope
from cyberos.domain.scope.primitives import ScopeId, ScopeStatus
from cyberos.domain.target.primitives import TargetId, TargetKind, TargetRule
from cyberos.persistence.scope_repository import SQLiteScopeRepository
from cyberos.persistence.target_repository import SQLiteTargetRepository
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork

if TYPE_CHECKING:
    from cyberos.persistence.connection import SQLiteConnectionFactory


@dataclass(frozen=True, slots=True)
class TargetCandidate:
    raw_value: str
    kind: TargetKind

    def __post_init__(self) -> None:
        if not isinstance(self.raw_value, str) or not self.raw_value.strip():
            raise CyberOSError(
                ErrorCode.TARGET_VALUE_INVALID,
                "Candidate raw_value must be non-empty text.",
            )
        if not isinstance(self.kind, TargetKind):
            try:
                object.__setattr__(self, "kind", TargetKind(self.kind))
            except (TypeError, ValueError) as exc:
                raise CyberOSError(
                    ErrorCode.TARGET_KIND_INVALID,
                    "Candidate kind is not supported.",
                ) from exc


@dataclass(frozen=True, slots=True)
class ScopeEvaluationResult:
    scope_id: ScopeId
    candidate: TargetCandidate
    decision: MatchDecision
    matched_target_id: TargetId | None
    matching_rule: TargetRule | None
    reason: str
    evaluated_at: datetime
    expires_at: datetime | None
    scope_status: ScopeStatus
    scope_version: int


@dataclass(frozen=True, slots=True)
class ExecutionAuthorization:
    scope_id: ScopeId
    candidate: TargetCandidate
    authorized_at: datetime
    expires_at: datetime | None
    matched_target_id: TargetId
    matching_rule: TargetRule
    reason: str
    scope_version: int


class ScopeValidationService:
    """Read-only application boundary that authorizes execution or fails closed."""

    def __init__(self, factory: SQLiteConnectionFactory) -> None:
        self.factory = factory

    def evaluate_candidate(
        self,
        scope_id: ScopeId,
        candidate: TargetCandidate,
        *,
        evaluated_at: datetime | None = None,
    ) -> ScopeEvaluationResult:
        timestamp = ensure_utc(evaluated_at) if evaluated_at is not None else utc_now()
        scope = self._load_scope_with_targets(scope_id)
        match = ScopeMatcher.match(
            scope,
            candidate.raw_value,
            candidate.kind,
            evaluated_at=timestamp,
        )
        return ScopeEvaluationResult(
            scope_id=scope.id,
            candidate=candidate,
            decision=match.decision,
            matched_target_id=match.matched_target_id,
            matching_rule=match.matching_rule,
            reason=match.reason,
            evaluated_at=timestamp,
            expires_at=scope.expires_at,
            scope_status=scope.status,
            scope_version=scope.version,
        )

    def authorize_execution(
        self,
        scope_id: ScopeId,
        candidate: TargetCandidate,
        *,
        evaluated_at: datetime | None = None,
    ) -> ExecutionAuthorization:
        result = self.evaluate_candidate(scope_id, candidate, evaluated_at=evaluated_at)
        if result.decision is not MatchDecision.INCLUDED:
            raise self._authorization_error(result)
        if result.matched_target_id is None or result.matching_rule is None:
            raise CyberOSError(
                ErrorCode.TARGET_OUT_OF_SCOPE,
                "Execution authorization requires a matched Include Target.",
            )
        return ExecutionAuthorization(
            scope_id=result.scope_id,
            candidate=result.candidate,
            authorized_at=result.evaluated_at,
            expires_at=result.expires_at,
            matched_target_id=result.matched_target_id,
            matching_rule=result.matching_rule,
            reason="execution_authorized_by_scope",
            scope_version=result.scope_version,
        )

    def _load_scope_with_targets(self, scope_id: ScopeId) -> Scope:
        with SQLiteUnitOfWork(self.factory) as unit:
            scope = SQLiteScopeRepository(unit).get(scope_id)
            if scope is None:
                unit.rollback()
                raise CyberOSError(ErrorCode.SCOPE_NOT_FOUND, "The Scope does not exist.")
            targets = tuple(SQLiteTargetRepository(unit).list_by_scope(scope_id))
            unit.rollback()
        values = scope.model_dump()
        values["targets"] = targets
        try:
            return Scope.model_validate(values)
        except Exception as exc:
            raise CyberOSError(
                ErrorCode.PERSISTENCE_MAPPING_FAILED,
                "Stored Scope and Targets failed application validation.",
            ) from exc

    @staticmethod
    def _authorization_error(result: ScopeEvaluationResult) -> CyberOSError:
        if result.reason == "scope_not_authorized":
            if result.scope_status is ScopeStatus.ARCHIVED:
                return CyberOSError(
                    ErrorCode.SCOPE_ARCHIVED,
                    "Archived Scope cannot authorize execution.",
                )
            return CyberOSError(
                ErrorCode.SCOPE_NOT_AUTHORIZED,
                "Scope is not authorized for execution.",
            )
        if result.reason == "scope_expired":
            return CyberOSError(ErrorCode.SCOPE_EXPIRED, "Scope authorization has expired.")
        if result.decision is MatchDecision.EXCLUDED:
            return CyberOSError(
                ErrorCode.TARGET_EXCLUDED,
                "Target is explicitly excluded by Scope policy.",
            )
        return CyberOSError(
            ErrorCode.TARGET_OUT_OF_SCOPE,
            "Target is outside the authorized Scope.",
        )
