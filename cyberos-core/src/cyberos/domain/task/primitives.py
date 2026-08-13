"""Typed Task identifiers and lifecycle status values."""

from enum import StrEnum
from typing import NewType
from uuid import UUID

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.ids import new_id

TaskId = NewType("TaskId", UUID)


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


def validate_task_id(value: UUID) -> TaskId:
    if not isinstance(value, UUID) or value.version != 4:
        raise CyberOSError(
            ErrorCode.DOMAIN_VALIDATION_FAILED,
            "Task identifier must be a UUID4.",
            details={"field": "task_id"},
        )
    return TaskId(value)


def new_task_id() -> TaskId:
    return TaskId(new_id())
