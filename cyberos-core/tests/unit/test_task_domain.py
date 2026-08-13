from datetime import UTC, datetime, timedelta

import pytest

from cyberos.application.scope_validation import ExecutionAuthorization, TargetCandidate
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.ids import new_id
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.primitives import TargetId, TargetKind, TargetRule
from cyberos.domain.task.model import Task
from cyberos.domain.task.primitives import TaskStatus
from cyberos.domain.task.spec import EnvPolicy, ExecutionSpec

NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


def authorization(
    scope_id: ScopeId,
    target_id: TargetId,
    *,
    expires_at: datetime | None = NOW + timedelta(hours=1),
) -> ExecutionAuthorization:
    return ExecutionAuthorization(
        scope_id=scope_id,
        candidate=TargetCandidate("api.example.com", TargetKind.FQDN),
        authorized_at=NOW,
        expires_at=expires_at,
        matched_target_id=target_id,
        matching_rule=TargetRule.INCLUDE,
        reason="execution_authorized_by_scope",
        scope_version=2,
    )


def spec() -> ExecutionSpec:
    return ExecutionSpec(
        command=("python", "-c", "print('safe argv')"),
        timeout_seconds=30,
        max_output_bytes=4096,
        env_policy=EnvPolicy(allowed_keys=("PATH", "LANG")),
    )


def test_task_creation_requires_target_bound_time_aware_authorization() -> None:
    scope_id = ScopeId(new_id())
    target_id = TargetId(new_id())
    task = Task.create(scope_id, target_id, authorization(scope_id, target_id), spec(), now=NOW)
    assert task.scope_id == scope_id
    assert task.target_id == target_id
    assert task.status is TaskStatus.PENDING
    assert task.version == 1
    assert task.authorization_expires_at == NOW + timedelta(hours=1)


def test_raw_target_string_is_rejected_at_task_boundary() -> None:
    scope_id = ScopeId(new_id())
    target_id = TargetId(new_id())
    with pytest.raises(CyberOSError) as captured:
        Task.create(
            scope_id,
            "api.example.com",
            authorization(scope_id, target_id),
            spec(),
            now=NOW,
        )  # type: ignore[arg-type]
    assert captured.value.code is ErrorCode.TASK_AUTHORIZATION_TARGET_MISMATCH


def test_scope_mismatch_is_rejected() -> None:
    scope_id = ScopeId(new_id())
    other_scope_id = ScopeId(new_id())
    target_id = TargetId(new_id())
    with pytest.raises(CyberOSError) as captured:
        Task.create(other_scope_id, target_id, authorization(scope_id, target_id), spec(), now=NOW)
    assert captured.value.code is ErrorCode.TASK_AUTHORIZATION_SCOPE_MISMATCH


def test_target_mismatch_is_rejected() -> None:
    scope_id = ScopeId(new_id())
    target_id = TargetId(new_id())
    other_target_id = TargetId(new_id())
    with pytest.raises(CyberOSError) as captured:
        Task.create(scope_id, other_target_id, authorization(scope_id, target_id), spec(), now=NOW)
    assert captured.value.code is ErrorCode.TASK_AUTHORIZATION_TARGET_MISMATCH


def test_expired_authorization_is_rejected() -> None:
    scope_id = ScopeId(new_id())
    target_id = TargetId(new_id())
    expired = authorization(scope_id, target_id, expires_at=NOW)
    with pytest.raises(CyberOSError) as captured:
        Task.create(scope_id, target_id, expired, spec(), now=NOW)
    assert captured.value.code is ErrorCode.TASK_AUTHORIZATION_EXPIRED


