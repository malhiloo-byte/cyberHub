from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from cyberos.application.services.common import execute_service
from cyberos.core.context import OperationContext
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.result import OperationResult
from cyberos.core.time import utc_now
from cyberos.domain.engagement.model import Engagement, EngagementKind, EngagementStatus
from cyberos.domain.engagement.primitives import EngagementId
from cyberos.domain.workspace.primitives import WorkspaceId
from cyberos.persistence.engagement_repository import SQLiteEngagementRepository
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork

if TYPE_CHECKING:
    from cyberos.persistence.connection import SQLiteConnectionFactory


class EngagementService:
    """Application orchestration for Engagement use cases."""

    def __init__(self, factory: SQLiteConnectionFactory) -> None:
        self.factory = factory

    def create(
        self,
        workspace_id: WorkspaceId,
        name: str,
        kind: EngagementKind,
        description: str = "",
        authorization_reference: str | None = None,
        *,
        start_at: datetime | None = None,
        context: OperationContext | None = None,
    ) -> OperationResult[Engagement]:
        return execute_service(
            lambda: self._create(
                workspace_id,
                name,
                kind,
                description,
                authorization_reference,
                start_at,
            ),
            context=context,
        )

    def list(
        self,
        workspace_id: WorkspaceId,
        *,
        status: EngagementStatus | None = None,
        context: OperationContext | None = None,
    ) -> OperationResult[Sequence[Engagement]]:
        return execute_service(lambda: self._list(workspace_id, status), context=context)

    def show(
        self,
        engagement_id: EngagementId,
        *,
        context: OperationContext | None = None,
    ) -> OperationResult[Engagement]:
        return execute_service(lambda: self._show(engagement_id), context=context)

    def transition(
        self,
        engagement_id: EngagementId,
        target_status: EngagementStatus,
        *,
        expected_version: int,
        at: datetime | None = None,
        end_at: datetime | None = None,
        context: OperationContext | None = None,
    ) -> OperationResult[Engagement]:
        return execute_service(
            lambda: self._transition(
                engagement_id,
                target_status,
                expected_version,
                at,
                end_at,
            ),
            context=context,
        )

    def archive(
        self,
        engagement_id: EngagementId,
        *,
        expected_version: int,
        context: OperationContext | None = None,
    ) -> OperationResult[Engagement]:
        return execute_service(
            lambda: self._archive(engagement_id, expected_version),
            context=context,
        )

    def _create(
        self,
        workspace_id: WorkspaceId,
        name: str,
        kind: EngagementKind,
        description: str,
        authorization_reference: str | None,
        start_at: datetime | None,
    ) -> Engagement:
        engagement = Engagement.create(
            workspace_id,
            name,
            kind,
            description,
            authorization_reference,
            start_at=start_at,
        )
        with SQLiteUnitOfWork(self.factory) as unit:
            saved = SQLiteEngagementRepository(unit).add(engagement)
            unit.commit()
            return saved

    def _list(
        self,
        workspace_id: WorkspaceId,
        status: EngagementStatus | None,
    ) -> Sequence[Engagement]:
        with SQLiteUnitOfWork(self.factory) as unit:
            values = tuple(
                SQLiteEngagementRepository(unit).list_by_workspace(
                    workspace_id,
                    status=status,
                )
            )
            unit.rollback()
            return values

    def _show(self, engagement_id: EngagementId) -> Engagement:
        with SQLiteUnitOfWork(self.factory) as unit:
            engagement = SQLiteEngagementRepository(unit).get(engagement_id)
            unit.rollback()
        if engagement is None:
            raise CyberOSError(ErrorCode.ENGAGEMENT_NOT_FOUND, "The Engagement does not exist.")
        return engagement

    def _transition(
        self,
        engagement_id: EngagementId,
        target_status: EngagementStatus,
        expected_version: int,
        at: datetime | None,
        end_at: datetime | None,
    ) -> Engagement:
        current = self._load_for_service(engagement_id)
        if (
            target_status is EngagementStatus.ACTIVE
            and current.kind is EngagementKind.AUTHORIZED_ASSESSMENT
            and not current.authorization_reference
        ):
            raise CyberOSError(
                ErrorCode.ENGAGEMENT_AUTHORIZATION_REQUIRED,
                "An authorization reference is required before activation.",
            )
        transition_at = at
        effective_end_at = end_at
        if target_status is EngagementStatus.COMPLETED and effective_end_at is None:
            transition_at = transition_at or utc_now()
            effective_end_at = transition_at
        with SQLiteUnitOfWork(self.factory) as unit:
            transitioned = SQLiteEngagementRepository(unit).transition(
                engagement_id,
                target_status,
                expected_version=expected_version,
                at=transition_at,
                end_at=effective_end_at,
            )
            unit.commit()
            return transitioned

    def _archive(self, engagement_id: EngagementId, expected_version: int) -> Engagement:
        with SQLiteUnitOfWork(self.factory) as unit:
            archived = SQLiteEngagementRepository(unit).archive(
                engagement_id,
                expected_version=expected_version,
            )
            unit.commit()
            return archived

    def _load_for_service(self, engagement_id: EngagementId) -> Engagement:
        with SQLiteUnitOfWork(self.factory) as unit:
            engagement = SQLiteEngagementRepository(unit).get(engagement_id)
            unit.rollback()
        if engagement is None:
            raise CyberOSError(ErrorCode.ENGAGEMENT_NOT_FOUND, "The Engagement does not exist.")
        return engagement


def parse_engagement_id(value: str) -> EngagementId:
    try:
        identifier = UUID(value)
    except ValueError as exc:
        raise CyberOSError(ErrorCode.INVALID_INPUT, "Engagement ID must be a valid UUID4.") from exc
    if identifier.version != 4:
        raise CyberOSError(ErrorCode.INVALID_INPUT, "Engagement ID must be a valid UUID4.")
    return identifier
