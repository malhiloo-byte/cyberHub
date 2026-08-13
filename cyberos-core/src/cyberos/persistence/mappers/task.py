"""SQLite mapping for immutable TaskRecord snapshots."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any
from uuid import UUID

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.primitives import TargetId
from cyberos.domain.task.model import Task
from cyberos.domain.task.primitives import TaskId, TaskStatus
from cyberos.domain.task.record import TaskRecord
from cyberos.domain.task.result import ExecutionFailureReason, ExecutionResult
from cyberos.domain.task.spec import EnvPolicy, ExecutionSpec

TASK_COLUMNS = (
    "id",
    "scope_id",
    "target_id",
    "status",
    "command_json",
    "timeout_seconds",
    "max_output_bytes",
    "env_policy_json",
    "authorization_expires_at",
    "created_at",
    "updated_at",
    "started_at",
    "completed_at",
    "failed_at",
    "cancelled_at",
    "version",
    "exit_code",
    "stdout",
    "stderr",
    "truncated",
    "duration_ms",
    "timeout_exceeded",
    "error_message",
)


def task_record_to_params(record: TaskRecord) -> tuple[Any, ...]:
    task = record.task
    result = record.result
    return (
        str(task.id),
        str(task.scope_id),
        str(task.target_id),
        task.status.value,
        json.dumps(list(task.execution_spec.command), ensure_ascii=False, separators=(",", ":")),
        task.execution_spec.timeout_seconds,
        task.execution_spec.max_output_bytes,
        json.dumps(list(task.execution_spec.env_policy.allowed_keys), separators=(",", ":")),
        _timestamp(task.authorization_expires_at),
        task.created_at.isoformat(),
        task.updated_at.isoformat(),
        _timestamp(task.started_at),
        _timestamp(task.completed_at),
        _timestamp(task.failed_at),
        _timestamp(task.cancelled_at),
        task.version,
        result.exit_code if result is not None else None,
        result.stdout if result is not None else None,
        result.stderr if result is not None else None,
        int(result.truncated) if result is not None else None,
        _duration_ms(result) if result is not None else None,
        int(result.timeout_exceeded) if result is not None else None,
        _error_message(result),
    )


def task_record_from_row(row: sqlite3.Row) -> TaskRecord:
    payload = {column: row[column] for column in TASK_COLUMNS}
    try:
        command = _json_string_list(payload["command_json"], "command_json")
        env_keys = _json_string_list(payload["env_policy_json"], "env_policy_json")
        execution_spec = ExecutionSpec(
            command=tuple(command),
            timeout_seconds=int(payload["timeout_seconds"]),
            max_output_bytes=int(payload["max_output_bytes"]),
            env_policy=EnvPolicy(allowed_keys=tuple(env_keys)),
        )
        task = Task.model_validate(
            {
                "id": TaskId(_uuid(payload["id"], "id")),
                "scope_id": ScopeId(_uuid(payload["scope_id"], "scope_id")),
                "target_id": TargetId(_uuid(payload["target_id"], "target_id")),
                "status": TaskStatus(payload["status"]),
                "execution_spec": execution_spec,
                "authorization_expires_at": _datetime(payload["authorization_expires_at"]),
                "created_at": _datetime(payload["created_at"]),
                "updated_at": _datetime(payload["updated_at"]),
                "started_at": _datetime(payload["started_at"]),
                "completed_at": _datetime(payload["completed_at"]),
                "failed_at": _datetime(payload["failed_at"]),
                "cancelled_at": _datetime(payload["cancelled_at"]),
                "version": int(payload["version"]),
            }
        )
        result = _result_from_payload(payload)
        return TaskRecord(task=task, result=result)
    except CyberOSError:
        raise
    except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise CyberOSError(
            ErrorCode.PERSISTENCE_MAPPING_FAILED,
            "A stored Task row failed domain mapping validation.",
        ) from exc


def _result_from_payload(payload: dict[str, Any]) -> ExecutionResult | None:
    result_fields = (
        payload["exit_code"],
        payload["stdout"],
        payload["stderr"],
        payload["truncated"],
        payload["duration_ms"],
        payload["timeout_exceeded"],
        payload["error_message"],
    )
    if all(value is None for value in result_fields):
        return None
    if any(value is None for value in result_fields[0:6]):
        raise ValueError("Stored execution result is incomplete")
    stdout = payload["stdout"]
    stderr = payload["stderr"]
    if not isinstance(stdout, bytes) or not isinstance(stderr, bytes):
        raise TypeError("Stored execution streams must be bytes")
    timeout_exceeded = bool(payload["timeout_exceeded"])
    error_message = payload["error_message"]
    if error_message is not None and not isinstance(error_message, str):
        raise TypeError("Stored execution error message must be text")
    return ExecutionResult(
        exit_code=int(payload["exit_code"]),
        stdout=stdout,
        stderr=stderr,
        truncated=bool(payload["truncated"]),
        duration_seconds=int(payload["duration_ms"]) / 1000,
        timeout_exceeded=timeout_exceeded,
        failure_reason=(ExecutionFailureReason.TIMEOUT_EXCEEDED if timeout_exceeded else None),
        error_message=error_message,
    )


def _json_string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, str):
        raise TypeError(f"Stored {field} must be JSON text")
    decoded = json.loads(value)
    if not isinstance(decoded, list) or any(not isinstance(item, str) for item in decoded):
        raise ValueError(f"Stored {field} must be a JSON string array")
    return decoded


def _uuid(value: Any, field: str) -> UUID:
    if not isinstance(value, str):
        raise TypeError(f"Stored {field} must be text")
    return UUID(value)


def _datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("Stored timestamp must be text")
    return datetime.fromisoformat(value)


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _duration_ms(result: ExecutionResult) -> int:
    return int(round(result.duration_seconds * 1000))


def _error_message(result: ExecutionResult | None) -> str | None:
    if result is None:
        return None
    if result.error_message is not None:
        return result.error_message
    return result.failure_reason.value if result.failure_reason is not None else None
