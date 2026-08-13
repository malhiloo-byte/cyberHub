"""Immutable Target domain model; persistence and matching remain out of scope."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.time import ensure_utc, utc_now
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.canonicalization import TargetCanonicalizer
from cyberos.domain.target.primitives import (
    TargetId,
    TargetKind,
    TargetRule,
    TargetStatus,
    new_target_id,
)


class Target(BaseModel):
    """Immutable canonical target owned by exactly one Scope."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: TargetId = Field(default_factory=new_target_id)
    scope_id: ScopeId
    rule: TargetRule
    kind: TargetKind
    value: str
    status: TargetStatus = TargetStatus.ACTIVE
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    archived_at: datetime | None = None
    version: int = Field(default=1, ge=1)

    @field_validator("id", "scope_id")
    @classmethod
    def validate_uuid4(cls, value: UUID) -> UUID:
        if value.version != 4:
            raise ValueError("Target and scope identifiers must be UUID4")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: TargetStatus) -> TargetStatus:
        if value not in TargetStatus:
            raise ValueError("Target status must be active or archived")
        return value

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: str) -> str:
        if not isinstance(value, str) or not value:
            raise ValueError("Target value must be non-empty text")
        return value

    @field_validator("created_at", "updated_at", "archived_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value) if value is not None else None

    @model_validator(mode="after")
    def validate_invariants(self) -> Target:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        if self.status is TargetStatus.ARCHIVED and self.archived_at is None:
            raise ValueError("archived target must have archived_at")
        if self.status is TargetStatus.ACTIVE and self.archived_at is not None:
            raise ValueError("active target cannot have archived_at")
        canonical = TargetCanonicalizer.canonicalize(self.kind, self.value)
        if canonical.value != self.value:
            raise ValueError("Target value must be canonical")
        return self

    @classmethod
    def create(
        cls,
        scope_id: ScopeId,
        rule: TargetRule,
        kind: TargetKind,
        value: str,
        *,
        target_id: TargetId | None = None,
        now: datetime | None = None,
    ) -> Target:
        timestamp = ensure_utc(now) if now is not None else utc_now()
        canonical = TargetCanonicalizer.canonicalize(kind, value)
        return cls._validated(
            id=target_id or new_target_id(),
            scope_id=scope_id,
            rule=rule,
            kind=canonical.kind,
            value=canonical.value,
            status=TargetStatus.ACTIVE,
            created_at=timestamp,
            updated_at=timestamp,
            archived_at=None,
            version=1,
        )

    def with_value(self, value: str, *, now: datetime | None = None) -> Target:
        if self.status is TargetStatus.ARCHIVED:
            raise CyberOSError(
                ErrorCode.TARGET_ALREADY_ARCHIVED,
                "An archived Target cannot be modified.",
            )
        timestamp = ensure_utc(now) if now is not None else utc_now()
        canonical = TargetCanonicalizer.canonicalize(self.kind, value)
        values = self.model_dump()
        values.update(value=canonical.value, updated_at=timestamp, version=self.version + 1)
        return self._validated(**values)

    def archive(self, *, at: datetime | None = None) -> Target:
        if self.status is TargetStatus.ARCHIVED:
            raise CyberOSError(
                ErrorCode.TARGET_ALREADY_ARCHIVED,
                "Target is already archived.",
            )
        timestamp = ensure_utc(at) if at is not None else utc_now()
        values = self.model_dump()
        values.update(
            status=TargetStatus.ARCHIVED,
            updated_at=timestamp,
            archived_at=timestamp,
            version=self.version + 1,
        )
        return self._validated(**values)

    @classmethod
    def _validated(cls, **values: Any) -> Target:
        try:
            return cls.model_validate(values)
        except ValidationError as exc:
            fields = [".".join(str(part) for part in error["loc"]) for error in exc.errors()]
            raise CyberOSError(
                ErrorCode.DOMAIN_VALIDATION_FAILED,
                "Target validation failed.",
                details={"fields": fields},
            ) from exc
