"""Neutral immutable execution result contract shared by execution and persistence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ExecutionFailureReason(StrEnum):
    """Machine-readable reasons for a non-normal execution outcome."""

    TIMEOUT_EXCEEDED = "TIMEOUT_EXCEEDED"


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Immutable, bounded result returned by a local execution boundary."""

    exit_code: int | None
    stdout: bytes
    stderr: bytes
    truncated: bool
    duration_seconds: float
    timeout_exceeded: bool
    failure_reason: ExecutionFailureReason | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.stdout, bytes) or not isinstance(self.stderr, bytes):
            raise TypeError("ExecutionResult streams must be bytes")
        if self.duration_seconds < 0:
            raise ValueError("ExecutionResult duration cannot be negative")
        if self.timeout_exceeded and (
            self.failure_reason is not ExecutionFailureReason.TIMEOUT_EXCEEDED
        ):
            raise ValueError("Timed-out results must use TIMEOUT_EXCEEDED")
        if not self.timeout_exceeded and self.failure_reason is not None:
            raise ValueError("Non-timeout results cannot carry a failure reason")
        if self.error_message is not None and not self.error_message.strip():
            raise ValueError("ExecutionResult error_message cannot be blank")
