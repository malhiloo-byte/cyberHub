from __future__ import annotations

import sqlite3
from typing import Any

from pydantic import ValidationError

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.workspace.model import Workspace

WORKSPACE_COLUMNS = (
    "id",
    "name",
    "description",
    "status",
    "created_at",
    "updated_at",
    "archived_at",
    "version",
)


def workspace_to_params(workspace: Workspace) -> tuple[Any, ...]:
    return (
        str(workspace.id),
        workspace.name,
        workspace.description,
        workspace.status.value,
        workspace.created_at.isoformat(),
        workspace.updated_at.isoformat(),
        workspace.archived_at.isoformat() if workspace.archived_at is not None else None,
        workspace.version,
    )


def workspace_from_row(row: sqlite3.Row) -> Workspace:
    payload = {column: row[column] for column in WORKSPACE_COLUMNS}
    try:
        return Workspace.model_validate(payload)
    except ValidationError as exc:
        raise CyberOSError(
            ErrorCode.PERSISTENCE_MAPPING_FAILED,
            "A stored Workspace row failed domain validation.",
            details={
                "fields": [".".join(str(part) for part in error["loc"]) for error in exc.errors()]
            },
        ) from exc
