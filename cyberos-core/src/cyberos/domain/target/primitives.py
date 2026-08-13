"""Typed Target primitives; persistence and matching are deferred to later slices."""

from enum import StrEnum
from typing import NewType
from uuid import UUID

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.ids import new_id

TargetId = NewType("TargetId", UUID)


class TargetStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class TargetRule(StrEnum):
    INCLUDE = "include"
    EXCLUDE = "exclude"


class TargetKind(StrEnum):
    FQDN = "fqdn"
    WILDCARD = "wildcard"
    IPV4 = "ipv4"
    IPV6 = "ipv6"
    CIDR = "cidr"
    URL = "url"


def validate_target_id(value: UUID) -> TargetId:
    """Validate and return a UUID4 as the strongly-typed TargetId."""

    if not isinstance(value, UUID) or value.version != 4:
        raise CyberOSError(
            ErrorCode.DOMAIN_VALIDATION_FAILED,
            "Target identifier must be a UUID4.",
            details={"field": "target_id"},
        )
    return TargetId(value)


def new_target_id() -> TargetId:
    """Create a new UUID4 TargetId."""

    return TargetId(new_id())
