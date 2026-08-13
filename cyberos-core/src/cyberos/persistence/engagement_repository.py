from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import datetime

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.time import utc_now
from cyberos.domain.engagement.model import Engagement, EngagementStatus
from cyberos.domain.engagement.primitives import EngagementId
from cyberos.domain.workspace.primitives import WorkspaceId
from cyberos.persistence.mappers.engagement import engagement_from_row, engagement_to_params
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork


def _translate_integrity_error(error: sqlite3.IntegrityError) -> CyberOSError:
    message = str(error).lower()
    if "engagements.workspace_id, engagements.name" in message:
        return CyberOSError(
            ErrorCode.ENGAGEMENT_NAME_CONFLICT,
            "An Engagement with this name already exists in the Workspace.",
        )
    if "foreign key constraint failed" in message:
        return CyberOSError(
            ErrorCode.WORKSPACE_NOT_FOUND,
            "The Engagement Workspace does not exist.",
        )
    return CyberOSError(
        ErrorCode.INVALID_INPUT,
        "The Engagement data violates a database constraint.",
    )


class SQLiteEngagementRepository:
    """SQLite adapter for EngagementRepository; UnitOfWork owns transactions."""

    def __init__(self, unit_of_work: SQLiteUnitOfWork) -> None:
        self.unit_of_work = unit_of_work

    def add(self, engagement: Engagement) -> Engagement:
        self._ensure_active_workspace(engagement.workspace_id)
        try:
            self.unit_of_work.raw.execute(
                """
                INSERT INTO engagements
                    (id, workspace_id, name, kind, status, description,
                     authorization_reference, start_at, end_at, created_at,
                     updated_at, archived_at, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                engagement_to_params(engagement),
            )
        except sqlite3.IntegrityError as exc:
            raise _translate_integrity_error(exc) from exc
        return engagement

    def get(self, engagement_id: EngagementId) -> Engagement | None:
        row = self.unit_of_work.raw.execute(
            """
            SELECT id, workspace_id, name, kind, status, description,
                   authorization_reference, start_at, end_at, created_at,
                   updated_at, archived_at, version
            FROM engagements WHERE id = ?
            """,
            (str(engagement_id),),
        ).fetchone()
        return engagement_from_row(row) if row is not None else None

    def list_by_workspace(
        self,
        workspace_id: WorkspaceId,
        *,
        status: EngagementStatus | None = None,
    ) -> Sequence[Engagement]:
        query = """
            SELECT id, workspace_id, name, kind, status, description,
                   authorization_reference, start_at, end_at, created_at,
                   updated_at, archived_at, version
            FROM engagements
            WHERE workspace_id = ?
        """
        parameters: tuple[object, ...] = (str(workspace_id),)
        if status is not None:
            query += " AND status = ?"
            parameters += (status.value,)
        query += " ORDER BY created_at DESC, id ASC"
        rows = self.unit_of_work.raw.execute(query, parameters).fetchall()
        return tuple(engagement_from_row(row) for row in rows)

    def update(self, engagement: Engagement, *, expected_version: int) -> Engagement:
        current = self._require(engagement.id)
        if current.workspace_id != engagement.workspace_id:
            raise CyberOSError(
                ErrorCode.ENGAGEMENT_WORKSPACE_IMMUTABLE,
                "An Engagement cannot be moved to another Workspace.",
            )
        try:
            cursor = self.unit_of_work.raw.execute(
                """
                UPDATE engagements
                SET name = ?, kind = ?, description = ?, authorization_reference = ?,
                    start_at = ?, end_at = ?, updated_at = ?, version = version + 1
                WHERE id = ? AND version = ?
                """,
                (
                    engagement.name,
                    engagement.kind.value,
                    engagement.description,
                    engagement.authorization_reference,
                    engagement.start_at.isoformat() if engagement.start_at is not None else None,
                    engagement.end_at.isoformat() if engagement.end_at is not None else None,
                    engagement.updated_at.isoformat(),
                    str(engagement.id),
                    expected_version,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise _translate_integrity_error(exc) from exc
        if cursor.rowcount == 0:
            self._raise_update_conflict(engagement.id)
        return self._require(engagement.id)

    def transition(
        self,
        engagement_id: EngagementId,
        target_status: EngagementStatus,
        *,
        expected_version: int,
        at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> Engagement:
        current = self._require(engagement_id)
        if target_status is EngagementStatus.ACTIVE:
            self._ensure_active_workspace(current.workspace_id)
        transitioned = current.transition(target_status, at=at, end_at=end_at)
        try:
            cursor = self.unit_of_work.raw.execute(
                """
                UPDATE engagements
                SET status = ?, end_at = ?, updated_at = ?, archived_at = ?, version = version + 1
                WHERE id = ? AND version = ?
                """,
                (
                    transitioned.status.value,
                    transitioned.end_at.isoformat() if transitioned.end_at is not None else None,
                    transitioned.updated_at.isoformat(),
                    transitioned.archived_at.isoformat()
                    if transitioned.archived_at is not None
                    else None,
                    str(engagement_id),
                    expected_version,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise _translate_integrity_error(exc) from exc
        if cursor.rowcount == 0:
            self._raise_update_conflict(engagement_id)
        return self._require(engagement_id)

    def archive(self, engagement_id: EngagementId, *, expected_version: int) -> Engagement:
        return self.transition(
            engagement_id,
            EngagementStatus.ARCHIVED,
            expected_version=expected_version,
            at=utc_now(),
        )

    def _ensure_active_workspace(self, workspace_id: WorkspaceId) -> None:
        row = self.unit_of_work.raw.execute(
            "SELECT status FROM workspaces WHERE id = ?", (str(workspace_id),)
        ).fetchone()
        if row is None:
            raise CyberOSError(
                ErrorCode.WORKSPACE_NOT_FOUND, "The Engagement Workspace does not exist."
            )
        if row["status"] != "active":
            raise CyberOSError(
                ErrorCode.WORKSPACE_ARCHIVED,
                "The Engagement Workspace is archived and cannot accept this operation.",
            )

    def _require(self, engagement_id: EngagementId) -> Engagement:
        engagement = self.get(engagement_id)
        if engagement is None:
            raise CyberOSError(ErrorCode.ENGAGEMENT_NOT_FOUND, "The Engagement does not exist.")
        return engagement

    def _raise_update_conflict(self, engagement_id: EngagementId) -> None:
        if self.get(engagement_id) is None:
            raise CyberOSError(ErrorCode.ENGAGEMENT_NOT_FOUND, "The Engagement does not exist.")
        raise CyberOSError(ErrorCode.CONCURRENCY_CONFLICT, "The Engagement version is stale.")
