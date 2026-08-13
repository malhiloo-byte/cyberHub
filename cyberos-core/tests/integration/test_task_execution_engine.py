"""Integration tests for TaskExecutionEngine lifecycle orchestration."""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta

from cyberos.application.scope_validation import ExecutionAuthorization, TargetCandidate
from cyberos.core.ids import new_id
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.primitives import TargetId, TargetKind, TargetRule
from cyberos.domain.task.model import Task
from cyberos.domain.task.primitives import TaskStatus
from cyberos.domain.task.spec import ExecutionSpec
from cyberos.execution.task_engine import TaskExecutionEngine


def run_async(coroutine: object) -> object:
    return asyncio.run(coroutine)  # type: ignore[arg-type]


def build_task(
    command: tuple[str, ...], *, timeout_seconds: int = 2
) -> tuple[Task, ExecutionAuthorization]:
    now = datetime.now(UTC)
    scope_id = ScopeId(new_id())
    target_id = TargetId(new_id())
    authorization = ExecutionAuthorization(
        scope_id=scope_id,
        candidate=TargetCandidate("localhost", TargetKind.FQDN),
        authorized_at=now,
        expires_at=now + timedelta(minutes=5),
        matched_target_id=target_id,
        matching_rule=TargetRule.INCLUDE,
        reason="test_authorized",
        scope_version=1,
    )
    spec = ExecutionSpec(command=command, timeout_seconds=timeout_seconds)
    return Task.create(scope_id, target_id, authorization, spec, now=now), authorization


def test_success_transitions_task_through_running_to_completed() -> None:
    task, authorization = build_task((sys.executable, "-c", "print('ok')"))

    updated, result = run_async(
        TaskExecutionEngine().execute(task, task.execution_spec, authorization)
    )

    assert updated.status is TaskStatus.COMPLETED  # type: ignore[union-attr]
    assert updated.started_at is not None  # type: ignore[union-attr]
    assert updated.completed_at is not None  # type: ignore[union-attr]
    assert updated.version == 3  # type: ignore[union-attr]
    assert result.exit_code == 0  # type: ignore[union-attr]


def test_nonzero_exit_transitions_task_to_failed() -> None:
    task, authorization = build_task((sys.executable, "-c", "raise SystemExit(7)"))

    updated, result = run_async(
        TaskExecutionEngine().execute(task, task.execution_spec, authorization)
    )

    assert updated.status is TaskStatus.FAILED  # type: ignore[union-attr]
    assert updated.failed_at is not None  # type: ignore[union-attr]
    assert result.exit_code == 7  # type: ignore[union-attr]
    assert result.timeout_exceeded is False  # type: ignore[union-attr]


def test_timeout_transitions_task_to_failed_and_preserves_reason() -> None:
    task, authorization = build_task(
        (sys.executable, "-c", "import time; time.sleep(5)"),
        timeout_seconds=1,
    )

    updated, result = run_async(
        TaskExecutionEngine().execute(task, task.execution_spec, authorization)
    )

    assert updated.status is TaskStatus.FAILED  # type: ignore[union-attr]
    assert result.timeout_exceeded is True  # type: ignore[union-attr]
    assert result.failure_reason is not None  # type: ignore[union-attr]


def test_engine_rejects_spec_not_bound_to_task() -> None:
    task, authorization = build_task((sys.executable, "-c", "print('bound')"))
    different_spec = ExecutionSpec(command=(sys.executable, "-c", "print('other')"))

    from cyberos.core.errors import CyberOSError, ErrorCode

    try:
        run_async(TaskExecutionEngine().execute(task, different_spec, authorization))
    except CyberOSError as error:
        assert error.code is ErrorCode.TASK_EXECUTION_SPEC_MISMATCH
    else:
        raise AssertionError("Expected a Task execution-spec mismatch")
