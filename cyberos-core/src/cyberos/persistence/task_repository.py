"""SQLite persistence adapter for TaskRecord snapshots."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.primitives import TargetId
from cyberos.domain.task.primitives import TaskId
from cyberos.domain.task.record import TaskRecord
from cyberos.persistence.mappers.task import (
    task_record_from_row,
    task_record_to_params,
)
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork

TASK_INSERT_SQL = """
INSERT INTO tasks
    (id, scope_id, target_id, status, command_json, timeout_seconds,
     max_output_bytes, env_policy_json, authorization_expires_at,
     created_at, updated_at, started_at, completed_at, failed_at, cancelled_at,
     version, exit_code, stdout, stderr, truncated, duration_ms,
     timeout_exceeded, error_message)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

TASK_SELECT_SQL = """
SELECT id, scope_id, target_id, status, command_json, timeout_seconds,
       max_output_bytes, env_policy_json, authorization_expires_at,
       created_at, updated_at, started_at, completed_at, failed_at, cancelled_at,
       version, exit_code, stdout, stderr, truncated, duration_ms,
       timeout_exceeded, error_message
FROM tasks
"""

TASK_GET_SQL = """
SELECT id, scope_id, target_id, status, command_json, timeout_seconds,
       max_output_bytes, env_policy_json, authorization_expires_at,
       created_at, updated_at, started_at, completed_at, failed_at, cancelled_at,
       version, exit_code, stdout, stderr, truncated, duration_ms,
       timeout_exceeded, error_message
FROM tasks
WHERE id = ?
"""

TASK_UPDATE_SQL = """
UPDATE tasks
SET status = ?, command_json = ?, timeout_seconds = ?, max_output_bytes = ?,
    env_policy_json = ?, authorization_expires_at = ?, created_at = ?,
    updated_at = ?, started_at = ?, completed_at = ?, failed_at = ?,
    cancelled_at = ?, version = ?, exit_code = ?, stdout = ?, stderr = ?,
    truncated = ?, duration_ms = ?, timeout_exceeded = ?, error_message = ?
WHERE id = ? AND version = ?
"""


class SQLiteTaskRepository:
    """Task persistence adapter; transaction ownership stays with UnitOfWork."""

    def __init__(self, unit_of_work: SQLiteUnitOfWork) -> None:
        self.unit_of_work = unit_of_work

    def add(self, record: TaskRecord) -> TaskRecord:
        self._ensure_parent_exists(record)
        try:
            self.unit_of_work.raw.execute(
                TASK_INSERT_SQL,
                task_record_to_params(record),
            )
        except sqlite3.IntegrityError as exc:
            raise self._translate_integrity_error(exc) from exc
        return record

    def get(self, task_id: TaskId) -> TaskRecord | None:
        row = self.unit_of_work.raw.execute(
            TASK_GET_SQL,
            (str(task_id),),
        ).fetchone()
        return task_record_from_row(row) if row is not None else None

    def list_by_scope(self, scope_id: ScopeId) -> Sequence[TaskRecord]:
        rows = self.unit_of_work.raw.execute(
            """
            SELECT id, scope_id, target_id, status, command_json, timeout_seconds,
                   max_output_bytes, env_policy_json, authorization_expires_at,
                   created_at, updated_at, started_at, completed_at, failed_at, cancelled_at,
                   version, exit_code, stdout, stderr, truncated, duration_ms,
                   timeout_exceeded, error_message
            FROM tasks
            WHERE scope_id = ?
            ORDER BY created_at DESC, id ASC
            """,
            (str(scope_id),),
        ).fetchall()
        return tuple(task_record_from_row(row) for row in rows)

    def list_by_target(self, target_id: TargetId) -> Sequence[TaskRecord]:
        rows = self.unit_of_work.raw.execute(
            """
            SELECT id, scope_id, target_id, status, command_json, timeout_seconds,
                   max_output_bytes, env_policy_json, authorization_expires_at,
                   created_at, updated_at, started_at, completed_at, failed_at, cancelled_at,
                   version, exit_code, stdout, stderr, truncated, duration_ms,
                   timeout_exceeded, error_message
            FROM tasks
            WHERE target_id = ?
            ORDER BY created_at DESC, id ASC
            """,
            (str(target_id),),
        ).fetchall()
        return tuple(task_record_from_row(row) for row in rows)

    def update_status_and_result(
        self,
        record: TaskRecord,
        *,
        expected_version: int,
    ) -> TaskRecord:
        current = self._require(record.task.id)
        if (
            current.task.scope_id != record.task.scope_id
            or current.task.target_id != record.task.target_id
        ):
            raise CyberOSError(
                ErrorCode.TASK_IDENTITY_IMMUTABLE,
                "A Task cannot move to another Scope or Target.",
            )
        params = task_record_to_params(record)[3:] + (
            str(record.task.id),
            expected_version,
        )
        try:
            cursor = self.unit_of_work.raw.execute(
                TASK_UPDATE_SQL,
                params,
            )
        except sqlite3.IntegrityError as exc:
            raise self._translate_integrity_error(exc) from exc
        if cursor.rowcount == 0:
            self._raise_update_conflict(record.task.id)
        return self._require(record.task.id)

    def _ensure_parent_exists(self, record: TaskRecord) -> None:
        scope = self.unit_of_work.raw.execute(
            "SELECT 1 FROM scopes WHERE id = ? LIMIT 1", (str(record.task.scope_id),)
        ).fetchone()
        if scope is None:
            raise CyberOSError(ErrorCode.SCOPE_NOT_FOUND, "The Task Scope does not exist.")
        target = self.unit_of_work.raw.execute(
            "SELECT 1 FROM targets WHERE id = ? LIMIT 1", (str(record.task.target_id),)
        ).fetchone()
        if target is None:
            raise CyberOSError(ErrorCode.TARGET_NOT_FOUND, "The Task Target does not exist.")

    def _require(self, task_id: TaskId) -> TaskRecord:
        record = self.get(task_id)
        if record is None:
            raise CyberOSError(ErrorCode.TASK_NOT_FOUND, "The Task does not exist.")
        return record

    def _raise_update_conflict(self, task_id: TaskId) -> None:
        if self.get(task_id) is None:
            raise CyberOSError(ErrorCode.TASK_NOT_FOUND, "The Task does not exist.")
        raise CyberOSError(ErrorCode.CONCURRENCY_CONFLICT, "The Task version is stale.")

    @staticmethod
    def _translate_integrity_error(error: sqlite3.IntegrityError) -> CyberOSError:
        message = str(error).lower()
        if "foreign key constraint failed" in message:
            return CyberOSError(
                ErrorCode.INVALID_INPUT,
                "The Task parent relationship is invalid.",
            )
        return CyberOSError(
            ErrorCode.INVALID_INPUT,
            "The Task data violates a database constraint.",
        )
