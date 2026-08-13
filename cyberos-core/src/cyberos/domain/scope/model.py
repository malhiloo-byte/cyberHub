"""Immutable Scope aggregate and lifecycle guards."""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.time import ensure_utc, utc_now
from cyberos.domain.engagement.primitives import EngagementId
from cyberos.domain.scope.primitives import (
    ScopeId,
    ScopeStatus,
    new_scope_id,
    normalize_scope_authorization_reference,
    normalize_scope_description,
    normalize_scope_name,
)
from cyberos.domain.target.model import Target


class Scope(BaseModel):
    """Immutable Scope aggregate; Target mutations are guarded by lifecycle state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: ScopeId = Field(default_factory=new_scope_id)
    engagement_id: EngagementId
    name: str
    description: str = ""
    status: ScopeStatus = ScopeStatus.DRAFT
    authorization_reference: str | None = None
    validated_at: datetime | None = None
    authorized_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    archived_at: datetime | None = None
    version: int = Field(default=1, ge=1)
    targets: tuple[Target, ...] = ()

    ALLOWED_TRANSITIONS: ClassVar[dict[ScopeStatus, frozenset[ScopeStatus]]] = {
        ScopeStatus.DRAFT: frozenset({ScopeStatus.VALIDATED, ScopeStatus.ARCHIVED}),
        ScopeStatus.VALIDATED: frozenset({ScopeStatus.AUTHORIZED, ScopeStatus.ARCHIVED}),
        ScopeStatus.AUTHORIZED: frozenset({ScopeStatus.ARCHIVED}),
        ScopeStatus.ARCHIVED: frozenset(),
    }

    @field_validator("id", "engagement_id")
    @classmethod
    def validate_uuid4(cls, value: UUID) -> UUID:
        if value.version != 4:
            raise ValueError("Scope and engagement identifiers must be UUID4")
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_scope_name(value)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        return normalize_scope_description(value)

    @field_validator("authorization_reference")
    @classmethod
    def validate_authorization_reference(cls, value: str | None) -> str | None:
        return normalize_scope_authorization_reference(value)

    @field_validator(
        "validated_at",
        "authorized_at",
        "expires_at",
        "created_at",
        "updated_at",
        "archived_at",
    )
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value) if value is not None else None

    @model_validator(mode="after")
    def validate_invariants(self) -> Scope:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        if self.archived_at is not None and self.status is not ScopeStatus.ARCHIVED:
            raise ValueError("non-archived Scope cannot have archived_at")
        if self.status is ScopeStatus.ARCHIVED and self.archived_at is None:
            raise ValueError("archived Scope must have archived_at")
        if self.status is ScopeStatus.DRAFT and (self.validated_at or self.authorized_at):
            raise ValueError("draft Scope cannot have validation or authorization timestamps")
        if self.status is ScopeStatus.VALIDATED and (
            self.validated_at is None or self.authorized_at is not None
        ):
            raise ValueError("validated Scope must have only validated_at")
        if self.status is ScopeStatus.AUTHORIZED and (
            self.validated_at is None
            or self.authorized_at is None
            or not self.authorization_reference
        ):
            raise ValueError("authorized Scope requires validation, authorization, and reference")
        if self.expires_at is not None and (
            self.authorized_at is None or self.expires_at <= self.authorized_at
        ):
            raise ValueError("expires_at must be later than authorized_at")
        if any(target.scope_id != self.id for target in self.targets):
            raise ValueError("all Scope targets must reference the owning Scope")
        return self

    @classmethod
    def create(
        cls,
        engagement_id: EngagementId,
        name: str,
        description: str = "",
        *,
        scope_id: ScopeId | None = None,
        now: datetime | None = None,
    ) -> Scope:
        timestamp = ensure_utc(now) if now is not None else utc_now()
        return cls._validated(
            id=scope_id or new_scope_id(),
            engagement_id=engagement_id,
            name=name,
            description=description,
            status=ScopeStatus.DRAFT,
            authorization_reference=None,
            validated_at=None,
            authorized_at=None,
            expires_at=None,
            created_at=timestamp,
            updated_at=timestamp,
            archived_at=None,
            version=1,
            targets=(),
        )

    def mark_validated(self, *, at: datetime | None = None) -> Scope:
        self._require_transition(ScopeStatus.VALIDATED)
        timestamp = ensure_utc(at) if at is not None else utc_now()
        values = self.model_dump()
        values.update(
            status=ScopeStatus.VALIDATED,
            validated_at=timestamp,
            updated_at=timestamp,
            version=self.version + 1,
        )
        return self._validated(**values)

    def authorize(
        self,
        authorization_reference: str,
        *,
        at: datetime | None = None,
        expires_at: datetime | None = None,
    ) -> Scope:
        self._require_transition(ScopeStatus.AUTHORIZED)
        reference = normalize_scope_authorization_reference(authorization_reference)
        if not reference:
            raise CyberOSError(
                ErrorCode.SCOPE_AUTHORIZATION_REQUIRED,
                "A non-empty authorization reference is required.",
            )
        timestamp = ensure_utc(at) if at is not None else utc_now()
        effective_expiry = ensure_utc(expires_at) if expires_at is not None else None
        if effective_expiry is not None and effective_expiry <= timestamp:
            raise CyberOSError(
                ErrorCode.DOMAIN_VALIDATION_FAILED,
                "Scope expiry must be later than authorization time.",
            )
        values = self.model_dump()
        values.update(
            status=ScopeStatus.AUTHORIZED,
            authorization_reference=reference,
            authorized_at=timestamp,
            expires_at=effective_expiry,
            updated_at=timestamp,
            version=self.version + 1,
        )
        return self._validated(**values)

    def return_to_draft(self, *, at: datetime | None = None) -> Scope:
        if self.status not in {ScopeStatus.VALIDATED, ScopeStatus.AUTHORIZED}:
            self._raise_state_error()
        timestamp = ensure_utc(at) if at is not None else utc_now()
        values = self.model_dump()
        values.update(
            status=ScopeStatus.DRAFT,
            authorization_reference=None,
            validated_at=None,
            authorized_at=None,
            expires_at=None,
            updated_at=timestamp,
            version=self.version + 1,
        )
        return self._validated(**values)

    def archive(self, *, at: datetime | None = None) -> Scope:
        if self.status is ScopeStatus.ARCHIVED:
            raise CyberOSError(ErrorCode.SCOPE_ARCHIVED, "Scope is already archived.")
        timestamp = ensure_utc(at) if at is not None else utc_now()
        values = self.model_dump()
        values.update(
            status=ScopeStatus.ARCHIVED,
            updated_at=timestamp,
            archived_at=timestamp,
            version=self.version + 1,
        )
        return self._validated(**values)

    def add_target(self, target: Target) -> Scope:
        self._require_target_mutation_allowed()
        if target.scope_id != self.id:
            raise CyberOSError(
                ErrorCode.TARGET_SCOPE_MISMATCH,
                "Target does not belong to this Scope.",
            )
        timestamp = utc_now()
        values = self.model_dump()
        values.update(
            targets=(*self.targets, target),
            updated_at=timestamp,
            version=self.version + 1,
        )
        return self._validated(**values)

    def update_target(self, target_id: UUID, value: str, *, at: datetime | None = None) -> Scope:
        self._require_target_mutation_allowed()
        target = self._find_target(target_id)
        updated_target = target.with_value(value, now=at)
        timestamp = ensure_utc(at) if at is not None else utc_now()
        targets = tuple(updated_target if item.id == target_id else item for item in self.targets)
        values = self.model_dump()
        values.update(
            targets=targets,
            updated_at=timestamp,
            version=self.version + 1,
        )
        return self._validated(**values)

    def archive_target(self, target_id: UUID, *, at: datetime | None = None) -> Scope:
        self._require_target_mutation_allowed()
        target = self._find_target(target_id)
        archived_target = target.archive(at=at)
        timestamp = ensure_utc(at) if at is not None else utc_now()
        targets = tuple(archived_target if item.id == target_id else item for item in self.targets)
        values = self.model_dump()
        values.update(
            targets=targets,
            updated_at=timestamp,
            version=self.version + 1,
        )
        return self._validated(**values)

    def _require_transition(self, target: ScopeStatus) -> None:
        if target not in self.ALLOWED_TRANSITIONS[self.status]:
            if self.status is ScopeStatus.ARCHIVED:
                raise CyberOSError(
                    ErrorCode.SCOPE_ARCHIVED,
                    "Archived Scope cannot change state.",
                )
            raise CyberOSError(
                ErrorCode.INVALID_SCOPE_TRANSITION,
                "The requested Scope status transition is not allowed.",
                details={"from": self.status.value, "to": target.value},
            )

    def _require_target_mutation_allowed(self) -> None:
        if self.status is ScopeStatus.AUTHORIZED:
            raise CyberOSError(
                ErrorCode.AUTHORIZED_SCOPE_IMMUTABLE,
                "Authorized Scope cannot mutate Targets; return it to draft first.",
            )
        if self.status is ScopeStatus.ARCHIVED:
            raise CyberOSError(
                ErrorCode.SCOPE_ARCHIVED,
                "Archived Scope cannot mutate Targets.",
            )
        if self.status is not ScopeStatus.DRAFT:
            raise CyberOSError(
                ErrorCode.SCOPE_NOT_DRAFT,
                "Scope must be returned to draft before Target mutation.",
            )

    def _raise_state_error(self) -> None:
        if self.status is ScopeStatus.ARCHIVED:
            raise CyberOSError(
                ErrorCode.SCOPE_ARCHIVED,
                "Archived Scope cannot change state.",
            )
        raise CyberOSError(
            ErrorCode.INVALID_SCOPE_TRANSITION,
            "Scope can only return to draft from validated or authorized.",
        )

    def _find_target(self, target_id: UUID) -> Target:
        for target in self.targets:
            if target.id == target_id:
                return target
        raise CyberOSError(
            ErrorCode.TARGET_NOT_FOUND,
            "Target was not found in this Scope.",
        )

    @classmethod
    def _validated(cls, **values: Any) -> Scope:
        try:
            return cls.model_validate(values)
        except ValidationError as exc:
            fields = [".".join(str(part) for part in error["loc"]) for error in exc.errors()]
            raise CyberOSError(
                ErrorCode.DOMAIN_VALIDATION_FAILED,
                "Scope validation failed.",
                details={"fields": fields},
            ) from exc
