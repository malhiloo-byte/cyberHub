from __future__ import annotations

from datetime import datetime

from cyberos.application.scope_validation import ExecutionAuthorization
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.recon.evidence import (
    EvidenceFactory,
    EvidenceKind,
    EvidenceRecord,
    JSONMetadata,
)
from cyberos.domain.recon.model import AssetAggregate, AssetObservation
from cyberos.domain.task.model import Task
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.recon_evidence_repository import SQLiteReconEvidenceRepository
from cyberos.persistence.recon_repository import SQLiteReconRepository
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork


class ReconEvidenceService:
    """Creates Evidence only from already committed Recon asset provenance."""

    def __init__(self, factory: SQLiteConnectionFactory) -> None:
        self.factory = factory

    def create_from_observation(
        self,
        task: Task,
        authorization: ExecutionAuthorization,
        asset: AssetAggregate,
        observation: AssetObservation,
        *,
        kind: EvidenceKind,
        title: str,
        metadata: JSONMetadata,
        pipeline_id: str | None = None,
        pipeline_version: str | None = None,
        collected_at: datetime | None = None,
    ) -> EvidenceRecord:
        record = EvidenceFactory.from_observation(
            task,
            authorization,
            asset,
            observation,
            kind=kind,
            title=title,
            metadata=metadata,
            pipeline_id=pipeline_id,
            pipeline_version=pipeline_version,
            collected_at=collected_at,
        )
        with SQLiteUnitOfWork(self.factory) as unit:
            recon = SQLiteReconRepository(unit)
            stored_asset = recon.get_asset(asset.id)
            stored_observations = recon.list_observations(asset.id)
            stored_observation = next(
                (item for item in stored_observations if item.id == observation.id), None
            )
            if (
                stored_asset is None
                or stored_observation is None
                or stored_asset != asset
                or stored_observation != observation
            ):
                raise CyberOSError(
                    ErrorCode.RECON_EVIDENCE_PROVENANCE_INVALID,
                    "Evidence requires committed Recon provenance.",
                )
            persisted = SQLiteReconEvidenceRepository(unit).add(record)
            unit.commit()
            return persisted
