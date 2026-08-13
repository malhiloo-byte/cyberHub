from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorSeverity(StrEnum):
    ERROR = "error"
    CRITICAL = "critical"


class ErrorCode(StrEnum):
    CONFIG_NOT_FOUND = "CONFIG_NOT_FOUND"
    CONFIG_INVALID = "CONFIG_INVALID"
    RUNTIME_UNSUPPORTED = "RUNTIME_UNSUPPORTED"
    PATH_NOT_WRITABLE = "PATH_NOT_WRITABLE"
    SERIALIZATION_FAILED = "SERIALIZATION_FAILED"
    INVALID_INPUT = "INVALID_INPUT"
    PLUGIN_MANIFEST_INVALID = "PLUGIN_MANIFEST_INVALID"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    OPERATION_CANCELLED = "OPERATION_CANCELLED"


EXIT_CODES: dict[ErrorCode, int] = {
    ErrorCode.CONFIG_NOT_FOUND: 2,
    ErrorCode.CONFIG_INVALID: 2,
    ErrorCode.RUNTIME_UNSUPPORTED: 3,
    ErrorCode.PATH_NOT_WRITABLE: 3,
    ErrorCode.SERIALIZATION_FAILED: 4,
    ErrorCode.INVALID_INPUT: 4,
    ErrorCode.PLUGIN_MANIFEST_INVALID: 5,
    ErrorCode.INTERNAL_ERROR: 10,
    ErrorCode.OPERATION_CANCELLED: 130,
}


class CyberOSError(Exception):
    """Safe, typed application error suitable for CLI/API boundaries."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.retryable = retryable
        self.severity = severity

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.code]
