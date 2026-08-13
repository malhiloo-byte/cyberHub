from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.ids import new_id
from cyberos.core.time import ensure_utc, utc_now
from cyberos.domain.engagement.primitives import (
    EngagementId,
    normalize_authorization_reference,
    normalize_engagement_description,
    normalize_engagement_name,
)
from cyberos.domain.workspace.primitives import WorkspaceId


class EngagementKind(StrEnum):
    LEARNING = "learning"
    AUTHORIZED_ASSESSMENT = "authorized_assessment"
    RESEARCH = "research"


class EngagementStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class Engagement(BaseModel):
    """Immutable Engagement aggregate entity without persistence concerns."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: EngagementId = Field(default_factory=new_id)
    workspace_id: WorkspaceId
    name: str
    kind: EngagementKind
    status: EngagementStatus = EngagementStatus.DRAFT
    description: str = ""
    authorization_reference: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    archived_at: datetime | None = None
    version: int = Field(default=1, ge=1)

    ALLOWED_TRANSITIONS: ClassVar[dict[EngagementStatus, frozenset[EngagementStatus]]] = {
        EngagementStatus.DRAFT: frozenset({EngagementStatus.ACTIVE, EngagementStatus.ARCHIVED}),
        EngagementStatus.ACTIVE: frozenset(
            {EngagementStatus.PAUSED, EngagementStatus.COMPLETED, EngagementStatus.ARCHIVED}
        ),
        EngagementStatus.PAUSED: frozenset(
            {EngagementStatus.ACTIVE, EngagementStatus.COMPLETED, EngagementStatus.ARCHIVED}
        ),
        EngagementStatus.COMPLETED: frozenset({EngagementStatus.ARCHIVED}),
        EngagementStatus.ARCHIVED: frozenset(),
    }

    @field_validator("id", "workspace_id")
    @classmethod
    def validate_uuid4(cls, value: UUID) -> UUID:
        if value.version != 4:
            raise ValueError("Engagement and workspace identifiers must be UUID4")
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_engagement_name(value)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        return normalize_engagement_description(value)

    @field_validator("authorization_reference")
    @classmethod
    def validate_authorization_reference(cls, value: str | None) -> str | None:
        return normalize_authorization_reference(value)

    @field_validator("created_at", "updated_at", "start_at", "end_at", "archived_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value) if value is not None else None

    @model_validator(mode="after")
    def validate_invariants(self) -> Engagement:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        if self.end_at is not None and self.start_at is not None and self.end_at < self.start_at:
            raise ValueError("end_at cannot be earlier than start_at")
        if self.status is EngagementStatus.ARCHIVED and self.archived_at is None:
            raise ValueError("archived engagement must have archived_at")
        if self.status is not EngagementStatus.ARCHIVED and self.archived_at is not None:
            raise ValueError("non-archived engagement cannot have archived_at")
        if (
            self.status is EngagementStatus.ACTIVE
            and self.kind is EngagementKind.AUTHORIZED_ASSESSMENT
            and not self.authorization_reference
        ):
            raise ValueError("authorized assessment requires authorization_reference when active")
        if self.status is EngagementStatus.COMPLETED and self.end_at is None:
            raise ValueError("completed engagement must have end_at")
        return self

    @classmethod
    def create(
        cls,
        workspace_id: WorkspaceId,
        name: str,
        kind: EngagementKind,
        description: str = "",
        authorization_reference: str | None = None,
        *,
        engagement_id: EngagementId | None = None,
        start_at: datetime | None = None,
        now: datetime | None = None,
    ) -> Engagement:
        timestamp = ensure_utc(now) if now is not None else utc_now()
        return cls._validated(
            id=engagement_id or new_id(),
            workspace_id=workspace_id,
            name=name,
            kind=kind,
            status=EngagementStatus.DRAFT,
            description=description,
            authorization_reference=authorization_reference,
            start_at=start_at,
            end_at=None,
            created_at=timestamp,
            updated_at=timestamp,
            archived_at=None,
            version=1,
        )

    def transition(
        self,
        target: EngagementStatus,
        *,
        at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> Engagement:
        if target not in self.ALLOWED_TRANSITIONS[self.status]:
            code = (
                ErrorCode.ENGAGEMENT_ALREADY_ARCHIVED
                if self.status is EngagementStatus.ARCHIVED
                else ErrorCode.ENGAGEMENT_INVALID_TRANSITION
            )
            raise CyberOSError(
                code,
                "The requested Engagement status transition is not allowed.",
                details={"from": self.status.value, "to": target.value},
            )
        timestamp = ensure_utc(at) if at is not None else utc_now()
        effective_end = ensure_utc(end_at) if end_at is not None else self.end_at
        if (
            target is EngagementStatus.ACTIVE
            and self.kind is EngagementKind.AUTHORIZED_ASSESSMENT
            and not self.authorization_reference
        ):
            raise CyberOSError(
                ErrorCode.ENGAGEMENT_AUTHORIZATION_REQUIRED,
                "An authorization reference is required before activation.",
            )
        if target is EngagementStatus.COMPLETED and effective_end is None:
            raise CyberOSError(
                ErrorCode.ENGAGEMENT_COMPLETION_REQUIRES_END_AT,
                "An end timestamp is required before completion.",
            )
        values = self.model_dump()
        values.update(
            status=target,
            updated_at=timestamp,
            end_at=effective_end,
            archived_at=timestamp if target is EngagementStatus.ARCHIVED else None,
            version=self.version + 1,
        )
        return self._validated(**values)

    def archive(self, *, at: datetime | None = None) -> Engagement:
        return self.transition(EngagementStatus.ARCHIVED, at=at)

    @classmethod
    def _validated(cls, **values: Any) -> Engagement:
        try:
            return cls.model_validate(values)
        except ValidationError as exc:
            fields = [".".join(str(part) for part in error["loc"]) for error in exc.errors()]
            raise CyberOSError(
                ErrorCode.DOMAIN_VALIDATION_FAILED,
                "Engagement validation failed.",
                details={"fields": fields},
            ) from exc
