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
    DATABASE_PATH_INVALID = "DATABASE_PATH_INVALID"
    DATABASE_PARENT_NOT_WRITABLE = "DATABASE_PARENT_NOT_WRITABLE"
    DATABASE_PERMISSION_POLICY_FAILED = "DATABASE_PERMISSION_POLICY_FAILED"
    DATABASE_SYMLINK_UNSAFE = "DATABASE_SYMLINK_UNSAFE"
    DATABASE_OPEN_FAILED = "DATABASE_OPEN_FAILED"
    DATABASE_BUSY = "DATABASE_BUSY"
    DATABASE_PRAGMA_FAILED = "DATABASE_PRAGMA_FAILED"
    DATABASE_PRAGMA_MISMATCH = "DATABASE_PRAGMA_MISMATCH"
    DATABASE_CONNECTION_CLOSED = "DATABASE_CONNECTION_CLOSED"
    DATABASE_INTEGRITY_FAILED = "DATABASE_INTEGRITY_FAILED"


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
    ErrorCode.DATABASE_PATH_INVALID: 3,
    ErrorCode.DATABASE_PARENT_NOT_WRITABLE: 3,
    ErrorCode.DATABASE_PERMISSION_POLICY_FAILED: 3,
    ErrorCode.DATABASE_SYMLINK_UNSAFE: 3,
    ErrorCode.DATABASE_OPEN_FAILED: 3,
    ErrorCode.DATABASE_BUSY: 3,
    ErrorCode.DATABASE_PRAGMA_FAILED: 3,
    ErrorCode.DATABASE_PRAGMA_MISMATCH: 3,
    ErrorCode.DATABASE_CONNECTION_CLOSED: 3,
    ErrorCode.DATABASE_INTEGRITY_FAILED: 3,
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
