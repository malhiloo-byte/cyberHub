"""The reviewed live subprocess boundary for Phase 2.

Style note: this module is a narrow, deny-by-default execution adapter. It
accepts host-created immutable requests, validates Scope/Target/Task binding,
delegates argv-only execution to the existing safe runner, and returns bounded
redacted receipts. It owns no persistence, renderer, network client, retry,
or authorization-renewal capability.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from cyberos.application.scope_validation import ExecutionAuthorization
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.time import ensure_utc, utc_now
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.primitives import TargetId, TargetKind, TargetRule
from cyberos.domain.task.model import Task
from cyberos.domain.task.spec import EnvPolicy, ExecutionSpec
from cyberos.execution.runner import SafeSubprocessRunner

__all__ = [
    "ApprovedExecutable",
    "BoundedProcessReceipt",
    "CommandSandbox",
    "LiveSubprocessAdapter",
    "LiveSubprocessRequest",
    "TerminationKind",
    "ValidatedCommandPlan",
]


_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_OUTPUT_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SHELL_META_RE = re.compile(r"[;|&><$`] |\n|\r", re.VERBOSE)
_SECRET_RE = re.compile(
    r"(?i)\b(authorization|cookie|password|passwd|token|api[_-]?key)\s*[:=]\s*([^\s,;]+)"
)
_PATH_RE = re.compile(r"(?<![A-Za-z0-9_])/(?:home|root|tmp|var|etc|Users)/[^\s,;]+")


class TerminationKind(StrEnum):
    EXITED = "exited"
    TERMINATED = "terminated"
    KILLED = "killed"
    TIMEOUT = "timeout"


def _safe_text(value: str, field: str, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value.encode("utf-8")) > maximum
        or _CONTROL_RE.search(value)
    ):
        raise CyberOSError(
            ErrorCode.COMMAND_SANITIZATION_FAILED, f"Live adapter {field} is invalid."
        )
    return value.strip()


def _uuid4(value: object, field: str) -> None:
    if getattr(value, "version", None) != 4:
        raise CyberOSError(ErrorCode.LIVE_ADAPTER_UNAUTHORIZED, f"Live adapter {field} is invalid.")


@dataclass(frozen=True, slots=True)
class ApprovedExecutable:
    """Reviewed logical executable definition used by CommandSandbox."""

    logical_id: str
    executable: str
    command_prefix: tuple[str, ...] = ()
    allowed_environment_keys: tuple[str, ...] = ()
    supported_target_kinds: tuple[TargetKind, ...] = ()
    require_target_argument: bool = False
    opaque_argument_indexes: frozenset[int] = frozenset()
    max_timeout_seconds: int = 3_600
    max_output_bytes: int = 16_777_216

    def __post_init__(self) -> None:
        _safe_text(self.logical_id, "executable identity", 128)
        _safe_text(self.executable, "executable", 4_096)
        if not os.path.isabs(self.executable):
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_MANIFEST_INVALID,
                "Live adapter executable identity must be absolute.",
            )
        if not isinstance(self.command_prefix, tuple) or any(
            not isinstance(part, str) or not part for part in self.command_prefix
        ):
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_MANIFEST_INVALID, "Command prefix is invalid."
            )
        if self.command_prefix and self.command_prefix[0] != self.executable:
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_MANIFEST_INVALID,
                "Command prefix executable does not match the manifest.",
            )
        if not isinstance(self.allowed_environment_keys, tuple) or any(
            not isinstance(key, str) or not key or "=" in key
            for key in self.allowed_environment_keys
        ):
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_MANIFEST_INVALID, "Environment allowlist is invalid."
            )
        if len(set(self.allowed_environment_keys)) != len(self.allowed_environment_keys):
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_MANIFEST_INVALID, "Environment allowlist is duplicated."
            )
        if not isinstance(self.supported_target_kinds, tuple) or any(
            not isinstance(kind, TargetKind) for kind in self.supported_target_kinds
        ):
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_MANIFEST_INVALID, "Target-kind allowlist is invalid."
            )
        if not isinstance(self.require_target_argument, bool):
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_MANIFEST_INVALID, "Target binding policy is invalid."
            )
        if any(
            not isinstance(index, int) or isinstance(index, bool) or index < 0
            for index in self.opaque_argument_indexes
        ):
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_MANIFEST_INVALID, "Opaque argument policy is invalid."
            )
        if (
            not isinstance(self.max_timeout_seconds, int)
            or isinstance(self.max_timeout_seconds, bool)
            or self.max_timeout_seconds < 1
            or not isinstance(self.max_output_bytes, int)
            or isinstance(self.max_output_bytes, bool)
            or self.max_output_bytes < 1
        ):
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_MANIFEST_INVALID, "Executable limits are invalid."
            )


@dataclass(frozen=True, slots=True)
class LiveSubprocessRequest:
    task: Task
    authorization: ExecutionAuthorization
    scope_id: ScopeId
    target_id: TargetId
    target_kind: TargetKind
    canonical_target: str
    command: tuple[str, ...]
    allowed_executable_id: str
    environment: tuple[tuple[str, str], ...] = ()
    working_directory: str | os.PathLike[str] | None = None
    timeout_seconds: int = 30
    max_stdout_bytes: int = 1_048_576
    max_stderr_bytes: int = 1_048_576
    max_argument_bytes: int = 16_384

    def __post_init__(self) -> None:
        _uuid4(self.scope_id, "scope_id")
        _uuid4(self.target_id, "target_id")
        if not isinstance(self.task, Task) or not isinstance(
            self.authorization, ExecutionAuthorization
        ):
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_UNAUTHORIZED, "Live adapter context is invalid."
            )
        if not isinstance(self.target_kind, TargetKind):
            raise CyberOSError(ErrorCode.COMMAND_SANITIZATION_FAILED, "Target kind is invalid.")
        _safe_text(self.canonical_target, "canonical target", 4_096)
        _safe_text(self.allowed_executable_id, "executable identity", 128)
        if (
            not isinstance(self.command, tuple)
            or not self.command
            or any(not isinstance(part, str) or not part for part in self.command)
        ):
            raise CyberOSError(ErrorCode.COMMAND_SANITIZATION_FAILED, "argv command is invalid.")
        if not isinstance(self.environment, tuple) or any(
            not isinstance(pair, tuple)
            or len(pair) != 2
            or not all(isinstance(item, str) for item in pair)
            for pair in self.environment
        ):
            raise CyberOSError(
                ErrorCode.COMMAND_SANITIZATION_FAILED, "Environment entries are invalid."
            )
        if len({key for key, _ in self.environment}) != len(self.environment):
            raise CyberOSError(
                ErrorCode.COMMAND_SANITIZATION_FAILED, "Environment keys are duplicated."
            )
        limits = (
            self.timeout_seconds,
            self.max_stdout_bytes,
            self.max_stderr_bytes,
            self.max_argument_bytes,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in limits
        ):
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_LIMIT_EXCEEDED, "Live adapter limits are invalid."
            )


@dataclass(frozen=True, slots=True)
class ValidatedCommandPlan:
    executable: ApprovedExecutable
    argv: tuple[str, ...]
    sanitized_environment: tuple[tuple[str, str], ...]
    working_directory: str | os.PathLike[str] | None
    timeout_seconds: int
    stdout_limit: int
    stderr_limit: int
    target_binding_digest: str


@dataclass(frozen=True, slots=True)
class BoundedProcessReceipt:
    executable_id: str
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    stdout_truncated: bool
    stderr_truncated: bool
    timeout_exceeded: bool
    termination: TerminationKind
    duration_ms: int
    output_digest: str
    redaction_applied: bool
    failure_code: ErrorCode | None = None

    def __post_init__(self) -> None:
        _safe_text(self.executable_id, "executable identity", 128)
        if not isinstance(self.stdout, bytes) or not isinstance(self.stderr, bytes):
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_OUTPUT_INVALID, "Bounded output must be bytes."
            )
        if not isinstance(self.termination, TerminationKind):
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_OUTPUT_INVALID, "Termination state is invalid."
            )
        if (
            not isinstance(self.duration_ms, int)
            or isinstance(self.duration_ms, bool)
            or self.duration_ms < 0
        ):
            raise CyberOSError(ErrorCode.LIVE_ADAPTER_OUTPUT_INVALID, "Duration is invalid.")
        if len(self.output_digest) != 64 or any(
            character not in "0123456789abcdef" for character in self.output_digest
        ):
            raise CyberOSError(ErrorCode.LIVE_ADAPTER_OUTPUT_INVALID, "Output digest is invalid.")
        if not self.redaction_applied:
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_OUTPUT_INVALID, "Output redaction is required."
            )
        if self.timeout_exceeded and self.failure_code is not ErrorCode.SUBPROCESS_TIMEOUT:
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_OUTPUT_INVALID, "Timeout failure code is invalid."
            )
        if (
            (self.stdout_truncated or self.stderr_truncated)
            and not self.timeout_exceeded
            and (self.failure_code is not ErrorCode.LIVE_ADAPTER_LIMIT_EXCEEDED)
        ):
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_OUTPUT_INVALID, "Truncation failure code is invalid."
            )


class CommandSandbox:
    """Pure deny-by-default validator for one host-created live request."""

    _SHELL_META = _SHELL_META_RE

    def __init__(self, executables: Mapping[str, ApprovedExecutable]) -> None:
        self.executables = dict(executables)

    def validate(
        self,
        request: LiveSubprocessRequest,
        *,
        now: datetime | None = None,
    ) -> ValidatedCommandPlan:
        timestamp = ensure_utc(now) if now is not None else utc_now()
        if request.task.status.value != "pending":
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_UNAUTHORIZED, "Live adapter requires a pending Task."
            )
        if (
            request.scope_id != request.task.scope_id
            or request.scope_id != request.authorization.scope_id
            or request.target_id != request.task.target_id
            or request.target_id != request.authorization.matched_target_id
        ):
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_UNAUTHORIZED, "Live adapter context does not align."
            )
        if request.authorization.matching_rule is not TargetRule.INCLUDE:
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_UNAUTHORIZED, "Live adapter requires Include authorization."
            )
        if (
            request.authorization.expires_at is not None
            and request.authorization.expires_at <= timestamp
        ):
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_UNAUTHORIZED, "Live adapter authorization has expired."
            )
        if request.canonical_target != request.authorization.candidate.raw_value:
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_UNAUTHORIZED, "Live adapter target context does not align."
            )
        if request.command != request.task.execution_spec.command:
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_UNAUTHORIZED, "Live adapter command does not match Task."
            )
        executable = self.executables.get(request.allowed_executable_id)
        if executable is None:
            raise CyberOSError(
                ErrorCode.COMMAND_SANITIZATION_FAILED, "Executable is not allowlisted."
            )
        if request.target_kind not in executable.supported_target_kinds:
            raise CyberOSError(
                ErrorCode.COMMAND_SANITIZATION_FAILED, "Target kind is not supported by executable."
            )
        if request.command[0] != executable.executable or not os.path.isabs(request.command[0]):
            raise CyberOSError(
                ErrorCode.COMMAND_SANITIZATION_FAILED, "Executable identity is invalid."
            )
        if (
            executable.command_prefix
            and request.command[: len(executable.command_prefix)] != executable.command_prefix
        ):
            raise CyberOSError(
                ErrorCode.COMMAND_SANITIZATION_FAILED, "Command prefix is not allowlisted."
            )
        if (
            executable.require_target_argument
            and request.canonical_target not in request.command[1:]
        ):
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_CONTEXT_MISMATCH, "Authorized target is absent from argv."
            )
        for index, argument in enumerate(request.command):
            _safe_text(argument, "argv argument", 16_384)
            if index not in executable.opaque_argument_indexes and self._SHELL_META.search(
                argument
            ):
                raise CyberOSError(
                    ErrorCode.COMMAND_SANITIZATION_FAILED, "Shell syntax is not permitted in argv."
                )
        argument_bytes = sum(len(argument.encode("utf-8")) for argument in request.command)
        if argument_bytes > request.max_argument_bytes:
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_LIMIT_EXCEEDED, "Argument byte budget exceeded."
            )
        if request.timeout_seconds > min(
            request.task.execution_spec.timeout_seconds, executable.max_timeout_seconds
        ):
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_LIMIT_EXCEEDED, "Timeout exceeds approved limit."
            )
        if request.max_stdout_bytes > min(
            request.task.execution_spec.max_output_bytes, executable.max_output_bytes
        ):
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_LIMIT_EXCEEDED, "stdout limit exceeds approved limit."
            )
        if request.max_stderr_bytes > min(
            request.task.execution_spec.max_output_bytes, executable.max_output_bytes
        ):
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_LIMIT_EXCEEDED, "stderr limit exceeds approved limit."
            )
        allowed_environment = set(executable.allowed_environment_keys).intersection(
            request.task.execution_spec.env_policy.allowed_keys
        )
        if any(
            key not in allowed_environment or _CONTROL_RE.search(key) or _CONTROL_RE.search(value)
            for key, value in request.environment
        ):
            raise CyberOSError(
                ErrorCode.COMMAND_SANITIZATION_FAILED, "Environment key is not allowlisted."
            )
        if request.working_directory is not None:
            raise CyberOSError(
                ErrorCode.COMMAND_SANITIZATION_FAILED, "Working directories are not enabled."
            )
        binding = (
            f"{request.scope_id}:{request.target_id}:{request.task.id}:"
            f"{request.allowed_executable_id}"
        )
        return ValidatedCommandPlan(
            executable,
            request.command,
            tuple(sorted(request.environment)),
            request.working_directory,
            request.timeout_seconds,
            request.max_stdout_bytes,
            request.max_stderr_bytes,
            hashlib.sha256(binding.encode("utf-8")).hexdigest(),
        )


class LiveSubprocessAdapter:
    """Run one validated local process through the existing safe runner."""

    def __init__(
        self,
        sandbox: CommandSandbox,
        *,
        runner: SafeSubprocessRunner | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.sandbox = sandbox
        self.runner = runner or SafeSubprocessRunner()
        self.clock = clock

    async def run(self, request: LiveSubprocessRequest) -> BoundedProcessReceipt:
        plan = self.sandbox.validate(request, now=self.clock())
        spec = ExecutionSpec(
            command=plan.argv,
            timeout_seconds=plan.timeout_seconds,
            max_output_bytes=max(plan.stdout_limit, plan.stderr_limit),
            env_policy=EnvPolicy(tuple(key for key, _ in plan.sanitized_environment)),
        )
        started = time.monotonic()
        try:
            result = await self.runner.run(
                spec,
                environment=dict(plan.sanitized_environment),
                cwd=plan.working_directory,
            )
        except CyberOSError as error:
            if error.code is ErrorCode.EXECUTION_START_FAILED:
                raise CyberOSError(
                    ErrorCode.LIVE_ADAPTER_START_FAILED, "Live adapter process could not start."
                ) from error
            raise
        stdout = _redact(result.stdout[: plan.stdout_limit])
        stderr = _redact(result.stderr[: plan.stderr_limit])
        timeout = result.timeout_exceeded
        truncated_stdout = result.truncated and len(result.stdout) >= plan.stdout_limit
        truncated_stderr = result.truncated and len(result.stderr) >= plan.stderr_limit
        failure_code = (
            ErrorCode.SUBPROCESS_TIMEOUT
            if timeout
            else (
                ErrorCode.LIVE_ADAPTER_LIMIT_EXCEEDED
                if truncated_stdout or truncated_stderr
                else None
            )
        )
        termination = TerminationKind.TIMEOUT if timeout else TerminationKind.EXITED
        digest = hashlib.sha256(stdout + b"\x00" + stderr).hexdigest()
        return BoundedProcessReceipt(
            executable_id=plan.executable.logical_id,
            exit_code=result.exit_code,
            stdout=stdout,
            stderr=stderr,
            stdout_truncated=truncated_stdout,
            stderr_truncated=truncated_stderr,
            timeout_exceeded=timeout,
            termination=termination,
            duration_ms=max(0, int((time.monotonic() - started) * 1000)),
            output_digest=digest,
            redaction_applied=True,
            failure_code=failure_code,
        )


def _redact(value: bytes) -> bytes:
    text = value.decode("utf-8", errors="replace")
    text = _SECRET_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    text = _PATH_RE.sub("[PATH_REDACTED]", text)
    text = _OUTPUT_CONTROL_RE.sub("", text)
    return text.encode("utf-8")
