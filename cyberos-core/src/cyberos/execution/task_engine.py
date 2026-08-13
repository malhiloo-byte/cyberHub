"""Task lifecycle orchestration around the safe subprocess boundary."""

from __future__ import annotations

from datetime import datetime

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.time import ensure_utc, utc_now
from cyberos.domain.target.primitives import TargetRule
from cyberos.domain.task.model import ExecutionAuthorizationContract, Task
from cyberos.domain.task.primitives import TaskStatus
from cyberos.domain.task.spec import ExecutionSpec
from cyberos.execution.runner import ExecutionResult, SafeSubprocessRunner


class TaskExecutionEngine:
    """Run one authorized Task and return its immutable post-execution state."""

    def __init__(self, runner: SafeSubprocessRunner | None = None) -> None:
        self._runner = runner or SafeSubprocessRunner()

    async def execute(
        self,
        task: Task,
        execution_spec: ExecutionSpec,
        authorization: ExecutionAuthorizationContract,
        *,
        now: datetime | None = None,
    ) -> tuple[Task, ExecutionResult]:
        """Transition, execute, and transition the Task to a terminal state."""

        timestamp = ensure_utc(now) if now is not None else utc_now()
        self._validate_contract(task, execution_spec, authorization, timestamp)
        running = task.transition(TaskStatus.RUNNING, at=timestamp)
        result = await self._runner.run(execution_spec)
        finished_at = utc_now()
        terminal_status = (
            TaskStatus.COMPLETED
            if result.exit_code == 0 and not result.timeout_exceeded
            else TaskStatus.FAILED
        )
        return running.transition(terminal_status, at=finished_at), result

    @staticmethod
    def _validate_contract(
        task: Task,
        execution_spec: ExecutionSpec,
        authorization: ExecutionAuthorizationContract,
        timestamp: datetime,
    ) -> None:
        if task.execution_spec != execution_spec:
            raise CyberOSError(
                ErrorCode.TASK_EXECUTION_SPEC_MISMATCH,
                "Task execution specification does not match the requested specification.",
            )
        if not isinstance(authorization, ExecutionAuthorizationContract):
            raise CyberOSError(
                ErrorCode.TASK_AUTHORIZATION_REQUIRED,
                "Task execution requires ExecutionAuthorization.",
            )
        if task.scope_id != authorization.scope_id:
            raise CyberOSError(
                ErrorCode.TASK_AUTHORIZATION_SCOPE_MISMATCH,
                "Task Scope does not match ExecutionAuthorization Scope.",
            )
        if task.target_id != authorization.matched_target_id:
            raise CyberOSError(
                ErrorCode.TASK_AUTHORIZATION_TARGET_MISMATCH,
                "Task Target does not match ExecutionAuthorization Target.",
            )
        if authorization.expires_at is not None and authorization.expires_at <= timestamp:
            raise CyberOSError(
                ErrorCode.TASK_AUTHORIZATION_EXPIRED,
                "ExecutionAuthorization has expired.",
            )
        if authorization.matching_rule is not TargetRule.INCLUDE:
            raise CyberOSError(
                ErrorCode.TASK_AUTHORIZATION_REQUIRED,
                "Task execution requires an Include authorization.",
            )
