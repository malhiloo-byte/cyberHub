"""SQL-independent Task persistence port."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.primitives import TargetId
from cyberos.domain.task.primitives import TaskId
from cyberos.domain.task.record import TaskRecord


class TaskRepository(Protocol):
    """Persistence contract for Task snapshots and execution results."""

    def add(self, record: TaskRecord) -> TaskRecord: ...

    def get(self, task_id: TaskId) -> TaskRecord | None: ...

    def list_by_scope(self, scope_id: ScopeId) -> Sequence[TaskRecord]: ...

    def list_by_target(self, target_id: TargetId) -> Sequence[TaskRecord]: ...

    def update_status_and_result(
        self,
        record: TaskRecord,
        *,
        expected_version: int,
    ) -> TaskRecord: ...
