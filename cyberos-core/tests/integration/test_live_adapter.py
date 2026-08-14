"""Module 2.0 live-adapter tests using only neutral local Python processes."""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from cyberos.application.scope_validation import ExecutionAuthorization, TargetCandidate
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.primitives import TargetId, TargetKind, TargetRule
from cyberos.domain.task.model import Task
from cyberos.domain.task.spec import EnvPolicy, ExecutionSpec
from cyberos.execution.live_adapter import (
    ApprovedExecutable,
    CommandSandbox,
    LiveSubprocessAdapter,
    LiveSubprocessRequest,
    TerminationKind,
)

NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


def run_async(coroutine: object) -> object:
    return asyncio.run(coroutine)  # type: ignore[arg-type]


def make_request(
    *,
    command: tuple[str, ...] | None = None,
    target_value: str = "example.test",
    target_id: TargetId | None = None,
    authorization_target_id: TargetId | None = None,
    expires_at: datetime | None = NOW + timedelta(hours=1),
    timeout_seconds: int = 2,
    max_stdout_bytes: int = 4_096,
    max_stderr_bytes: int = 4_096,
    environment: tuple[tuple[str, str], ...] = (),
    env_keys: tuple[str, ...] = (),
) -> tuple[LiveSubprocessRequest, ApprovedExecutable]:
    scope_id = ScopeId(uuid4())
    actual_target_id = target_id or TargetId(uuid4())
    auth_target = authorization_target_id or actual_target_id
    candidate = TargetCandidate(target_value, TargetKind.FQDN)
    authorization = ExecutionAuthorization(
        scope_id=scope_id,
        candidate=candidate,
        authorized_at=NOW,
        expires_at=expires_at,
        matched_target_id=auth_target,
        matching_rule=TargetRule.INCLUDE,
        reason="test_authorized",
        scope_version=1,
    )
    selected_command = command or (
        sys.executable,
        "-c",
        "import sys; print(sys.argv[1])",
        target_value,
    )
    spec = ExecutionSpec(
        command=selected_command,
        timeout_seconds=timeout_seconds,
        max_output_bytes=max(max_stdout_bytes, max_stderr_bytes, 1),
        env_policy=EnvPolicy(env_keys),
    )
    task = Task.create(
        scope_id,
        actual_target_id,
        authorization,
        spec,
        now=NOW,
    )
    executable = ApprovedExecutable(
        logical_id="neutral.python",
        executable=sys.executable,
        command_prefix=(sys.executable,),
        allowed_environment_keys=env_keys,
        supported_target_kinds=(TargetKind.FQDN,),
        require_target_argument=True,
        opaque_argument_indexes=frozenset({2}),
        max_timeout_seconds=timeout_seconds,
        max_output_bytes=max(max_stdout_bytes, max_stderr_bytes, 1),
    )
    return (
        LiveSubprocessRequest(
            task=task,
            authorization=authorization,
            scope_id=scope_id,
            target_id=actual_target_id,
            target_kind=TargetKind.FQDN,
            canonical_target=target_value,
            command=selected_command,
            allowed_executable_id="neutral.python",
            environment=environment,
            timeout_seconds=timeout_seconds,
            max_stdout_bytes=max_stdout_bytes,
            max_stderr_bytes=max_stderr_bytes,
        ),
        executable,
    )


def adapter_for(
    request: LiveSubprocessRequest, executable: ApprovedExecutable
) -> LiveSubprocessAdapter:
    return LiveSubprocessAdapter(
        CommandSandbox({executable.logical_id: executable}),
        clock=lambda: NOW,
    )


def test_neutral_process_success_is_bound_and_redacted_receipt_is_bounded() -> None:
    request, executable = make_request()
    adapter = adapter_for(request, executable)

    receipt = run_async(adapter.run(request))

    assert receipt.exit_code == 0  # type: ignore[union-attr]
    assert receipt.stdout == b"example.test\n"  # type: ignore[union-attr]
    assert receipt.redaction_applied is True  # type: ignore[union-attr]
    assert receipt.failure_code is None  # type: ignore[union-attr]
    assert request.task.status.value == "pending"


def test_scope_target_authorization_mismatch_fails_before_spawn() -> None:
    request, executable = make_request(target_id=TargetId(uuid4()))
    adapter = adapter_for(request, executable)
    mismatched = LiveSubprocessRequest(
        task=request.task,
        authorization=request.authorization,
        scope_id=request.scope_id,
        target_id=TargetId(uuid4()),
        target_kind=request.target_kind,
        canonical_target=request.canonical_target,
        command=request.command,
        allowed_executable_id=request.allowed_executable_id,
    )

    with pytest.raises(CyberOSError) as error:
        run_async(adapter.run(mismatched))
    assert error.value.code is ErrorCode.LIVE_ADAPTER_UNAUTHORIZED


def test_expired_authorization_fails_closed_before_spawn() -> None:
    request, executable = make_request()
    adapter = LiveSubprocessAdapter(
        CommandSandbox({executable.logical_id: executable}),
        clock=lambda: NOW + timedelta(hours=2),
    )

    with pytest.raises(CyberOSError) as error:
        run_async(adapter.run(request))
    assert error.value.code is ErrorCode.LIVE_ADAPTER_UNAUTHORIZED


