from __future__ import annotations

from uuid import UUID

from cyberos.core.errors import CyberOSError, ErrorCode

EngagementId = UUID


def normalize_engagement_name(value: str) -> str:
    if not isinstance(value, str):
        raise CyberOSError(ErrorCode.DOMAIN_VALIDATION_FAILED, "Engagement name must be text.")
    normalized = value.strip()
    if not 1 <= len(normalized) <= 160:
        raise CyberOSError(
            ErrorCode.DOMAIN_VALIDATION_FAILED,
            "Engagement name must contain 1 to 160 characters.",
        )
    return normalized


def normalize_engagement_description(value: str) -> str:
    if not isinstance(value, str):
        raise CyberOSError(
            ErrorCode.DOMAIN_VALIDATION_FAILED, "Engagement description must be text."
        )
    normalized = value.strip()
    if len(normalized) > 4000:
        raise CyberOSError(
            ErrorCode.DOMAIN_VALIDATION_FAILED,
            "Engagement description cannot exceed 4000 characters.",
        )
    return normalized


def normalize_authorization_reference(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CyberOSError(
            ErrorCode.DOMAIN_VALIDATION_FAILED,
            "Authorization reference must be text.",
        )
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > 1000:
        raise CyberOSError(
            ErrorCode.DOMAIN_VALIDATION_FAILED,
            "Authorization reference cannot exceed 1000 characters.",
        )
    return normalized
