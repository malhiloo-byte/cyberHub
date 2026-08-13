"""Integration tests for the local, argv-only execution boundary."""

from __future__ import annotations

import asyncio
import sys
import time

import pytest

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.task.spec import EnvPolicy, ExecutionSpec
from cyberos.execution.runner import ExecutionFailureReason, SafeSubprocessRunner


def run_async(coroutine: object) -> object:
    """Run one async test operation without requiring pytest-asyncio."""

    return asyncio.run(coroutine)  # type: ignore[arg-type]


def test_argv_treats_shell_metacharacters_as_literal_arguments() -> None:
    payload = "; echo INJECTION && echo PIPE | echo REDIRECT"
    spec = ExecutionSpec(
        command=(sys.executable, "-c", "import sys; print(sys.argv[1])", payload),
    )

    result = run_async(SafeSubprocessRunner().run(spec))

    assert result.exit_code == 0  # type: ignore[union-attr]
    assert result.stdout == f"{payload}\n".encode()  # type: ignore[union-attr]


def test_timeout_terminates_slow_process_and_records_reason() -> None:
    spec = ExecutionSpec(
        command=(sys.executable, "-c", "import time; time.sleep(5)"),
        timeout_seconds=1,
    )
    started = time.monotonic()

    result = run_async(SafeSubprocessRunner().run(spec))

    elapsed = time.monotonic() - started
    assert result.timeout_exceeded is True  # type: ignore[union-attr]
    assert result.failure_reason is ExecutionFailureReason.TIMEOUT_EXCEEDED  # type: ignore[union-attr]
    assert result.exit_code is not None  # type: ignore[union-attr]
    assert elapsed < 3  # type: ignore[comparison-overlap]


def test_output_is_truncated_at_max_output_bytes() -> None:
    spec = ExecutionSpec(
        command=(sys.executable, "-c", "import sys; sys.stdout.write('x' * 100)"),
        max_output_bytes=16,
    )

    result = run_async(SafeSubprocessRunner().run(spec))

    assert result.exit_code == 0  # type: ignore[union-attr]
    assert result.stdout == b"x" * 16  # type: ignore[union-attr]
    assert result.truncated is True  # type: ignore[union-attr]


def test_stdout_and_stderr_are_bounded_independently() -> None:
    spec = ExecutionSpec(
        command=(
            sys.executable,
            "-c",
            "import sys; sys.stdout.write('o'*20); sys.stderr.write('e'*20)",
        ),
        max_output_bytes=8,
    )

    result = run_async(SafeSubprocessRunner().run(spec))

    assert result.stdout == b"o" * 8  # type: ignore[union-attr]
    assert result.stderr == b"e" * 8  # type: ignore[union-attr]
    assert result.truncated is True  # type: ignore[union-attr]


def test_environment_allowlist_does_not_inherit_or_forward_sensitive_keys() -> None:
    spec = ExecutionSpec(
        command=(
            sys.executable,
            "-c",
            "import os; print(os.getenv('CYBEROS_VISIBLE', 'missing')); "
            "print(os.getenv('CYBEROS_SECRET', 'missing'))",
        ),
        env_policy=EnvPolicy(allowed_keys=("CYBEROS_VISIBLE",)),
    )

    result = run_async(
        SafeSubprocessRunner().run(
            spec,
            environment={
                "CYBEROS_VISIBLE": "allowed",
                "CYBEROS_SECRET": "must-not-pass",
            },
        )
    )

    assert result.exit_code == 0  # type: ignore[union-attr]
    assert result.stdout == b"allowed\nmissing\n"  # type: ignore[union-attr]


def test_environment_values_must_be_strings() -> None:
    spec = ExecutionSpec(command=(sys.executable, "-c", "print('never')"))

    with pytest.raises(CyberOSError) as error:
        run_async(SafeSubprocessRunner().run(spec, environment={"X": 1}))  # type: ignore[dict-item]

    assert error.value.code is ErrorCode.EXECUTION_START_FAILED


def test_spawn_failure_is_translated_without_raw_os_error() -> None:
    spec = ExecutionSpec(command=("/definitely/missing/cyberos-command",))

    with pytest.raises(CyberOSError) as error:
        run_async(SafeSubprocessRunner().run(spec))

    assert error.value.code is ErrorCode.EXECUTION_START_FAILED
    assert "No such file" not in error.value.message
