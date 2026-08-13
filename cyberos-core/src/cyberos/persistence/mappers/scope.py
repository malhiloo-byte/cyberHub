"""SQLite row mapping for Scope; no repository or transaction ownership."""

import sqlite3
from typing import Any

from pydantic import ValidationError

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.scope.model import Scope

SCOPE_COLUMNS = (
    "id",
    "engagement_id",
    "name",
    "description",
    "status",
    "authorization_reference",
    "validated_at",
    "authorized_at",
    "expires_at",
    "created_at",
    "updated_at",
    "archived_at",
    "version",
)


def scope_to_params(scope: Scope) -> tuple[Any, ...]:
    return (
        str(scope.id),
        str(scope.engagement_id),
        scope.name,
        scope.description,
        scope.status.value,
        scope.authorization_reference,
        scope.validated_at.isoformat() if scope.validated_at is not None else None,
        scope.authorized_at.isoformat() if scope.authorized_at is not None else None,
        scope.expires_at.isoformat() if scope.expires_at is not None else None,
        scope.created_at.isoformat(),
        scope.updated_at.isoformat(),
        scope.archived_at.isoformat() if scope.archived_at is not None else None,
        scope.version,
    )


def scope_from_row(row: sqlite3.Row) -> Scope:
    payload = {column: row[column] for column in SCOPE_COLUMNS}
    try:
        return Scope.model_validate(payload)
    except ValidationError as exc:
        raise CyberOSError(
            ErrorCode.PERSISTENCE_MAPPING_FAILED,
            "A stored Scope row failed domain validation.",
            details={
                "fields": [".".join(str(part) for part in error["loc"]) for error in exc.errors()]
            },
        ) from exc
