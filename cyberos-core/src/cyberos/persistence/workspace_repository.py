from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.time import utc_now
from cyberos.domain.workspace.model import Workspace, WorkspaceStatus
from cyberos.domain.workspace.primitives import WorkspaceId
from cyberos.persistence.mappers.workspace import workspace_from_row, workspace_to_params
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork


def _translate_integrity_error(error: sqlite3.IntegrityError) -> CyberOSError:
    message = str(error).lower()
    if "uq_workspaces_name_nocase" in message or "workspaces.name" in message:
        return CyberOSError(
            ErrorCode.WORKSPACE_NAME_CONFLICT, "A Workspace with this name already exists."
        )
    return CyberOSError(
        ErrorCode.INVALID_INPUT, "The Workspace data violates a database constraint."
    )


class SQLiteWorkspaceRepository:
    """SQLite adapter for WorkspaceRepository; transaction ownership stays in UnitOfWork."""

    def __init__(self, unit_of_work: SQLiteUnitOfWork) -> None:
        self.unit_of_work = unit_of_work

    def add(self, workspace: Workspace) -> Workspace:
        try:
            self.unit_of_work.raw.execute(
                """
                INSERT INTO workspaces
                    (id, name, description, status, created_at, updated_at, archived_at, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                workspace_to_params(workspace),
            )
        except sqlite3.IntegrityError as exc:
            raise _translate_integrity_error(exc) from exc
        return workspace

    def get(self, workspace_id: WorkspaceId) -> Workspace | None:
        row = self.unit_of_work.raw.execute(
            """
            SELECT id, name, description, status, created_at, updated_at, archived_at, version
            FROM workspaces WHERE id = ?
            """,
            (str(workspace_id),),
        ).fetchone()
        return workspace_from_row(row) if row is not None else None

    def list(self, *, status: WorkspaceStatus | None = None) -> Sequence[Workspace]:
        if status is None:
            rows = self.unit_of_work.raw.execute(
                """
                SELECT id, name, description, status, created_at, updated_at, archived_at, version
                FROM workspaces ORDER BY created_at DESC, id ASC
                """
            ).fetchall()
        else:
            rows = self.unit_of_work.raw.execute(
                """
                SELECT id, name, description, status, created_at, updated_at, archived_at, version
                FROM workspaces WHERE status = ? ORDER BY created_at DESC, id ASC
                """,
                (status.value,),
            ).fetchall()
        return tuple(workspace_from_row(row) for row in rows)

    def exists(self, workspace_id: WorkspaceId) -> bool:
        row = self.unit_of_work.raw.execute(
            "SELECT 1 FROM workspaces WHERE id = ? LIMIT 1", (str(workspace_id),)
        ).fetchone()
        return row is not None

    def update(self, workspace: Workspace, *, expected_version: int) -> Workspace:
        try:
            cursor = self.unit_of_work.raw.execute(
                """
                UPDATE workspaces
                SET name = ?, description = ?, status = ?, updated_at = ?, archived_at = ?,
                    version = version + 1
                WHERE id = ? AND version = ?
                """,
                (
                    workspace.name,
                    workspace.description,
                    workspace.status.value,
                    workspace.updated_at.isoformat(),
                    workspace.archived_at.isoformat()
                    if workspace.archived_at is not None
                    else None,
                    str(workspace.id),
                    expected_version,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise _translate_integrity_error(exc) from exc
        if cursor.rowcount == 0:
            self._raise_update_conflict(workspace.id)
        result = self.get(workspace.id)
        if result is None:
            raise CyberOSError(ErrorCode.WORKSPACE_NOT_FOUND, "The Workspace does not exist.")
        return result

    def archive(self, workspace_id: WorkspaceId, *, expected_version: int) -> Workspace:
        timestamp = utc_now().isoformat()
        try:
            cursor = self.unit_of_work.raw.execute(
                """
                UPDATE workspaces
                SET status = 'archived', archived_at = ?, updated_at = ?, version = version + 1
                WHERE id = ? AND version = ? AND status = 'active'
                """,
                (
                    timestamp,
                    timestamp,
                    str(workspace_id),
                    expected_version,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise _translate_integrity_error(exc) from exc
        if cursor.rowcount == 0:
            self._raise_update_conflict(workspace_id)
        result = self.get(workspace_id)
        if result is None:
            raise CyberOSError(ErrorCode.WORKSPACE_NOT_FOUND, "The Workspace does not exist.")
        return result

    def _raise_update_conflict(self, workspace_id: WorkspaceId) -> None:
        if not self.exists(workspace_id):
            raise CyberOSError(ErrorCode.WORKSPACE_NOT_FOUND, "The Workspace does not exist.")
        raise CyberOSError(ErrorCode.CONCURRENCY_CONFLICT, "The Workspace version is stale.")
