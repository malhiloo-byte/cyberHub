from __future__ import annotations

import sqlite3
from typing import Any

from pydantic import ValidationError

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.engagement.model import Engagement

ENGAGEMENT_COLUMNS = (
    "id",
    "workspace_id",
    "name",
    "kind",
    "status",
    "description",
    "authorization_reference",
    "start_at",
    "end_at",
    "created_at",
    "updated_at",
    "archived_at",
    "version",
)


def engagement_to_params(engagement: Engagement) -> tuple[Any, ...]:
    return (
        str(engagement.id),
        str(engagement.workspace_id),
        engagement.name,
        engagement.kind.value,
        engagement.status.value,
        engagement.description,
        engagement.authorization_reference,
        engagement.start_at.isoformat() if engagement.start_at is not None else None,
        engagement.end_at.isoformat() if engagement.end_at is not None else None,
        engagement.created_at.isoformat(),
        engagement.updated_at.isoformat(),
        engagement.archived_at.isoformat() if engagement.archived_at is not None else None,
        engagement.version,
    )


def engagement_from_row(row: sqlite3.Row) -> Engagement:
    payload = {column: row[column] for column in ENGAGEMENT_COLUMNS}
    try:
        return Engagement.model_validate(payload)
    except ValidationError as exc:
        raise CyberOSError(
            ErrorCode.PERSISTENCE_MAPPING_FAILED,
            "A stored Engagement row failed domain validation.",
            details={
                "fields": [".".join(str(part) for part in error["loc"]) for error in exc.errors()]
            },
        ) from exc
