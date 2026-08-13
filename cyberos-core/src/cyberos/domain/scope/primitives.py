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
