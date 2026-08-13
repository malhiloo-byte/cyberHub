"""SQLite adapter for ScopeRepository; UnitOfWork owns transaction boundaries."""

import sqlite3
from collections.abc import Sequence

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.time import utc_now
from cyberos.domain.engagement.primitives import EngagementId
from cyberos.domain.scope.model import Scope
from cyberos.domain.scope.primitives import ScopeId, ScopeStatus
from cyberos.persistence.mappers.scope import scope_from_row, scope_to_params
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork


def _translate_integrity_error(error: sqlite3.IntegrityError) -> CyberOSError:
    message = str(error).lower()
    if (
        "scopes.engagement_id, scopes.name" in message
        or "uq_scopes_engagement_name_nocase" in message
    ):
        return CyberOSError(
            ErrorCode.SCOPE_NAME_CONFLICT,
            "A Scope with this name already exists in the Engagement.",
        )
    if "foreign key constraint failed" in message:
        return CyberOSError(
            ErrorCode.ENGAGEMENT_NOT_FOUND,
            "The Scope Engagement does not exist.",
        )
    return CyberOSError(ErrorCode.INVALID_INPUT, "The Scope data violates a database constraint.")


class SQLiteScopeRepository:
    """Persistence adapter for Scope; it never owns commit or rollback."""

    def __init__(self, unit_of_work: SQLiteUnitOfWork) -> None:
        self.unit_of_work = unit_of_work

    def add(self, scope: Scope) -> Scope:
        self._ensure_active_engagement(scope.engagement_id)
        try:
            self.unit_of_work.raw.execute(
                """
                INSERT INTO scopes
                    (id, engagement_id, name, description, status,
                     authorization_reference, validated_at, authorized_at,
                     expires_at, created_at, updated_at, archived_at, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                scope_to_params(scope),
            )
        except sqlite3.IntegrityError as exc:
            raise _translate_integrity_error(exc) from exc
        return scope

    def get(self, scope_id: ScopeId) -> Scope | None:
        row = self.unit_of_work.raw.execute(
            """
            SELECT id, engagement_id, name, description, status,
                   authorization_reference, validated_at, authorized_at,
                   expires_at, created_at, updated_at, archived_at, version
            FROM scopes WHERE id = ?
            """,
            (str(scope_id),),
        ).fetchone()
        return scope_from_row(row) if row is not None else None

    def list_by_engagement(self, engagement_id: EngagementId) -> Sequence[Scope]:
        rows = self.unit_of_work.raw.execute(
            """
            SELECT id, engagement_id, name, description, status,
                   authorization_reference, validated_at, authorized_at,
                   expires_at, created_at, updated_at, archived_at, version
            FROM scopes
            WHERE engagement_id = ?
            ORDER BY created_at DESC, id ASC
            """,
            (str(engagement_id),),
        ).fetchall()
        return tuple(scope_from_row(row) for row in rows)

    def exists(self, scope_id: ScopeId) -> bool:
        row = self.unit_of_work.raw.execute(
            "SELECT 1 FROM scopes WHERE id = ? LIMIT 1", (str(scope_id),)
        ).fetchone()
        return row is not None

    def update(self, scope: Scope, *, expected_version: int) -> Scope:
        current = self._require(scope.id)
        if current.engagement_id != scope.engagement_id:
            raise CyberOSError(
                ErrorCode.INVALID_INPUT,
                "A Scope cannot move to another Engagement.",
            )
        try:
            cursor = self.unit_of_work.raw.execute(
                """
                UPDATE scopes
                SET name = ?, description = ?, status = ?,
                    authorization_reference = ?, validated_at = ?,
                    authorized_at = ?, expires_at = ?, updated_at = ?,
                    archived_at = ?, version = version + 1
                WHERE id = ? AND version = ?
                """,
                (
                    scope.name,
                    scope.description,
                    scope.status.value,
                    scope.authorization_reference,
                    scope.validated_at.isoformat() if scope.validated_at is not None else None,
                    scope.authorized_at.isoformat() if scope.authorized_at is not None else None,
                    scope.expires_at.isoformat() if scope.expires_at is not None else None,
                    scope.updated_at.isoformat(),
                    scope.archived_at.isoformat() if scope.archived_at is not None else None,
                    str(scope.id),
                    expected_version,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise _translate_integrity_error(exc) from exc
        if cursor.rowcount == 0:
            self._raise_update_conflict(scope.id)
        return self._require(scope.id)

    def archive(self, scope_id: ScopeId, *, expected_version: int) -> Scope:
        current = self._require(scope_id)
        if current.status is ScopeStatus.ARCHIVED:
            raise CyberOSError(ErrorCode.SCOPE_ARCHIVED, "Scope is already archived.")
        timestamp = utc_now().isoformat()
        try:
            cursor = self.unit_of_work.raw.execute(
                """
                UPDATE scopes
                SET status = 'archived', archived_at = ?, updated_at = ?,
                    version = version + 1
                WHERE id = ? AND version = ?
                """,
                (timestamp, timestamp, str(scope_id), expected_version),
            )
        except sqlite3.IntegrityError as exc:
            raise _translate_integrity_error(exc) from exc
        if cursor.rowcount == 0:
            self._raise_update_conflict(scope_id)
        return self._require(scope_id)

    def _ensure_active_engagement(self, engagement_id: EngagementId) -> None:
        row = self.unit_of_work.raw.execute(
            "SELECT status FROM engagements WHERE id = ?", (str(engagement_id),)
        ).fetchone()
        if row is None:
            raise CyberOSError(
                ErrorCode.ENGAGEMENT_NOT_FOUND,
                "The Scope Engagement does not exist.",
            )
        if row["status"] == "archived":
            raise CyberOSError(
                ErrorCode.ENGAGEMENT_ARCHIVED,
                "The Engagement is archived and cannot accept a Scope.",
            )

    def _require(self, scope_id: ScopeId) -> Scope:
        scope = self.get(scope_id)
        if scope is None:
            raise CyberOSError(ErrorCode.SCOPE_NOT_FOUND, "The Scope does not exist.")
        return scope

    def _raise_update_conflict(self, scope_id: ScopeId) -> None:
        if self.get(scope_id) is None:
            raise CyberOSError(ErrorCode.SCOPE_NOT_FOUND, "The Scope does not exist.")
        raise CyberOSError(ErrorCode.CONCURRENCY_CONFLICT, "The Scope version is stale.")
