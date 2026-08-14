from __future__ import annotations

import sqlite3

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.time import utc_now
from cyberos.domain.recon.evidence import EvidenceId, EvidenceRecord, EvidenceStatus
from cyberos.domain.recon.model import AssetId
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.task.primitives import TaskId
from cyberos.persistence.mappers.evidence import evidence_from_row, evidence_to_params
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork

EVIDENCE_SELECT = (
    "SELECT id, scope_id, target_id, task_id, asset_id, observation_id, kind, title, "
    "content_digest, content_size_bytes, metadata_json, source_plugin_id, "
    "source_plugin_version, pipeline_id, pipeline_version, collected_at, status, "
    "version, created_at, updated_at, archived_at FROM evidence_records"
)
EVIDENCE_INSERT = (
    "INSERT INTO evidence_records (id, scope_id, target_id, task_id, asset_id, "
    "observation_id, kind, title, content_digest, content_size_bytes, metadata_json, "
    "source_plugin_id, source_plugin_version, pipeline_id, pipeline_version, "
    "collected_at, status, version, created_at, updated_at, archived_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
LIST_BY_TASK = EVIDENCE_SELECT + " WHERE task_id = ?"
LIST_BY_ASSET = EVIDENCE_SELECT + " WHERE asset_id = ?"
LIST_BY_SCOPE = EVIDENCE_SELECT + " WHERE scope_id = ?"


class SQLiteReconEvidenceRepository:
    """SQLite adapter; callers own the UnitOfWork transaction lifecycle."""

    def __init__(self, unit_of_work: SQLiteUnitOfWork) -> None:
        self.unit_of_work = unit_of_work

    def add(self, record: EvidenceRecord) -> EvidenceRecord:
        self._ensure_parent_context(record)
        existing = self._find_idempotent(record)
        if existing is not None:
            return existing
        try:
            self.unit_of_work.raw.execute(
                EVIDENCE_INSERT,
                evidence_to_params(record),
            )
        except sqlite3.IntegrityError as exc:
            raise self._translate_integrity_error(exc) from exc
        return record

    def get(self, evidence_id: EvidenceId) -> EvidenceRecord | None:
        row = self.unit_of_work.raw.execute(
            EVIDENCE_SELECT + " WHERE id = ?",
            (str(evidence_id),),
        ).fetchone()
        return evidence_from_row(row) if row is not None else None

    def list_by_task(
        self, task_id: TaskId, *, include_archived: bool = False
    ) -> tuple[EvidenceRecord, ...]:
        return self._list("task_id", str(task_id), include_archived=include_archived)

    def list_by_asset(
        self, asset_id: AssetId, *, include_archived: bool = False
    ) -> tuple[EvidenceRecord, ...]:
        return self._list("asset_id", str(asset_id), include_archived=include_archived)

    def list_by_scope(
        self, scope_id: ScopeId, *, include_archived: bool = False
    ) -> tuple[EvidenceRecord, ...]:
        return self._list("scope_id", str(scope_id), include_archived=include_archived)

    def archive(self, evidence_id: EvidenceId, *, expected_version: int) -> EvidenceRecord:
        current = self.get(evidence_id)
        if current is None:
            raise CyberOSError(ErrorCode.RECON_EVIDENCE_NOT_FOUND, "Evidence does not exist.")
        if current.status is EvidenceStatus.ARCHIVED:
            raise CyberOSError(ErrorCode.RECON_EVIDENCE_ARCHIVED, "Evidence is already archived.")
        if current.version != expected_version:
            raise CyberOSError(ErrorCode.CONCURRENCY_CONFLICT, "Evidence version is stale.")
        timestamp = utc_now().isoformat()
        cursor = self.unit_of_work.raw.execute(
            "UPDATE evidence_records SET status = 'archived', archived_at = ?, "
            "updated_at = ?, version = version + 1 WHERE id = ? AND version = ?",
            (timestamp, timestamp, str(evidence_id), expected_version),
        )
        if cursor.rowcount != 1:
            raise CyberOSError(ErrorCode.CONCURRENCY_CONFLICT, "Evidence version is stale.")
        updated = self.get(evidence_id)
        if updated is None:
            raise CyberOSError(ErrorCode.RECON_EVIDENCE_NOT_FOUND, "Evidence disappeared.")
        return updated

    def _list(
        self, field: str, value: str, *, include_archived: bool
    ) -> tuple[EvidenceRecord, ...]:
        query = {
            "task_id": LIST_BY_TASK,
            "asset_id": LIST_BY_ASSET,
            "scope_id": LIST_BY_SCOPE,
        }[field]
        parameters: tuple[str, ...] = (value,)
        if not include_archived:
            query += " AND status = 'active'"
        query += " ORDER BY collected_at DESC, id ASC"
        rows = self.unit_of_work.raw.execute(query, parameters).fetchall()
        return tuple(evidence_from_row(row) for row in rows)

    def _find_idempotent(self, record: EvidenceRecord) -> EvidenceRecord | None:
        row = self.unit_of_work.raw.execute(
            EVIDENCE_SELECT + " WHERE task_id = ? AND asset_id = ? "
            "AND observation_id IS ? AND kind = ? AND content_digest = ?",
            (
                str(record.task_id),
                str(record.asset_id),
                str(record.observation_id) if record.observation_id is not None else None,
                record.kind.value,
                record.content_digest,
            ),
        ).fetchone()
        return evidence_from_row(row) if row is not None else None

    def _ensure_parent_context(self, record: EvidenceRecord) -> None:
        task = self.unit_of_work.raw.execute(
            "SELECT 1 FROM tasks WHERE id = ? AND scope_id = ? AND target_id = ?",
            (str(record.task_id), str(record.scope_id), str(record.target_id)),
        ).fetchone()
        asset = self.unit_of_work.raw.execute(
            "SELECT 1 FROM assets WHERE id = ? AND scope_id = ? AND target_id = ?",
            (str(record.asset_id), str(record.scope_id), str(record.target_id)),
        ).fetchone()
        if task is None or asset is None:
            raise CyberOSError(
                ErrorCode.RECON_EVIDENCE_PROVENANCE_INVALID,
                "Evidence parent Task/Scope/Target/Asset context is invalid.",
            )
        if record.observation_id is not None:
            observation = self.unit_of_work.raw.execute(
                "SELECT 1 FROM asset_observations WHERE id = ? AND asset_id = ? "
                "AND scope_id = ? AND target_id = ? AND task_id = ?",
                (
                    str(record.observation_id),
                    str(record.asset_id),
                    str(record.scope_id),
                    str(record.target_id),
                    str(record.task_id),
                ),
            ).fetchone()
            if observation is None:
                raise CyberOSError(
                    ErrorCode.RECON_EVIDENCE_PROVENANCE_INVALID,
                    "Evidence observation provenance is invalid.",
                )

    @staticmethod
    def _translate_integrity_error(error: sqlite3.IntegrityError) -> CyberOSError:
        message = str(error).lower()
        if "foreign key" in message:
            return CyberOSError(
                ErrorCode.RECON_EVIDENCE_PROVENANCE_INVALID,
                "Evidence parent relationship is invalid.",
            )
        if "unique" in message:
            return CyberOSError(
                ErrorCode.RECON_EVIDENCE_DUPLICATE,
                "Evidence idempotency identity already exists.",
            )
        return CyberOSError(
            ErrorCode.RECON_EVIDENCE_INVALID,
            "Evidence data violates a database constraint.",
        )
