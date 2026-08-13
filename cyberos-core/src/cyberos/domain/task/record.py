"""Persistence-neutral projection of a Task snapshot and its execution result."""

from __future__ import annotations

from dataclasses import dataclass

from cyberos.domain.task.model import Task
from cyberos.domain.task.primitives import TaskStatus
from cyberos.domain.task.result import ExecutionResult


@dataclass(frozen=True, slots=True)
class TaskRecord:
    """Immutable row projection; persistence adapters map it to storage."""

    task: Task
    result: ExecutionResult | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.task, Task):
            raise TypeError("TaskRecord.task must be a Task")
        if self.task.status in (TaskStatus.PENDING, TaskStatus.RUNNING) and self.result is not None:
            raise ValueError("Pending or running Tasks cannot have an execution result")
        if self.task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED) and self.result is None:
            raise ValueError("Completed or failed Tasks require an execution result")
