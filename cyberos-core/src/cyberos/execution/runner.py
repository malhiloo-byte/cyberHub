"""argv-only subprocess execution with bounded output and isolated environment."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Mapping
from pathlib import Path

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.task.result import ExecutionFailureReason, ExecutionResult
from cyberos.domain.task.spec import ExecutionSpec

__all__ = ["ExecutionFailureReason", "ExecutionResult", "SafeSubprocessRunner"]


class SafeSubprocessRunner:
    """Execute a validated ``ExecutionSpec`` without a shell.

    The runner intentionally owns no Task state or persistence. A caller that
    owns the Task aggregate is responsible for transitioning it to FAILED when
    ``ExecutionResult.timeout_exceeded`` is true.
    """

    _TERMINATION_GRACE_SECONDS = 0.25
    _READ_CHUNK_BYTES = 64 * 1024

    async def run(
        self,
        spec: ExecutionSpec,
        *,
        environment: Mapping[str, str] | None = None,
        cwd: str | os.PathLike[str] | None = None,
    ) -> ExecutionResult:
        """Run an argv tuple with bounded pipes and a sanitized environment."""

        child_environment = self._build_environment(spec, environment)
        child_cwd = self._normalize_cwd(cwd)
        started = time.monotonic()
        try:
            process = await asyncio.create_subprocess_exec(
                *spec.command,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=child_environment,
                cwd=child_cwd,
            )
        except (OSError, TypeError, ValueError) as exc:
            raise CyberOSError(
                ErrorCode.EXECUTION_START_FAILED,
                "Safe subprocess could not be started.",
            ) from exc

        stdout_task = asyncio.create_task(self._collect(process.stdout, spec.max_output_bytes))
        stderr_task = asyncio.create_task(self._collect(process.stderr, spec.max_output_bytes))
        timeout_exceeded = False
        try:
            try:
                await asyncio.wait_for(process.wait(), timeout=spec.timeout_seconds)
            except TimeoutError:
                timeout_exceeded = True
                await self._terminate(process)
            stdout, stderr, truncated = await self._collect_streams(stdout_task, stderr_task)
        except asyncio.CancelledError:
            await self._terminate(process)
            await self._collect_streams(stdout_task, stderr_task)
            raise

        return ExecutionResult(
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            truncated=truncated,
            duration_seconds=max(0.0, time.monotonic() - started),
            timeout_exceeded=timeout_exceeded,
            failure_reason=(ExecutionFailureReason.TIMEOUT_EXCEEDED if timeout_exceeded else None),
            error_message=(
                ExecutionFailureReason.TIMEOUT_EXCEEDED.value if timeout_exceeded else None
            ),
        )

    @staticmethod
    def _build_environment(
        spec: ExecutionSpec,
        environment: Mapping[str, str] | None,
    ) -> dict[str, str]:
        if environment is None:
            return {}
        if any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in environment.items()
        ):
            raise CyberOSError(
                ErrorCode.EXECUTION_START_FAILED,
                "Safe subprocess environment must contain string keys and values.",
            )
        return {key: environment[key] for key in spec.env_policy.allowed_keys if key in environment}

    @staticmethod
    def _normalize_cwd(cwd: str | os.PathLike[str] | None) -> str | None:
        if cwd is None:
            return None
        if not isinstance(cwd, (str, Path, os.PathLike)):
            raise CyberOSError(
                ErrorCode.EXECUTION_START_FAILED,
                "Safe subprocess working directory is invalid.",
            )
        return os.fspath(cwd)

    async def _terminate(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=self._TERMINATION_GRACE_SECONDS)
        except TimeoutError:
            process.kill()
            await process.wait()

    async def _collect_streams(
        self,
        stdout_task: asyncio.Task[tuple[bytes, bool]],
        stderr_task: asyncio.Task[tuple[bytes, bool]],
    ) -> tuple[bytes, bytes, bool]:
        (stdout, stdout_truncated), (stderr, stderr_truncated) = await asyncio.gather(
            stdout_task,
            stderr_task,
        )
        return stdout, stderr, stdout_truncated or stderr_truncated

    async def _collect(
        self,
        stream: asyncio.StreamReader | None,
        limit: int,
    ) -> tuple[bytes, bool]:
        if stream is None:
            return b"", False
        chunks: list[bytes] = []
        retained = 0
        truncated = False
        while True:
            chunk = await stream.read(self._READ_CHUNK_BYTES)
            if not chunk:
                break
            remaining = limit - retained
            if remaining > 0:
                chunks.append(chunk[:remaining])
                retained += min(len(chunk), remaining)
            if len(chunk) > remaining:
                truncated = True
        return b"".join(chunks), truncated
