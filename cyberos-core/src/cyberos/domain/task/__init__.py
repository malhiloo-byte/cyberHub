"""Task domain primitives, execution specifications, and aggregate."""

from cyberos.domain.task.model import Task
from cyberos.domain.task.primitives import TaskId, TaskStatus, new_task_id, validate_task_id
from cyberos.domain.task.record import TaskRecord
from cyberos.domain.task.result import ExecutionFailureReason, ExecutionResult
from cyberos.domain.task.spec import EnvPolicy, ExecutionSpec

__all__ = [
    "EnvPolicy",
    "ExecutionSpec",
    "ExecutionFailureReason",
    "ExecutionResult",
    "Task",
    "TaskRecord",
    "TaskId",
    "TaskStatus",
    "new_task_id",
    "validate_task_id",
]
