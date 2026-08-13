"""Application services for Scope lifecycle operations exposed by the CLI."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from cyberos.application.services.common import execute_service
from cyberos.core.context import OperationContext
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.result import OperationResult
from cyberos.core.time import utc_now
from cyberos.domain.engagement.primitives import EngagementId
from cyberos.domain.scope.model import Scope
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.model import Target
from cyberos.domain.target.primitives import TargetKind, TargetRule
from cyberos.persistence.scope_repository import SQLiteScopeRepository
from cyberos.persistence.target_repository import SQLiteTargetRepository
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork

if TYPE_CHECKING:
    from cyberos.persistence.connection import SQLiteConnectionFactory


class ScopeService:
    """Orchestrate Scope creation and authorization without execution side effects."""

    def __init__(self, factory: SQLiteConnectionFactory) -> None:
        self.factory = factory

    def create(
        self,
        engagement_id: EngagementId,
        name: str,
        description: str = "",
        *,
        context: OperationContext | None = None,
    ) -> OperationResult[Scope]:
        return execute_service(
            lambda: self._create(engagement_id, name, description),
            context=context,
        )

    def authorize(
        self,
        scope_id: ScopeId,
        authorization_reference: str,
        expires_at: datetime | None = None,
        *,
        context: OperationContext | None = None,
    ) -> OperationResult[Scope]:
        return execute_service(
            lambda: self._authorize(scope_id, authorization_reference, expires_at),
            context=context,
        )

    def _create(self, engagement_id: EngagementId, name: str, description: str) -> Scope:
        scope = Scope.create(engagement_id, name, description)
        with SQLiteUnitOfWork(self.factory) as unit:
            saved = SQLiteScopeRepository(unit).add(scope)
            unit.commit()
            return saved

    def _authorize(
        self,
        scope_id: ScopeId,
        authorization_reference: str,
        expires_at: datetime | None,
    ) -> Scope:
        with SQLiteUnitOfWork(self.factory) as unit:
            current = SQLiteScopeRepository(unit).get(scope_id)
            unit.rollback()
        if current is None:
            raise CyberOSError(ErrorCode.SCOPE_NOT_FOUND, "The Scope does not exist.")
        timestamp = utc_now()
        validated = current.mark_validated(at=timestamp)
        authorized = validated.authorize(
            authorization_reference,
            at=timestamp,
            expires_at=expires_at,
        )
        with SQLiteUnitOfWork(self.factory) as unit:
            saved = SQLiteScopeRepository(unit).update(authorized, expected_version=current.version)
            unit.commit()
            return saved


class TargetService:
    """Orchestrate typed Target creation without executing any action."""

    def __init__(self, factory: SQLiteConnectionFactory) -> None:
        self.factory = factory

    def add(
        self,
        scope_id: ScopeId,
        rule: TargetRule,
        kind: TargetKind,
        value: str,
        *,
        context: OperationContext | None = None,
    ) -> OperationResult[Target]:
        return execute_service(
            lambda: self._add(scope_id, rule, kind, value),
            context=context,
        )

    def _add(self, scope_id: ScopeId, rule: TargetRule, kind: TargetKind, value: str) -> Target:
        target = Target.create(scope_id, rule, kind, value)
        with SQLiteUnitOfWork(self.factory) as unit:
            saved = SQLiteTargetRepository(unit).add(target)
            unit.commit()
            return saved
