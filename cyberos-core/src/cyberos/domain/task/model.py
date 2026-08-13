"""Immutable Task aggregate with authorization-bound creation and strict lifecycle."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.time import ensure_utc, utc_now
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.primitives import TargetId, TargetRule
from cyberos.domain.task.primitives import TaskId, TaskStatus, new_task_id
from cyberos.domain.task.spec import ExecutionSpec


@runtime_checkable
class ExecutionAuthorizationContract(Protocol):
    """Structural contract accepted from the application authorization boundary."""

    scope_id: ScopeId
    matched_target_id: TargetId
    matching_rule: TargetRule
    expires_at: datetime | None


class Task(BaseModel):
    """A scheduled/executable unit; construction requires a valid authorization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: TaskId = Field(default_factory=new_task_id)
    scope_id: ScopeId
    target_id: TargetId
    status: TaskStatus = TaskStatus.PENDING
    execution_spec: ExecutionSpec
    authorization_expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failed_at: datetime | None = None
    cancelled_at: datetime | None = None
    version: int = Field(default=1, ge=1)

    ALLOWED_TRANSITIONS: ClassVar[dict[TaskStatus, frozenset[TaskStatus]]] = {
        TaskStatus.PENDING: frozenset({TaskStatus.RUNNING, TaskStatus.CANCELLED}),
        TaskStatus.RUNNING: frozenset(
            {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}
        ),
        TaskStatus.COMPLETED: frozenset(),
        TaskStatus.FAILED: frozenset(),
        TaskStatus.CANCELLED: frozenset(),
    }

    @field_validator("scope_id", "target_id")
    @classmethod
    def validate_uuid4(cls, value: UUID) -> UUID:
        if value.version != 4:
            raise ValueError("Task identifiers must be UUID4")
        return value

    @field_validator(
        "created_at",
        "updated_at",
        "started_at",
        "completed_at",
        "failed_at",
        "cancelled_at",
        "authorization_expires_at",
    )
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value) if value is not None else None

    @model_validator(mode="after")
    def validate_invariants(self) -> Task:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        if self.authorization_expires_at is not None and (
            self.authorization_expires_at <= self.created_at
        ):
            raise ValueError("authorization_expires_at must be later than task creation")
        if self.status is TaskStatus.PENDING and any(
            timestamp is not None
            for timestamp in (self.started_at, self.completed_at, self.failed_at, self.cancelled_at)
        ):
            raise ValueError("pending Task cannot have execution timestamps")
        if self.status is TaskStatus.RUNNING and self.started_at is None:
            raise ValueError("running Task requires started_at")
        if self.status is TaskStatus.COMPLETED and self.completed_at is None:
            raise ValueError("completed Task requires completed_at")
        if self.status is TaskStatus.FAILED and self.failed_at is None:
            raise ValueError("failed Task requires failed_at")
        if self.status is TaskStatus.CANCELLED and self.cancelled_at is None:
            raise ValueError("cancelled Task requires cancelled_at")
        return self

    @classmethod
    def create(
        cls,
        scope_id: ScopeId,
        target_id: TargetId,
        authorization: ExecutionAuthorizationContract,
        execution_spec: ExecutionSpec,
        *,
        now: datetime | None = None,
        task_id: TaskId | None = None,
    ) -> Task:
        if not isinstance(authorization, ExecutionAuthorizationContract):
            raise CyberOSError(
                ErrorCode.TASK_AUTHORIZATION_REQUIRED,
                "Task creation requires ExecutionAuthorization.",
            )
        if scope_id != authorization.scope_id:
            raise CyberOSError(
                ErrorCode.TASK_AUTHORIZATION_SCOPE_MISMATCH,
                "Task Scope does not match ExecutionAuthorization Scope.",
            )
        if target_id != authorization.matched_target_id:
            raise CyberOSError(
                ErrorCode.TASK_AUTHORIZATION_TARGET_MISMATCH,
                "Task Target does not match ExecutionAuthorization Target.",
            )
        timestamp = ensure_utc(now) if now is not None else utc_now()
        if authorization.expires_at is not None and authorization.expires_at <= timestamp:
            raise CyberOSError(
                ErrorCode.TASK_AUTHORIZATION_EXPIRED,
                "ExecutionAuthorization has expired.",
            )
        if authorization.matching_rule is not TargetRule.INCLUDE:
            raise CyberOSError(
                ErrorCode.TASK_AUTHORIZATION_REQUIRED,
                "Task creation requires an Include authorization.",
            )
        return cls(
            id=task_id or new_task_id(),
            scope_id=scope_id,
            target_id=target_id,
            execution_spec=execution_spec,
            authorization_expires_at=authorization.expires_at,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def transition(self, target_status: TaskStatus, *, at: datetime | None = None) -> Task:
        if target_status not in self.ALLOWED_TRANSITIONS[self.status]:
            raise CyberOSError(
                ErrorCode.TASK_INVALID_TRANSITION,
                f"Task cannot transition from {self.status.value} to {target_status.value}.",
            )
        timestamp = ensure_utc(at) if at is not None else utc_now()
        values = self.model_dump()
        values.update(status=target_status, updated_at=timestamp, version=self.version + 1)
        if target_status is TaskStatus.RUNNING:
            values["started_at"] = timestamp
        elif target_status is TaskStatus.COMPLETED:
            values["completed_at"] = timestamp
        elif target_status is TaskStatus.FAILED:
            values["failed_at"] = timestamp
        elif target_status is TaskStatus.CANCELLED:
            values["cancelled_at"] = timestamp
        return Task.model_validate(values)
