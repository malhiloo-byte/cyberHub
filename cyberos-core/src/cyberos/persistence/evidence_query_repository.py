from __future__ import annotations

import sqlite3

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.recon.evidence import EvidenceRecord
from cyberos.domain.recon.evidence_query import (
    EvidenceCursor,
    EvidenceQuery,
    EvidenceQueryPort,
    EvidenceRecordPage,
    EvidenceSort,
)
from cyberos.persistence.mappers.evidence import evidence_from_row
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork

_SELECT = (
    "SELECT id, scope_id, target_id, task_id, asset_id, observation_id, kind, title, "
    "content_digest, content_size_bytes, metadata_json, source_plugin_id, "
    "source_plugin_version, pipeline_id, pipeline_version, collected_at, status, "
    "version, created_at, updated_at, archived_at FROM evidence_records"
)

_ORDER_BY = {
    EvidenceSort.COLLECTED_AT_DESC: " ORDER BY collected_at DESC, id ASC",
    EvidenceSort.CREATED_AT_DESC: " ORDER BY created_at DESC, id ASC",
    EvidenceSort.KIND_ASC: " ORDER BY kind ASC, collected_at DESC, id ASC",
    EvidenceSort.STATUS_ASC: " ORDER BY status ASC, collected_at DESC, id ASC",
}

_KEYSET = {
    EvidenceSort.COLLECTED_AT_DESC: (
        " AND (? IS NULL OR collected_at < ? OR (collected_at = ? AND id > ?))"
    ),
    EvidenceSort.CREATED_AT_DESC: (
        " AND (? IS NULL OR created_at < ? OR (created_at = ? AND id > ?))"
    ),
    EvidenceSort.KIND_ASC: (
        " AND (? IS NULL OR kind > ? OR "
        "(kind = ? AND (collected_at < ? OR "
        "(collected_at = ? AND id > ?))))"
    ),
    EvidenceSort.STATUS_ASC: (
        " AND (? IS NULL OR status > ? OR "
        "(status = ? AND (collected_at < ? OR "
        "(collected_at = ? AND id > ?))))"
    ),
}

_CONTEXT_TARGET_SCOPE = "SELECT 1 FROM targets WHERE id = ? AND scope_id = ?"
_CONTEXT_TASK_SCOPE = "SELECT 1 FROM tasks WHERE id = ? AND scope_id = ?"
_CONTEXT_ASSET_SCOPE = "SELECT 1 FROM assets WHERE id = ? AND scope_id = ?"
_CONTEXT_TASK_TARGET = "SELECT 1 FROM tasks WHERE id = ? AND target_id = ?"
_CONTEXT_ASSET_TARGET = "SELECT 1 FROM assets WHERE id = ? AND target_id = ?"
_CONTEXT_ASSET_TASK = (
    "SELECT 1 FROM assets a JOIN tasks t ON t.scope_id = a.scope_id "
    "AND t.target_id = a.target_id WHERE a.id = ? AND t.id = ?"
)


