from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from cyberos.core.context import OperationContext
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.result import OperationResult
from cyberos.logging.setup import bind_context

T = TypeVar("T")


def execute_service(
    operation: Callable[[], T],
    *,
    context: OperationContext | None = None,
) -> OperationResult[T]:
    """Run a service operation and convert failures to a stable result envelope."""

    operation_context = context or OperationContext()
    bind_context(
        correlation_id=str(operation_context.correlation_id),
        operation_id=str(operation_context.operation_id),
    )
    started_at = time.perf_counter()
    try:
        return OperationResult.success(operation(), operation_context, started_at)
    except CyberOSError as error:
        return OperationResult.failure(error, operation_context, started_at)
    except Exception:  # pragma: no cover - safety boundary tested through typed failures
        safe_error = CyberOSError(
            ErrorCode.INTERNAL_ERROR,
            "The operation failed unexpectedly; no internal details were exposed.",
        )
        return OperationResult.failure(safe_error, operation_context, started_at)