def test_shell_metacharacter_in_non_opaque_argument_is_rejected() -> None:
    payload = "example.test; echo INJECTION && echo PIPE"
    request, executable = make_request(target_value=payload)
    adapter = adapter_for(request, executable)

    with pytest.raises(CyberOSError) as error:
        run_async(adapter.run(request))
    assert error.value.code is ErrorCode.COMMAND_SANITIZATION_FAILED
    assert payload not in error.value.message


def test_command_must_match_the_task_execution_spec() -> None:
    request, executable = make_request()
    altered = LiveSubprocessRequest(
        task=request.task,
        authorization=request.authorization,
        scope_id=request.scope_id,
        target_id=request.target_id,
        target_kind=request.target_kind,
        canonical_target=request.canonical_target,
        command=(sys.executable, "-c", "print('altered')", request.canonical_target),
        allowed_executable_id=request.allowed_executable_id,
    )
    with pytest.raises(CyberOSError) as error:
        run_async(adapter_for(altered, executable).run(altered))
    assert error.value.code is ErrorCode.LIVE_ADAPTER_UNAUTHORIZED


def test_environment_is_empty_by_default_and_allowlisted_explicitly() -> None:
    command = (
        sys.executable,
        "-c",
        "import os; print(os.getenv('CYBEROS_VISIBLE', 'missing')); "
        "print(os.getenv('CYBEROS_SECRET', 'missing'))",
        "example.test",
    )
    request, executable = make_request(
        command=command,
        environment=(("CYBEROS_VISIBLE", "allowed"),),
        env_keys=("CYBEROS_VISIBLE",),
    )
    receipt = run_async(adapter_for(request, executable).run(request))

    assert receipt.stdout == b"allowed\nmissing\n"  # type: ignore[union-attr]


def test_timeout_returns_typed_timeout_receipt_and_terminates() -> None:
    command = (
        sys.executable,
        "-c",
        "import time; time.sleep(5)",
        "example.test",
    )
    request, executable = make_request(command=command, timeout_seconds=1)
    receipt = run_async(adapter_for(request, executable).run(request))

    assert receipt.timeout_exceeded is True  # type: ignore[union-attr]
    assert receipt.failure_code is ErrorCode.SUBPROCESS_TIMEOUT  # type: ignore[union-attr]
    assert receipt.termination is TerminationKind.TIMEOUT  # type: ignore[union-attr]
    assert receipt.exit_code is not None  # type: ignore[union-attr]


def test_stdout_and_stderr_are_capped_and_marked_as_limit_failure() -> None:
    command = (
        sys.executable,
        "-c",
        "import sys; sys.stdout.write('o'*100); sys.stderr.write('e'*100)",
        "example.test",
    )
    request, executable = make_request(
        command=command,
        max_stdout_bytes=8,
        max_stderr_bytes=8,
    )
    receipt = run_async(adapter_for(request, executable).run(request))

    assert receipt.stdout == b"o" * 8  # type: ignore[union-attr]
    assert receipt.stderr == b"e" * 8  # type: ignore[union-attr]
    assert receipt.stdout_truncated is True  # type: ignore[union-attr]
    assert receipt.stderr_truncated is True  # type: ignore[union-attr]
    assert receipt.failure_code is ErrorCode.LIVE_ADAPTER_LIMIT_EXCEEDED  # type: ignore[union-attr]


def test_output_redacts_credentials_and_local_paths_before_receipt() -> None:
    command = (
        sys.executable,
        "-c",
        "print('Authorization: secret-token /home/ubuntu/private.txt')",
        "example.test",
    )
    request, executable = make_request(command=command)
    receipt = run_async(adapter_for(request, executable).run(request))

    assert b"secret-token" not in receipt.stdout  # type: ignore[union-attr]
    assert b"/home/ubuntu/private.txt" not in receipt.stdout  # type: ignore[union-attr]
    assert b"[REDACTED]" in receipt.stdout  # type: ignore[union-attr]
    assert b"[PATH_REDACTED]" in receipt.stdout  # type: ignore[union-attr]


def test_spawn_failure_is_typed_and_does_not_leak_executable_path() -> None:
    missing = ApprovedExecutable(
        logical_id="neutral.missing",
        executable="/definitely/missing/cyberos-neutral-process",
        command_prefix=("/definitely/missing/cyberos-neutral-process",),
        supported_target_kinds=(TargetKind.FQDN,),
        require_target_argument=True,
        opaque_argument_indexes=frozenset({2}),
    )
    command = (missing.executable, "-c", "print('never')", "example.test")
    altered, _ = make_request(command=command)
    altered = LiveSubprocessRequest(
        task=altered.task,
        authorization=altered.authorization,
        scope_id=altered.scope_id,
        target_id=altered.target_id,
        target_kind=altered.target_kind,
        canonical_target=altered.canonical_target,
        command=command,
        allowed_executable_id=missing.logical_id,
        timeout_seconds=altered.task.execution_spec.timeout_seconds,
        max_stdout_bytes=altered.task.execution_spec.max_output_bytes,
        max_stderr_bytes=altered.task.execution_spec.max_output_bytes,
    )

    with pytest.raises(CyberOSError) as error:
        run_async(adapter_for(altered, missing).run(altered))
    assert error.value.code is ErrorCode.LIVE_ADAPTER_START_FAILED
    assert missing.executable not in error.value.message
