"""Typed Scope primitives; aggregate behavior is intentionally deferred to 0.4.b."""

from enum import StrEnum
from typing import NewType
from uuid import UUID

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.ids import new_id

ScopeId = NewType("ScopeId", UUID)


class ScopeStatus(StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    AUTHORIZED = "authorized"
    ARCHIVED = "archived"


def normalize_scope_name(value: str) -> str:
    if not isinstance(value, str):
        raise CyberOSError(ErrorCode.DOMAIN_VALIDATION_FAILED, "Scope name must be text.")
    normalized = value.strip()
    if not 1 <= len(normalized) <= 160:
        raise CyberOSError(
            ErrorCode.DOMAIN_VALIDATION_FAILED,
            "Scope name must contain 1 to 160 characters.",
        )
    return normalized


def normalize_scope_description(value: str) -> str:
    if not isinstance(value, str):
        raise CyberOSError(ErrorCode.DOMAIN_VALIDATION_FAILED, "Scope description must be text.")
    normalized = value.strip()
    if len(normalized) > 4000:
        raise CyberOSError(
            ErrorCode.DOMAIN_VALIDATION_FAILED,
            "Scope description cannot exceed 4000 characters.",
        )
    return normalized


def normalize_scope_authorization_reference(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CyberOSError(
            ErrorCode.DOMAIN_VALIDATION_FAILED,
            "Scope authorization reference must be text.",
        )
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > 1000:
        raise CyberOSError(
            ErrorCode.DOMAIN_VALIDATION_FAILED,
            "Scope authorization reference cannot exceed 1000 characters.",
        )
    return normalized


def validate_scope_id(value: UUID) -> ScopeId:
    """Validate and return a UUID4 as the strongly-typed ScopeId."""

    if not isinstance(value, UUID) or value.version != 4:
        raise CyberOSError(
            ErrorCode.DOMAIN_VALIDATION_FAILED,
            "Scope identifier must be a UUID4.",
            details={"field": "scope_id"},
        )
    return ScopeId(value)


def new_scope_id() -> ScopeId:
    """Create a new UUID4 ScopeId."""

    return ScopeId(new_id())
