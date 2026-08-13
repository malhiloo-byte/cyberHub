from __future__ import annotations

import time
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from cyberos.core.context import OperationContext
from cyberos.core.errors import CyberOSError, ErrorSeverity

T = TypeVar("T")


class ResultMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    correlation_id: str
    duration_ms: int = Field(ge=0)


class ErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    retryable: bool = False
    severity: str = ErrorSeverity.ERROR.value


class OperationResult(BaseModel, Generic[T]):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    data: T | None = None
    error: ErrorPayload | None = None
    meta: ResultMeta

    @classmethod
    def success(cls, data: T, context: OperationContext, started_at: float) -> OperationResult[T]:
        duration_ms = max(0, round((time.perf_counter() - started_at) * 1000))
        return cls(
            ok=True,
            data=data,
            meta=ResultMeta(correlation_id=str(context.correlation_id), duration_ms=duration_ms),
        )

    @classmethod
    def failure(
        cls, error: CyberOSError, context: OperationContext, started_at: float
    ) -> OperationResult[T]:
        duration_ms = max(0, round((time.perf_counter() - started_at) * 1000))
        return cls(
            ok=False,
            error=ErrorPayload(
                code=error.code.value,
                message=error.message,
                details=error.details,
                retryable=error.retryable,
                severity=error.severity.value,
            ),
            meta=ResultMeta(correlation_id=str(context.correlation_id), duration_ms=duration_ms),
        )
