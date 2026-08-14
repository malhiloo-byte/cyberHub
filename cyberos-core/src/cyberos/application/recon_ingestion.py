from __future__ import annotations

import hashlib
import json
from datetime import datetime
from urllib.parse import urlsplit

from cyberos.application.scope_validation import ExecutionAuthorization
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.time import ensure_utc, utc_now
from cyberos.domain.recon.model import (
    AssetAggregate,
    AssetKind,
    AssetObservation,
    AssetStatus,
    DiscoveredHttpEndpoint,
    DiscoveredService,
    DiscoveredSubdomain,
    ReconIngestion,
    ReconIngestionReceipt,
    ReconRecord,
    new_asset_id,
    new_observation_id,
)
from cyberos.domain.target.canonicalization import TargetCanonicalizer
from cyberos.domain.target.primitives import TargetKind
from cyberos.domain.task.model import Task
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.recon_repository import SQLiteReconRepository
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork
from cyberos.recon.contracts import ExecutionLimits, ReconObservation, ReconResult, ReconStatus


class ReconIngestionService:
    """Persist only successful, already-authorized, target-bound ReconResults."""

    def __init__(self, factory: SQLiteConnectionFactory) -> None:
        self.factory = factory

    def ingest(
        self,
        *,
        task: Task,
        authorization: ExecutionAuthorization,
        result: ReconResult,
        effective_limits: ExecutionLimits,
        observed_at: datetime | None = None,
    ) -> ReconIngestionReceipt:
        timestamp = ensure_utc(observed_at) if observed_at else utc_now()
        self._validate_boundary(task, authorization, result, effective_limits, timestamp)
        ingestions = tuple(
            self._to_ingestion(task, result, value, timestamp) for value in result.observations
        )
        inserted = 0
        updated = 0
        with SQLiteUnitOfWork(self.factory) as unit:
            repository = SQLiteReconRepository(unit)
            for ingestion in ingestions:
                current = repository.find_asset(
                    ingestion.scope_id,
                    ingestion.target_id,
                    ingestion.asset.asset_kind,
                    ingestion.asset.canonical_value,
                )
                repository.ingest(ingestion)
                inserted += 1 if current is None else 0
                updated += 1 if current is not None else 0
            unit.commit()
        return ReconIngestionReceipt(
            task_id=result.task_id,
            inserted_assets=inserted,
            inserted_observations=len(ingestions),
            updated_assets=updated,
        )

    @staticmethod
    def _validate_boundary(
        task: Task,
        authorization: ExecutionAuthorization,
        result: ReconResult,
        limits: ExecutionLimits,
        now: datetime,
    ) -> None:
        task_id = task.id
        scope_id = task.scope_id
        target_id = task.target_id
        spec = task.execution_spec
        if result.status is not ReconStatus.SUCCESS or not result.observations:
            raise CyberOSError(
                ErrorCode.RECON_RESULT_INVALID,
                "Only successful non-empty ReconResults can be persisted.",
            )
        if (
            result.task_id != task_id
            or result.scope_id != scope_id
            or result.target_id != target_id
        ):
            raise CyberOSError(
                ErrorCode.RECON_RESULT_INVALID, "ReconResult identity is not Task-bound."
            )
        if authorization.scope_id != scope_id or authorization.matched_target_id != target_id:
            raise CyberOSError(
                ErrorCode.RECON_AUTHORIZATION_INVALID,
                "Authorization is not Scope/Target-bound to Task.",
            )
        if authorization.expires_at is not None and now > authorization.expires_at:
            raise CyberOSError(ErrorCode.RECON_AUTHORIZATION_INVALID, "Authorization has expired.")
        if (
            limits.max_output_bytes > spec.max_output_bytes
            or limits.timeout_seconds > spec.timeout_seconds
        ):
            raise CyberOSError(
                ErrorCode.PLUGIN_LIMIT_EXCEEDED, "Effective plugin limits exceed Task limits."
            )
        result.validate_within(limits)

    @classmethod
    def _to_ingestion(
        cls, task: Task, result: ReconResult, observation: ReconObservation, timestamp: datetime
    ) -> ReconIngestion:
        metadata = dict(observation.metadata)
        record, kind, canonical, display = cls._record(observation, metadata)
        task_id = result.task_id
        scope_id = result.scope_id
        target_id = result.target_id
        digest = hashlib.sha256(
            json.dumps(observation.to_payload(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        asset = AssetAggregate(
            id=new_asset_id(),
            scope_id=scope_id,
            target_id=target_id,
            asset_kind=kind,
            canonical_value=canonical,
            display_value=display,
            status=AssetStatus.ACTIVE,
            first_seen_at=timestamp,
            last_seen_at=timestamp,
            first_seen_task_id=task_id,
            last_seen_task_id=task_id,
            created_at=timestamp,
            updated_at=timestamp,
            archived_at=None,
            version=1,
            record=record,
        )
        obs = AssetObservation(
            id=new_observation_id(),
            asset_id=asset.id,
            scope_id=scope_id,
            target_id=target_id,
            task_id=task_id,
            plugin_id=result.plugin_id,
            plugin_version=result.plugin_version,
            contract_version=result.contract_version,
            result_digest=digest,
            observed_at=timestamp,
            created_at=timestamp,
        )
        return ReconIngestion(
            task_id=task_id,
            scope_id=scope_id,
            target_id=target_id,
            plugin_id=result.plugin_id,
            plugin_version=result.plugin_version,
            contract_version=result.contract_version,
            result=result,
            asset=asset,
            observation=obs,
        )

    @staticmethod
    def _record(
        observation: ReconObservation, metadata: dict[str, str]
    ) -> tuple[ReconRecord, AssetKind, str, str]:
        if not isinstance(observation.value, str) or not observation.value.strip():
            raise CyberOSError(
                ErrorCode.RECON_RECORD_INVALID, "Recon observation value must be non-empty text."
            )
        value = observation.value.strip()
        if observation.observation_type == "subdomain":
            canonical = TargetCanonicalizer.canonicalize(TargetKind.FQDN, value).value
            parent = TargetCanonicalizer.canonicalize(
                TargetKind.FQDN, metadata.get("parent_domain", canonical.split(".", 1)[-1])
            ).value
            return DiscoveredSubdomain(canonical, parent), AssetKind.SUBDOMAIN, canonical, canonical
        if observation.observation_type == "service":
            transport = metadata.get("transport", "tcp")
            port = int(metadata.get("port", "1"))
            service_record = DiscoveredService(
                transport,
                port,
                metadata.get("service_name"),
                metadata.get("product"),
                metadata.get("service_version"),
            )
            return service_record, AssetKind.SERVICE, f"{transport}:{port}:{value}", value
        if observation.observation_type == "http_endpoint":
            parsed = urlsplit(value)
            scheme = parsed.scheme.lower()
            port = int(metadata.get("port", str(parsed.port or (443 if scheme == "https" else 80))))
            path = parsed.path or "/"
            endpoint_record = DiscoveredHttpEndpoint(
                scheme,
                port,
                path,
                metadata.get("query_fingerprint"),
                int(metadata["status_code"]) if "status_code" in metadata else None,
                metadata.get("title"),
                metadata.get("technologies_json", "[]"),
            )
            canonical = TargetCanonicalizer.canonicalize(TargetKind.URL, value).value
            return endpoint_record, AssetKind.URL, canonical, canonical
        if observation.observation_type == "asset":
            kind = AssetKind(metadata.get("asset_kind", "host"))
            return None, kind, value, value
        raise CyberOSError(
            ErrorCode.RECON_RECORD_INVALID, "Unsupported observation_type for persistence."
        )