def test_missing_or_non_include_authorization_is_rejected() -> None:
    scope_id = ScopeId(new_id())
    target_id = TargetId(new_id())
    with pytest.raises(CyberOSError) as missing:
        Task.create(scope_id, target_id, object(), spec(), now=NOW)  # type: ignore[arg-type]
    assert missing.value.code is ErrorCode.TASK_AUTHORIZATION_REQUIRED

    base = authorization(scope_id, target_id)
    excluded = ExecutionAuthorization(
        scope_id=base.scope_id,
        candidate=base.candidate,
        authorized_at=base.authorized_at,
        expires_at=base.expires_at,
        matched_target_id=base.matched_target_id,
        matching_rule=TargetRule.EXCLUDE,
        reason=base.reason,
        scope_version=base.scope_version,
    )
    with pytest.raises(CyberOSError) as non_include:
        Task.create(scope_id, target_id, excluded, spec(), now=NOW)
    assert non_include.value.code is ErrorCode.TASK_AUTHORIZATION_REQUIRED


def test_task_state_machine_allows_run_to_terminal_and_increments_version() -> None:
    scope_id = ScopeId(new_id())
    target_id = TargetId(new_id())
    task = Task.create(scope_id, target_id, authorization(scope_id, target_id), spec(), now=NOW)
    running = task.transition(TaskStatus.RUNNING, at=NOW + timedelta(seconds=1))
    completed = running.transition(TaskStatus.COMPLETED, at=NOW + timedelta(seconds=2))
    assert running.started_at == NOW + timedelta(seconds=1)
    assert completed.completed_at == NOW + timedelta(seconds=2)
    assert completed.version == 3


@pytest.mark.parametrize(
    ("current", "requested"),
    [
        (TaskStatus.PENDING, TaskStatus.COMPLETED),
        (TaskStatus.COMPLETED, TaskStatus.RUNNING),
        (TaskStatus.FAILED, TaskStatus.RUNNING),
        (TaskStatus.CANCELLED, TaskStatus.COMPLETED),
    ],
)
def test_illegal_task_transitions_are_rejected(current: TaskStatus, requested: TaskStatus) -> None:
    scope_id = ScopeId(new_id())
    target_id = TargetId(new_id())
    task = Task.create(scope_id, target_id, authorization(scope_id, target_id), spec(), now=NOW)
    if current is TaskStatus.RUNNING:
        task = task.transition(TaskStatus.RUNNING, at=NOW + timedelta(seconds=1))
    elif current is TaskStatus.COMPLETED:
        task = task.transition(TaskStatus.RUNNING, at=NOW + timedelta(seconds=1)).transition(
            TaskStatus.COMPLETED, at=NOW + timedelta(seconds=2)
        )
    elif current is TaskStatus.FAILED:
        task = task.transition(TaskStatus.RUNNING, at=NOW + timedelta(seconds=1)).transition(
            TaskStatus.FAILED, at=NOW + timedelta(seconds=2)
        )
    elif current is TaskStatus.CANCELLED:
        task = task.transition(TaskStatus.CANCELLED, at=NOW + timedelta(seconds=1))
    with pytest.raises(CyberOSError) as captured:
        task.transition(requested, at=NOW + timedelta(seconds=3))
    assert captured.value.code is ErrorCode.TASK_INVALID_TRANSITION


@pytest.mark.parametrize(
    "bad_spec",
    [
        {"command": ()},
        {"command": ("",)},
        {"command": ("python",), "timeout_seconds": 0},
        {"command": ("python",), "timeout_seconds": 3601},
        {"command": ("python",), "max_output_bytes": 0},
        {"command": ("python",), "max_output_bytes": 16_777_217},
        {"command": ["python"]},
    ],
)
def test_execution_spec_rejects_unsafe_or_invalid_values(bad_spec: dict[str, object]) -> None:
    with pytest.raises(CyberOSError) as captured:
        ExecutionSpec(**bad_spec)  # type: ignore[arg-type]
    assert captured.value.code is ErrorCode.EXECUTION_SPEC_INVALID


def test_env_policy_is_an_explicit_unique_allowlist() -> None:
    assert EnvPolicy(allowed_keys=("PATH", "LANG")).allowed_keys == ("PATH", "LANG")
    with pytest.raises(CyberOSError):
        EnvPolicy(allowed_keys=("PATH", "PATH"))
    with pytest.raises(CyberOSError):
        EnvPolicy(allowed_keys=("BAD=VALUE",))
