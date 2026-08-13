"""SQLite row mapping for Target; canonicalization remains a Domain invariant."""

import sqlite3
from typing import Any

from pydantic import ValidationError

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.target.model import Target

TARGET_COLUMNS = (
    "id",
    "scope_id",
    "rule",
    "kind",
    "value",
    "status",
    "created_at",
    "updated_at",
    "archived_at",
    "version",
)


def target_to_params(target: Target) -> tuple[Any, ...]:
    return (
        str(target.id),
        str(target.scope_id),
        target.rule.value,
        target.kind.value,
        target.value,
        target.status.value,
        target.created_at.isoformat(),
        target.updated_at.isoformat(),
        target.archived_at.isoformat() if target.archived_at is not None else None,
        target.version,
    )


def target_from_row(row: sqlite3.Row) -> Target:
    payload = {column: row[column] for column in TARGET_COLUMNS}
    try:
        return Target.model_validate(payload)
    except ValidationError as exc:
        raise CyberOSError(
            ErrorCode.PERSISTENCE_MAPPING_FAILED,
            "A stored Target row failed domain validation.",
            details={
                "fields": [".".join(str(part) for part in error["loc"]) for error in exc.errors()]
            },
        ) from exc
