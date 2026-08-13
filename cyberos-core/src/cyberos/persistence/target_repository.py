"""SQLite adapter for TargetRepository; parent Scope guards are fail-closed."""

import sqlite3
from collections.abc import Sequence

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.time import utc_now
from cyberos.domain.scope.primitives import ScopeId, ScopeStatus
from cyberos.domain.target.model import Target
from cyberos.domain.target.primitives import TargetId, TargetStatus
from cyberos.persistence.mappers.target import target_from_row, target_to_params
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork


def _translate_integrity_error(error: sqlite3.IntegrityError) -> CyberOSError:
    message = str(error).lower()
    if (
        "targets.scope_id, targets.rule, targets.kind, targets.value" in message
        or "uq_targets_scope_rule_kind_value" in message
    ):
        return CyberOSError(
            ErrorCode.TARGET_DUPLICATE,
            "This Target rule already exists in the Scope.",
        )
    if "foreign key constraint failed" in message:
        return CyberOSError(ErrorCode.SCOPE_NOT_FOUND, "The Target Scope does not exist.")
    return CyberOSError(ErrorCode.INVALID_INPUT, "The Target data violates a database constraint.")


class SQLiteTargetRepository:
    """Persistence adapter for Target; it never owns commit or rollback."""

    def __init__(self, unit_of_work: SQLiteUnitOfWork) -> None:
        self.unit_of_work = unit_of_work

    def add(self, target: Target) -> Target:
        self._ensure_mutable_scope(target.scope_id)
        try:
            self.unit_of_work.raw.execute(
                """
                INSERT INTO targets
                    (id, scope_id, rule, kind, value, status,
                     created_at, updated_at, archived_at, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                target_to_params(target),
            )
        except sqlite3.IntegrityError as exc:
            raise _translate_integrity_error(exc) from exc
        return target

    def get(self, target_id: TargetId) -> Target | None:
        row = self.unit_of_work.raw.execute(
            """
            SELECT id, scope_id, rule, kind, value, status,
                   created_at, updated_at, archived_at, version
            FROM targets WHERE id = ?
            """,
            (str(target_id),),
        ).fetchone()
        return target_from_row(row) if row is not None else None

    def list_by_scope(self, scope_id: ScopeId) -> Sequence[Target]:
        rows = self.unit_of_work.raw.execute(
            """
            SELECT id, scope_id, rule, kind, value, status,
                   created_at, updated_at, archived_at, version
            FROM targets
            WHERE scope_id = ?
            ORDER BY created_at DESC, id ASC
            """,
            (str(scope_id),),
        ).fetchall()
        return tuple(target_from_row(row) for row in rows)

    def exists(self, target_id: TargetId) -> bool:
        row = self.unit_of_work.raw.execute(
            "SELECT 1 FROM targets WHERE id = ? LIMIT 1", (str(target_id),)
        ).fetchone()
        return row is not None

    def update(self, target: Target, *, expected_version: int) -> Target:
        current = self._require(target.id)
        if current.scope_id != target.scope_id:
            raise CyberOSError(
                ErrorCode.TARGET_SCOPE_MISMATCH,
                "A Target cannot move to another Scope.",
            )
        self._ensure_mutable_scope(target.scope_id)
        if current.status is TargetStatus.ARCHIVED:
            raise CyberOSError(ErrorCode.TARGET_ALREADY_ARCHIVED, "Target is already archived.")
        try:
            cursor = self.unit_of_work.raw.execute(
                """
                UPDATE targets
                SET rule = ?, kind = ?, value = ?, status = ?,
                    updated_at = ?, archived_at = ?, version = version + 1
                WHERE id = ? AND version = ?
                """,
                (
                    target.rule.value,
                    target.kind.value,
                    target.value,
                    target.status.value,
                    target.updated_at.isoformat(),
                    target.archived_at.isoformat() if target.archived_at is not None else None,
                    str(target.id),
                    expected_version,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise _translate_integrity_error(exc) from exc
        if cursor.rowcount == 0:
            self._raise_update_conflict(target.id)
        return self._require(target.id)

    def archive(self, target_id: TargetId, *, expected_version: int) -> Target:
        current = self._require(target_id)
        self._ensure_mutable_scope(current.scope_id)
        if current.status is TargetStatus.ARCHIVED:
            raise CyberOSError(ErrorCode.TARGET_ALREADY_ARCHIVED, "Target is already archived.")
        timestamp = utc_now().isoformat()
        try:
            cursor = self.unit_of_work.raw.execute(
                """
                UPDATE targets
                SET status = 'archived', archived_at = ?, updated_at = ?,
                    version = version + 1
                WHERE id = ? AND version = ?
                """,
                (timestamp, timestamp, str(target_id), expected_version),
            )
        except sqlite3.IntegrityError as exc:
            raise _translate_integrity_error(exc) from exc
        if cursor.rowcount == 0:
            self._raise_update_conflict(target_id)
        return self._require(target_id)

    def _ensure_mutable_scope(self, scope_id: ScopeId) -> None:
        row = self.unit_of_work.raw.execute(
            "SELECT status FROM scopes WHERE id = ?", (str(scope_id),)
        ).fetchone()
        if row is None:
            raise CyberOSError(ErrorCode.SCOPE_NOT_FOUND, "The Target Scope does not exist.")
        status = ScopeStatus(row["status"])
        if status is ScopeStatus.AUTHORIZED:
            raise CyberOSError(
                ErrorCode.AUTHORIZED_SCOPE_IMMUTABLE,
                "Authorized Scope cannot mutate Targets.",
            )
        if status is ScopeStatus.ARCHIVED:
            raise CyberOSError(ErrorCode.SCOPE_ARCHIVED, "Archived Scope cannot mutate Targets.")
        if status is not ScopeStatus.DRAFT:
            raise CyberOSError(
                ErrorCode.SCOPE_NOT_DRAFT,
                "Scope must be returned to draft before Target mutation.",
            )

    def _require(self, target_id: TargetId) -> Target:
        target = self.get(target_id)
        if target is None:
            raise CyberOSError(ErrorCode.TARGET_NOT_FOUND, "The Target does not exist.")
        return target

    def _raise_update_conflict(self, target_id: TargetId) -> None:
        if self.get(target_id) is None:
            raise CyberOSError(ErrorCode.TARGET_NOT_FOUND, "The Target does not exist.")
        raise CyberOSError(ErrorCode.CONCURRENCY_CONFLICT, "The Target version is stale.")
