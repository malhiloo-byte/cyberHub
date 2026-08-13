from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING
from uuid import UUID

from cyberos.application.services.common import execute_service
from cyberos.core.context import OperationContext
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.result import OperationResult
from cyberos.domain.workspace.model import Workspace, WorkspaceStatus
from cyberos.domain.workspace.primitives import WorkspaceId
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork
from cyberos.persistence.workspace_repository import SQLiteWorkspaceRepository

if TYPE_CHECKING:
    from cyberos.persistence.connection import SQLiteConnectionFactory


class WorkspaceService:
    """Application orchestration for Workspace use cases."""

    def __init__(self, factory: SQLiteConnectionFactory) -> None:
        self.factory = factory

    def create(
        self,
        name: str,
        description: str = "",
        *,
        context: OperationContext | None = None,
    ) -> OperationResult[Workspace]:
        return execute_service(
            lambda: self._create(name, description),
            context=context,
        )

    def list(
        self,
        *,
        status: WorkspaceStatus | None = None,
        context: OperationContext | None = None,
    ) -> OperationResult[Sequence[Workspace]]:
        return execute_service(lambda: self._list(status), context=context)

    def show(
        self,
        workspace_id: WorkspaceId,
        *,
        context: OperationContext | None = None,
    ) -> OperationResult[Workspace]:
        return execute_service(lambda: self._show(workspace_id), context=context)

    def archive(
        self,
        workspace_id: WorkspaceId,
        *,
        expected_version: int,
        context: OperationContext | None = None,
    ) -> OperationResult[Workspace]:
        return execute_service(
            lambda: self._archive(workspace_id, expected_version),
            context=context,
        )

    def _create(self, name: str, description: str) -> Workspace:
        workspace = Workspace.create(name, description)
        with SQLiteUnitOfWork(self.factory) as unit:
            saved = SQLiteWorkspaceRepository(unit).add(workspace)
            unit.commit()
            return saved

    def _list(self, status: WorkspaceStatus | None) -> Sequence[Workspace]:
        with SQLiteUnitOfWork(self.factory) as unit:
            values = tuple(SQLiteWorkspaceRepository(unit).list(status=status))
            unit.rollback()
            return values

    def _show(self, workspace_id: WorkspaceId) -> Workspace:
        with SQLiteUnitOfWork(self.factory) as unit:
            workspace = SQLiteWorkspaceRepository(unit).get(workspace_id)
            unit.rollback()
        if workspace is None:
            raise CyberOSError(ErrorCode.WORKSPACE_NOT_FOUND, "The Workspace does not exist.")
        return workspace

    def _archive(self, workspace_id: WorkspaceId, expected_version: int) -> Workspace:
        with SQLiteUnitOfWork(self.factory) as unit:
            archived = SQLiteWorkspaceRepository(unit).archive(
                workspace_id,
                expected_version=expected_version,
            )
            unit.commit()
            return archived


def parse_workspace_id(value: str) -> WorkspaceId:
    try:
        identifier = UUID(value)
    except ValueError as exc:
        raise CyberOSError(ErrorCode.INVALID_INPUT, "Workspace ID must be a valid UUID4.") from exc
    if identifier.version != 4:
        raise CyberOSError(ErrorCode.INVALID_INPUT, "Workspace ID must be a valid UUID4.")
    return identifier
