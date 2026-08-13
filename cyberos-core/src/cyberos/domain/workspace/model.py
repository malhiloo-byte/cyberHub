from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.ids import new_id
from cyberos.core.time import ensure_utc, utc_now
from cyberos.domain.workspace.primitives import (
    WorkspaceId,
    normalize_workspace_description,
    normalize_workspace_name,
)


class WorkspaceStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class Workspace(BaseModel):
    """Immutable Workspace aggregate root without persistence concerns."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: WorkspaceId = Field(default_factory=new_id)
    name: str
    description: str = ""
    status: WorkspaceStatus = WorkspaceStatus.ACTIVE
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    archived_at: datetime | None = None
    version: int = Field(default=1, ge=1)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: UUID) -> UUID:
        if value.version != 4:
            raise ValueError("Workspace id must be a UUID4")
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_workspace_name(value)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        return normalize_workspace_description(value)

    @field_validator("created_at", "updated_at", "archived_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value) if value is not None else None

    @model_validator(mode="after")
    def validate_invariants(self) -> Workspace:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        if self.status is WorkspaceStatus.ACTIVE and self.archived_at is not None:
            raise ValueError("active workspace cannot have archived_at")
        if self.status is WorkspaceStatus.ARCHIVED and self.archived_at is None:
            raise ValueError("archived workspace must have archived_at")
        return self

    @classmethod
    def create(
        cls,
        name: str,
        description: str = "",
        *,
        workspace_id: WorkspaceId | None = None,
        now: datetime | None = None,
    ) -> Workspace:
        timestamp = ensure_utc(now) if now is not None else utc_now()
        return cls._validated(
            id=workspace_id or new_id(),
            name=name,
            description=description,
            status=WorkspaceStatus.ACTIVE,
            created_at=timestamp,
            updated_at=timestamp,
            archived_at=None,
            version=1,
        )

    def archive(self, *, archived_at: datetime | None = None) -> Workspace:
        if self.status is WorkspaceStatus.ARCHIVED:
            raise CyberOSError(
                ErrorCode.WORKSPACE_ALREADY_ARCHIVED, "The workspace is already archived."
            )
        timestamp = ensure_utc(archived_at) if archived_at is not None else utc_now()
        values = self.model_dump()
        values.update(
            status=WorkspaceStatus.ARCHIVED,
            updated_at=timestamp,
            archived_at=timestamp,
            version=self.version + 1,
        )
        return self._validated(**values)

    @classmethod
    def _validated(cls, **values: Any) -> Workspace:
        try:
            return cls.model_validate(values)
        except ValidationError as exc:
            fields = [".".join(str(part) for part in error["loc"]) for error in exc.errors()]
            raise CyberOSError(
                ErrorCode.DOMAIN_VALIDATION_FAILED,
                "Workspace validation failed.",
                details={"fields": fields},
            ) from exc
