"""Application orchestration for authorized Task execution and retrieval."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import TYPE_CHECKING
from uuid import UUID

from cyberos.application.scope_validation import ScopeValidationService, TargetCandidate
from cyberos.application.services.common import execute_service
from cyberos.core.context import OperationContext
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.result import OperationResult
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.primitives import TargetId
from cyberos.domain.task.model import Task
from cyberos.domain.task.primitives import TaskId
from cyberos.domain.task.record import TaskRecord
from cyberos.domain.task.spec import ExecutionSpec
from cyberos.execution.task_engine import TaskExecutionEngine
from cyberos.persistence.task_repository import SQLiteTaskRepository
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork

if TYPE_CHECKING:
    from cyberos.persistence.connection import SQLiteConnectionFactory


class TaskService:
    """The only application orchestrator allowed to run and persist Tasks."""

    def __init__(self, factory: SQLiteConnectionFactory) -> None:
        self.factory = factory

    def run(
        self,
        scope_id: ScopeId,
        target_id: TargetId,
        candidate: TargetCandidate,
        execution_spec: ExecutionSpec,
        *,
        context: OperationContext | None = None,
    ) -> OperationResult[TaskRecord]:
        return execute_service(
            lambda: self._run(scope_id, target_id, candidate, execution_spec),
            context=context,
        )

    def list(
        self,
        *,
        scope_id: ScopeId | None = None,
        target_id: TargetId | None = None,
        context: OperationContext | None = None,
    ) -> OperationResult[Sequence[TaskRecord]]:
        return execute_service(
            lambda: self._list(scope_id=scope_id, target_id=target_id),
            context=context,
        )

    def show(
        self,
        task_id: TaskId,
        *,
        context: OperationContext | None = None,
    ) -> OperationResult[TaskRecord]:
        return execute_service(lambda: self._show(task_id), context=context)

    def _run(
        self,
        scope_id: ScopeId,
        target_id: TargetId,
        candidate: TargetCandidate,
        execution_spec: ExecutionSpec,
    ) -> TaskRecord:
        authorization = ScopeValidationService(self.factory).authorize_execution(
            scope_id,
            candidate,
        )
        if authorization.matched_target_id != target_id:
            raise CyberOSError(
                ErrorCode.TASK_AUTHORIZATION_TARGET_MISMATCH,
                "Requested Target does not match the authorized Scope Target.",
            )
        task = Task.create(scope_id, target_id, authorization, execution_spec)
        pending_record = TaskRecord(task)
        with SQLiteUnitOfWork(self.factory) as unit:
            SQLiteTaskRepository(unit).add(pending_record)
            unit.commit()

        updated_task, result = asyncio.run(
            TaskExecutionEngine().execute(task, execution_spec, authorization)
        )
        terminal_record = TaskRecord(updated_task, result)
        with SQLiteUnitOfWork(self.factory) as unit:
            saved = SQLiteTaskRepository(unit).update_status_and_result(
                terminal_record,
                expected_version=task.version,
            )
            unit.commit()
            return saved

    def _list(
        self,
        *,
        scope_id: ScopeId | None,
        target_id: TargetId | None,
    ) -> Sequence[TaskRecord]:
        if (scope_id is None) == (target_id is None):
            raise CyberOSError(
                ErrorCode.INVALID_INPUT,
                "Provide exactly one of --scope-id or --target-id.",
            )
        with SQLiteUnitOfWork(self.factory) as unit:
            repository = SQLiteTaskRepository(unit)
            if scope_id is not None:
                values = repository.list_by_scope(scope_id)
            else:
                assert target_id is not None
                values = repository.list_by_target(target_id)
            unit.rollback()
            return tuple(values)

    def _show(self, task_id: TaskId) -> TaskRecord:
        with SQLiteUnitOfWork(self.factory) as unit:
            record = SQLiteTaskRepository(unit).get(task_id)
            unit.rollback()
        if record is None:
            raise CyberOSError(ErrorCode.TASK_NOT_FOUND, "The Task does not exist.")
        return record


def parse_task_id(value: str) -> TaskId:
    try:
        identifier = UUID(value)
    except ValueError as exc:
        raise CyberOSError(ErrorCode.INVALID_INPUT, "Task ID must be a valid UUID4.") from exc
    if identifier.version != 4:
        raise CyberOSError(ErrorCode.INVALID_INPUT, "Task ID must be a valid UUID4.")
    return TaskId(identifier)
