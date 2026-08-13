from __future__ import annotations

from uuid import UUID

from cyberos.core.errors import CyberOSError, ErrorCode

WorkspaceId = UUID


def normalize_workspace_name(value: str) -> str:
    if not isinstance(value, str):
        raise CyberOSError(ErrorCode.DOMAIN_VALIDATION_FAILED, "Workspace name must be text.")
    normalized = value.strip()
    if not 1 <= len(normalized) <= 120:
        raise CyberOSError(
            ErrorCode.DOMAIN_VALIDATION_FAILED, "Workspace name must contain 1 to 120 characters."
        )
    return normalized


def normalize_workspace_description(value: str) -> str:
    if not isinstance(value, str):
        raise CyberOSError(
            ErrorCode.DOMAIN_VALIDATION_FAILED, "Workspace description must be text."
        )
    normalized = value.strip()
    if len(normalized) > 4000:
        raise CyberOSError(
            ErrorCode.DOMAIN_VALIDATION_FAILED,
            "Workspace description cannot exceed 4000 characters.",
        )
    return normalized