class SQLiteEvidenceQueryRepository(EvidenceQueryPort):
    """Read-only Evidence adapter with static SQL and bounded keyset pages."""

    def __init__(self, unit_of_work: SQLiteUnitOfWork) -> None:
        self.unit_of_work = unit_of_work

    def query(self, query: EvidenceQuery) -> EvidenceRecordPage:
        try:
            self._validate_context(query)
            cursor_values = self._cursor_values(query)
            sql = (
                _SELECT + " WHERE (? IS NULL OR scope_id = ?)"
                " AND (? IS NULL OR target_id = ?)"
                " AND (? IS NULL OR task_id = ?)"
                " AND (? IS NULL OR asset_id = ?)"
                " AND (? IS NULL OR kind = ?)"
                " AND status = ?" + _KEYSET[query.sort] + _ORDER_BY[query.sort] + " LIMIT ?"
            )
            values: tuple[object, ...] = (
                self._uuid_text(query.scope_id),
                self._uuid_text(query.scope_id),
                self._uuid_text(query.target_id),
                self._uuid_text(query.target_id),
                self._uuid_text(query.task_id),
                self._uuid_text(query.task_id),
                self._uuid_text(query.asset_id),
                self._uuid_text(query.asset_id),
                query.kind.value if query.kind is not None else None,
                query.kind.value if query.kind is not None else None,
                query.status.value,
                *cursor_values,
                query.limit + 1,
            )
            rows = self.unit_of_work.raw.execute(sql, values).fetchall()
        except CyberOSError:
            raise
        except sqlite3.Error as exc:
            raise CyberOSError(
                ErrorCode.EVIDENCE_QUERY_STORAGE_FAILED,
                "Evidence query storage operation failed.",
            ) from exc

        has_more = len(rows) > query.limit
        selected = rows[: query.limit]
        records = tuple(evidence_from_row(row) for row in selected)
        next_cursor = self._next_cursor(query, records) if has_more and records else None
        return EvidenceRecordPage(records, next_cursor, has_more)

    def _validate_context(self, query: EvidenceQuery) -> None:
        checks: tuple[tuple[str, tuple[str, str]], ...] = ()
        if query.scope_id is not None and query.target_id is not None:
            checks += ((_CONTEXT_TARGET_SCOPE, (str(query.target_id), str(query.scope_id))),)
        if query.scope_id is not None and query.task_id is not None:
            checks += ((_CONTEXT_TASK_SCOPE, (str(query.task_id), str(query.scope_id))),)
        if query.scope_id is not None and query.asset_id is not None:
            checks += ((_CONTEXT_ASSET_SCOPE, (str(query.asset_id), str(query.scope_id))),)
        if query.target_id is not None and query.task_id is not None:
            checks += ((_CONTEXT_TASK_TARGET, (str(query.task_id), str(query.target_id))),)
        if query.target_id is not None and query.asset_id is not None:
            checks += ((_CONTEXT_ASSET_TARGET, (str(query.asset_id), str(query.target_id))),)
        if query.task_id is not None and query.asset_id is not None:
            checks += ((_CONTEXT_ASSET_TASK, (str(query.asset_id), str(query.task_id))),)
        for sql, values in checks:
            if self.unit_of_work.raw.execute(sql, values).fetchone() is None:
                raise CyberOSError(
                    ErrorCode.EVIDENCE_QUERY_CONTEXT_INVALID,
                    "Evidence query context is inconsistent.",
                )

    @staticmethod
    def _uuid_text(value: object) -> str | None:
        return str(value) if value is not None else None

    @staticmethod
    def _cursor_values(query: EvidenceQuery) -> tuple[object, ...]:
        if query.cursor is None:
            return (None,) * (
                6 if query.sort in {EvidenceSort.KIND_ASC, EvidenceSort.STATUS_ASC} else 4
            )
        if query.cursor.fingerprint != query.fingerprint() or query.cursor.sort is not query.sort:
            raise CyberOSError(
                ErrorCode.EVIDENCE_QUERY_CURSOR_INVALID,
                "Evidence cursor does not match the query.",
            )
        values = query.cursor.position
        expected = 3 if query.sort in {EvidenceSort.KIND_ASC, EvidenceSort.STATUS_ASC} else 3
        if len(values) != expected:
            raise CyberOSError(
                ErrorCode.EVIDENCE_QUERY_CURSOR_INVALID, "Evidence cursor is invalid."
            )
        if query.sort in {EvidenceSort.KIND_ASC, EvidenceSort.STATUS_ASC}:
            return (values[0], values[0], values[0], values[1], values[1], values[2])
        return (values[0], values[0], values[0], values[1])

    @staticmethod
    def _next_cursor(query: EvidenceQuery, records: tuple[EvidenceRecord, ...]) -> EvidenceCursor:
        record = records[-1]
        if query.sort is EvidenceSort.COLLECTED_AT_DESC:
            position = (record.collected_at.isoformat(), str(record.id), "")
        elif query.sort is EvidenceSort.CREATED_AT_DESC:
            position = (record.created_at.isoformat(), str(record.id), "")
        elif query.sort is EvidenceSort.KIND_ASC:
            position = (record.kind.value, record.collected_at.isoformat(), str(record.id))
        else:
            position = (record.status.value, record.collected_at.isoformat(), str(record.id))
        return EvidenceCursor(1, query.fingerprint(), query.sort, position)
