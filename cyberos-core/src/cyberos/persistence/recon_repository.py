from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from uuid import UUID

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.recon.model import (
    AssetAggregate,
    AssetId,
    AssetKind,
    AssetObservation,
    AssetObservationId,
    DiscoveredHttpEndpoint,
    DiscoveredService,
    DiscoveredSubdomain,
    ReconIngestion,
)
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.primitives import TargetId
from cyberos.persistence.mappers.recon import asset_from_row, asset_to_params
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork

ASSET_SELECT = """
SELECT id, scope_id, target_id, asset_kind, canonical_value, display_value,
       status, first_seen_at, last_seen_at, first_seen_task_id,
       last_seen_task_id, created_at, updated_at, archived_at, version
FROM assets
"""
ASSET_INSERT = """
INSERT INTO assets
    (id, scope_id, target_id, asset_kind, canonical_value, display_value,
     status, first_seen_at, last_seen_at, first_seen_task_id,
     last_seen_task_id, created_at, updated_at, archived_at, version)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


class SQLiteReconRepository:
    """Persistence adapter; UnitOfWork owns transaction lifecycle."""

    def __init__(self, unit_of_work: SQLiteUnitOfWork) -> None:
        self.unit_of_work = unit_of_work

    def ingest(self, ingestion: ReconIngestion) -> AssetAggregate:
        self._ensure_parents(ingestion)
        asset = self._upsert_asset(ingestion.asset)
        self._insert_observation(ingestion.observation, asset.id)
        self._insert_typed_record(ingestion, asset)
        return asset

    def get_asset(self, asset_id: AssetId) -> AssetAggregate | None:
        row = self.unit_of_work.raw.execute(
            ASSET_SELECT + "WHERE id = ?", (str(asset_id),)
        ).fetchone()
        return asset_from_row(row) if row is not None else None

    def find_asset(
        self,
        scope_id: ScopeId,
        target_id: TargetId,
        asset_kind: AssetKind,
        canonical_value: str,
    ) -> AssetAggregate | None:
        row = self.unit_of_work.raw.execute(
            ASSET_SELECT + "WHERE scope_id = ? AND target_id = ? AND asset_kind = ? "
            "AND canonical_value = ?",
            (str(scope_id), str(target_id), asset_kind.value, canonical_value),
        ).fetchone()
        return asset_from_row(row) if row is not None else None

    def list_assets(
        self, scope_id: ScopeId, target_id: TargetId | None = None
    ) -> tuple[AssetAggregate, ...]:
        query = ASSET_SELECT + "WHERE scope_id = ?"
        parameters: tuple[str, ...] = (str(scope_id),)
        if target_id is not None:
            query += " AND target_id = ?"
            parameters += (str(target_id),)
        query += " ORDER BY last_seen_at DESC, id ASC"
        rows = self.unit_of_work.raw.execute(query, parameters).fetchall()
        return tuple(asset_from_row(row) for row in rows)

    def list_observations(self, asset_id: AssetId) -> tuple[AssetObservation, ...]:
        rows = self.unit_of_work.raw.execute(
            "SELECT id, asset_id, scope_id, target_id, task_id, plugin_id, "
            "plugin_version, contract_version, result_digest, observed_at, created_at "
            "FROM asset_observations WHERE asset_id = ? "
            "ORDER BY observed_at ASC, id ASC",
            (str(asset_id),),
        ).fetchall()
        return tuple(self._observation_from_row(row) for row in rows)

    def archive_asset(self, asset_id: AssetId, *, expected_version: int) -> AssetAggregate:
        current = self.get_asset(asset_id)
        if current is None:
            raise CyberOSError(ErrorCode.RECON_NOT_FOUND, "The Recon asset does not exist.")
        if current.version != expected_version:
            raise CyberOSError(ErrorCode.CONCURRENCY_CONFLICT, "The Recon asset version is stale.")
        now = current.updated_at.astimezone(UTC).isoformat()
        cursor = self.unit_of_work.raw.execute(
            "UPDATE assets SET status = 'archived', archived_at = ?, "
            "updated_at = ?, version = version + 1 WHERE id = ? AND version = ?",
            (now, now, str(asset_id), expected_version),
        )
        if cursor.rowcount != 1:
            raise CyberOSError(ErrorCode.CONCURRENCY_CONFLICT, "The Recon asset version is stale.")
        row = self.unit_of_work.raw.execute(
            ASSET_SELECT + "WHERE id = ?", (str(asset_id),)
        ).fetchone()
        if row is None:
            raise CyberOSError(ErrorCode.RECON_NOT_FOUND, "The Recon asset disappeared.")
        return asset_from_row(row)

    def _upsert_asset(self, asset: AssetAggregate) -> AssetAggregate:
        row = self.unit_of_work.raw.execute(
            ASSET_SELECT + "WHERE scope_id = ? AND target_id = ? AND asset_kind = ? "
            "AND canonical_value = ?",
            (
                str(asset.scope_id),
                str(asset.target_id),
                asset.asset_kind.value,
                asset.canonical_value,
            ),
        ).fetchone()
        if row is None:
            try:
                self.unit_of_work.raw.execute(ASSET_INSERT, asset_to_params(asset))
            except sqlite3.IntegrityError as exc:
                raise self._translate_integrity_error(exc) from exc
            return asset

        current = asset_from_row(row)
        if current.status.value == "archived":
            raise CyberOSError(
                ErrorCode.RECON_CORRELATION_CONFLICT,
                "Archived asset cannot be silently reactivated.",
            )
        try:
            self.unit_of_work.raw.execute(
                "UPDATE assets SET display_value = ?, last_seen_at = ?, "
                "last_seen_task_id = ?, updated_at = ?, version = version + 1 "
                "WHERE id = ?",
                (
                    asset.display_value,
                    asset.last_seen_at.isoformat(),
                    str(asset.last_seen_task_id),
                    asset.updated_at.isoformat(),
                    str(current.id),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise self._translate_integrity_error(exc) from exc
        updated = self.get_asset(current.id)
        if updated is None:
            raise CyberOSError(ErrorCode.RECON_NOT_FOUND, "The Recon asset disappeared.")
        return updated

    def _insert_observation(self, observation: AssetObservation, asset_id: AssetId) -> None:
        try:
            self.unit_of_work.raw.execute(
                "INSERT OR IGNORE INTO asset_observations "
                "(id, asset_id, scope_id, target_id, task_id, plugin_id, "
                "plugin_version, contract_version, result_digest, observed_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(observation.id),
                    str(asset_id),
                    str(observation.scope_id),
                    str(observation.target_id),
                    str(observation.task_id),
                    observation.plugin_id,
                    observation.plugin_version,
                    observation.contract_version,
                    observation.result_digest,
                    observation.observed_at.isoformat(),
                    observation.created_at.isoformat(),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise self._translate_integrity_error(exc) from exc

    def _insert_typed_record(self, ingestion: ReconIngestion, asset: AssetAggregate) -> None:
        record = asset.record
        if record is None:
            return
        common = (
            str(asset.id),
            str(asset.scope_id),
            str(asset.target_id),
            str(ingestion.task_id),
            "active",
            asset.first_seen_at.isoformat(),
            asset.last_seen_at.isoformat(),
            asset.created_at.isoformat(),
            asset.updated_at.isoformat(),
            None,
            1,
        )
        try:
            if isinstance(record, DiscoveredSubdomain):
                self.unit_of_work.raw.execute(
                    "INSERT OR IGNORE INTO subdomain_records "
                    "(id, asset_id, scope_id, target_id, task_id, fqdn, parent_domain, "
                    "status, first_seen_at, last_seen_at, created_at, updated_at, "
                    "archived_at, version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(asset.id),
                        str(asset.id),
                        *common[1:4],
                        record.fqdn,
                        record.parent_domain,
                        *common[4:],
                    ),
                )
            elif isinstance(record, DiscoveredService):
                self.unit_of_work.raw.execute(
                    "INSERT OR IGNORE INTO port_service_records "
                    "(id, asset_id, scope_id, target_id, task_id, transport, port, "
                    "service_name, product, service_version, status, first_seen_at, "
                    "last_seen_at, created_at, updated_at, archived_at, version) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(asset.id),
                        str(asset.id),
                        *common[1:4],
                        record.transport,
                        record.port,
                        record.service_name,
                        record.product,
                        record.service_version,
                        *common[4:],
                    ),
                )
            elif isinstance(record, DiscoveredHttpEndpoint):
                self.unit_of_work.raw.execute(
                    "INSERT OR IGNORE INTO http_endpoint_records "
                    "(id, asset_id, scope_id, target_id, task_id, scheme, port, path, "
                    "query_fingerprint, status_code, title, technologies_json, status, "
                    "first_seen_at, last_seen_at, created_at, updated_at, archived_at, version) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(asset.id),
                        str(asset.id),
                        *common[1:4],
                        record.scheme,
                        record.port,
                        record.path,
                        record.query_fingerprint,
                        record.status_code,
                        record.title,
                        record.technologies_json,
                        *common[4:],
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise self._translate_integrity_error(exc) from exc

    def _ensure_parents(self, ingestion: ReconIngestion) -> None:
        target = self.unit_of_work.raw.execute(
            "SELECT 1 FROM targets WHERE id = ? AND scope_id = ?",
            (str(ingestion.target_id), str(ingestion.scope_id)),
        ).fetchone()
        task = self.unit_of_work.raw.execute(
            "SELECT 1 FROM tasks WHERE id = ? AND scope_id = ? AND target_id = ?",
            (
                str(ingestion.task_id),
                str(ingestion.scope_id),
                str(ingestion.target_id),
            ),
        ).fetchone()
        if target is None or task is None:
            raise CyberOSError(
                ErrorCode.RECON_PARENT_NOT_FOUND,
                "Recon parent Scope/Target/Task does not exist.",
            )

    @staticmethod
    def _observation_from_row(row: sqlite3.Row) -> AssetObservation:
        return AssetObservation(
            id=AssetObservationId(UUID(row["id"])),
            asset_id=AssetId(UUID(row["asset_id"])),
            scope_id=ScopeId(UUID(row["scope_id"])),
            target_id=TargetId(UUID(row["target_id"])),
            task_id=UUID(row["task_id"]),
            plugin_id=row["plugin_id"],
            plugin_version=row["plugin_version"],
            contract_version=row["contract_version"],
            result_digest=row["result_digest"],
            observed_at=datetime.fromisoformat(row["observed_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _translate_integrity_error(error: sqlite3.IntegrityError) -> CyberOSError:
        message = str(error).lower()
        if "foreign key" in message:
            return CyberOSError(
                ErrorCode.RECON_PARENT_NOT_FOUND,
                "Recon parent relationship is invalid.",
            )
        if "unique" in message:
            return CyberOSError(
                ErrorCode.RECON_ASSET_DUPLICATE,
                "Recon identity already exists.",
            )
        return CyberOSError(
            ErrorCode.RECON_RECORD_INVALID,
            "Recon data violates a database constraint.",
        )
