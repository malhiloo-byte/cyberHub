"""Safe, declarative execution specifications; this module never executes commands."""

from __future__ import annotations

from dataclasses import dataclass

from cyberos.core.errors import CyberOSError, ErrorCode

DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 3600
DEFAULT_MAX_OUTPUT_BYTES = 1_048_576
MAX_OUTPUT_BYTES = 16_777_216


@dataclass(frozen=True, slots=True)
class EnvPolicy:
    """Allowlist policy for a future executor's inherited environment."""

    allowed_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.allowed_keys, tuple):
            raise CyberOSError(
                ErrorCode.EXECUTION_SPEC_INVALID,
                "EnvPolicy allowed_keys must be a tuple.",
            )
        if any(not isinstance(key, str) or not key or "=" in key for key in self.allowed_keys):
            raise CyberOSError(
                ErrorCode.EXECUTION_SPEC_INVALID,
                "EnvPolicy keys must be non-empty environment names without '='.",
            )
        if len(set(self.allowed_keys)) != len(self.allowed_keys):
            raise CyberOSError(
                ErrorCode.EXECUTION_SPEC_INVALID,
                "EnvPolicy keys must be unique.",
            )


@dataclass(frozen=True, slots=True)
class ExecutionSpec:
    """Declarative command limits for a future argv-based executor."""

    command: tuple[str, ...]
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES
    env_policy: EnvPolicy = EnvPolicy()

    def __post_init__(self) -> None:
        if not isinstance(self.command, tuple) or not self.command:
            raise CyberOSError(
                ErrorCode.EXECUTION_SPEC_INVALID,
                "ExecutionSpec command must be a non-empty tuple.",
            )
        if any(not isinstance(part, str) or not part for part in self.command):
            raise CyberOSError(
                ErrorCode.EXECUTION_SPEC_INVALID,
                "ExecutionSpec command parts must be non-empty strings.",
            )
        if not isinstance(self.timeout_seconds, int) or not (
            1 <= self.timeout_seconds <= MAX_TIMEOUT_SECONDS
        ):
            raise CyberOSError(
                ErrorCode.EXECUTION_SPEC_INVALID,
                f"timeout_seconds must be between 1 and {MAX_TIMEOUT_SECONDS}.",
            )
        if not isinstance(self.max_output_bytes, int) or not (
            1 <= self.max_output_bytes <= MAX_OUTPUT_BYTES
        ):
            raise CyberOSError(
                ErrorCode.EXECUTION_SPEC_INVALID,
                f"max_output_bytes must be between 1 and {MAX_OUTPUT_BYTES}.",
            )
        if not isinstance(self.env_policy, EnvPolicy):
            raise CyberOSError(
                ErrorCode.EXECUTION_SPEC_INVALID,
                "ExecutionSpec env_policy must be an EnvPolicy.",
            )
