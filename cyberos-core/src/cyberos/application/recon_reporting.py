from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime

from cyberos.application.recon_evidence_query import EvidenceQueryService
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.time import utc_now
from cyberos.domain.recon.evidence import EvidenceStatus
from cyberos.domain.recon.evidence_query import (
    EvidenceQuery,
    EvidenceQueryPage,
    EvidenceReadModel,
    EvidenceSort,
    MetadataMode,
)
from cyberos.domain.recon.model import AssetKind, AssetStatus
from cyberos.domain.recon.reporting import (
    AssetDistributionBreakdown,
    AssetKindDistribution,
    AssetStatusDistribution,
    PipelineSourceSummary,
    PluginSourceSummary,
    ProvenanceAuditSummary,
    ReconAssetReadBundle,
    ReconReportBudget,
    ReconReportContext,
    ReconReportSourcePort,
    ReportSourceWindow,
    TargetReconSummary,
)
from cyberos.domain.task.primitives import TaskId
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.recon_reporting_source import SQLiteReconReportSource
from cyberos.persistence.scope_repository import SQLiteScopeRepository
from cyberos.persistence.target_repository import SQLiteTargetRepository
from cyberos.persistence.task_repository import SQLiteTaskRepository
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork


def _is_synthetic(record: EvidenceReadModel) -> bool:
    return (
        record.metadata is not None
        and record.metadata.get("offline_fixture") is True
        and record.metadata.get("synthetic") is True
    )


@dataclass(frozen=True, slots=True)
class _ReportDataset:
    context: ReconReportContext
    generated_at: datetime
    bundles: tuple[ReconAssetReadBundle, ...]
    active_evidence: tuple[EvidenceReadModel, ...]
    archived_evidence: tuple[EvidenceReadModel, ...]
    source_window: ReportSourceWindow

    @property
    def evidence(self) -> tuple[EvidenceReadModel, ...]:
        return self.active_evidence + self.archived_evidence


class ReconReportingService:
    """Builds bounded, immutable read-only Recon reporting projections."""

    def __init__(
        self,
        factory: SQLiteConnectionFactory,
        *,
        source: ReconReportSourcePort | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.factory = factory
        self.source = source or SQLiteReconReportSource(factory)
        self.clock = clock
        self.evidence_queries = EvidenceQueryService(factory)

    def target_recon_summary(
        self,
        context: ReconReportContext,
        *,
        budget: ReconReportBudget | None = None,
    ) -> TargetReconSummary:
        dataset = self._load(context, budget or ReconReportBudget())
        evidence_by_kind = Counter(record.kind for record in dataset.evidence)
        assets_by_kind = Counter(bundle.asset.asset_kind for bundle in dataset.bundles)
        plugin_counts = Counter(
            (record.source_plugin_id, record.source_plugin_version) for record in dataset.evidence
        )
        pipeline_counts = Counter(
            (record.pipeline_id, record.pipeline_version)
            for record in dataset.evidence
            if record.pipeline_id is not None and record.pipeline_version is not None
        )
        metadata_records = tuple(
            record for record in dataset.evidence if record.metadata is not None
        )
        return TargetReconSummary(
            scope_id=context.scope_id,
            target_id=context.target_id,
            generated_at=dataset.generated_at,
            source_window=dataset.source_window,
            asset_count=len(dataset.bundles),
            observation_count=sum(len(bundle.observations) for bundle in dataset.bundles),
            active_evidence_count=len(dataset.active_evidence),
            archived_evidence_count=len(dataset.archived_evidence),
            evidence_by_kind=dict(evidence_by_kind),
            assets_by_kind=dict(assets_by_kind),
            source_plugins=tuple(
                PluginSourceSummary(plugin_id, version, count)
                for (plugin_id, version), count in sorted(plugin_counts.items())
            ),
            pipelines=tuple(
                PipelineSourceSummary(pipeline_id, version, count)
                for (pipeline_id, version), count in sorted(pipeline_counts.items())
            ),
            provenance=self._provenance(dataset),
            synthetic_fixture_only=bool(metadata_records)
            and all(_is_synthetic(record) for record in metadata_records),
        )

    def asset_distribution_breakdown(
        self,
        context: ReconReportContext,
        *,
        budget: ReconReportBudget | None = None,
    ) -> AssetDistributionBreakdown:
        dataset = self._load(context, budget or ReconReportBudget())
        assets = tuple(bundle.asset for bundle in dataset.bundles)
        observed_ids = {bundle.asset.id for bundle in dataset.bundles if bundle.observations}
        evidence_asset_ids = {record.asset_id for record in dataset.evidence}
        by_kind_counter = Counter(asset.asset_kind for asset in assets)
        by_status_counter = Counter(asset.status for asset in assets)
        return AssetDistributionBreakdown(
            scope_id=context.scope_id,
            target_id=context.target_id,
            generated_at=dataset.generated_at,
            total_assets=len(assets),
            by_kind=tuple(
                AssetKindDistribution(kind, by_kind_counter.get(kind, 0))
                for kind in AssetKind
                if by_kind_counter.get(kind, 0) > 0
            ),
            by_status=tuple(
                AssetStatusDistribution(status, by_status_counter.get(status, 0))
                for status in AssetStatus
                if by_status_counter.get(status, 0) > 0
            ),
            observed_asset_count=len(observed_ids),
            evidence_linked_asset_count=len(evidence_asset_ids),
            unlinked_asset_count=len(set(asset.id for asset in assets) - evidence_asset_ids),
            source_window=dataset.source_window,
        )

    def provenance_audit_summary(
        self,
        context: ReconReportContext,
        *,
        budget: ReconReportBudget | None = None,
    ) -> ProvenanceAuditSummary:
        return self._provenance(self._load(context, budget or ReconReportBudget()))

    def _load(self, context: ReconReportContext, budget: ReconReportBudget) -> _ReportDataset:
        self._validate_context(context)
        bundles = self.source.read_assets(context.scope_id, context.target_id)
        selected_bundles = self._select_task_bundles(bundles, context.task_id)
        asset_count = len(selected_bundles)
        observation_count = sum(len(bundle.observations) for bundle in selected_bundles)
        if asset_count > budget.max_assets or observation_count > budget.max_observations:
            raise CyberOSError(ErrorCode.REPORT_BUDGET_EXCEEDED, "Reporting asset budget exceeded.")

        active, active_pages, active_bytes = self._read_evidence(
            context, EvidenceStatus.ACTIVE, budget
        )
        archived, archived_pages, archived_bytes = self._read_evidence(
            context, EvidenceStatus.ARCHIVED, budget
        )
        total_records = len(active) + len(archived)
        total_pages = active_pages + archived_pages
        total_bytes = active_bytes + archived_bytes
        if total_records > budget.max_evidence_records or total_pages > budget.max_pages:
            raise CyberOSError(
                ErrorCode.REPORT_BUDGET_EXCEEDED, "Reporting evidence budget exceeded."
            )
        if total_bytes > budget.max_metadata_bytes:
            raise CyberOSError(
                ErrorCode.REPORT_BUDGET_EXCEEDED, "Reporting metadata budget exceeded."
            )
        generated_at = self.clock()
        return _ReportDataset(
            context,
            generated_at,
            selected_bundles,
            active,
            archived,
            ReportSourceWindow(
                total_pages, total_records, asset_count, observation_count, total_bytes
            ),
        )

    def _read_evidence(
        self,
        context: ReconReportContext,
        status: EvidenceStatus,
        budget: ReconReportBudget,
    ) -> tuple[tuple[EvidenceReadModel, ...], int, int]:
        query = EvidenceQuery(
            scope_id=context.scope_id,
            target_id=context.target_id,
            task_id=context.task_id,
            status=status,
            sort=EvidenceSort.COLLECTED_AT_DESC,
            limit=min(200, budget.max_evidence_records),
            metadata_mode=MetadataMode.SAFE_METADATA,
        )
        records: list[EvidenceReadModel] = []
        pages = 0
        metadata_bytes = 0
        while True:
            if pages >= budget.max_pages:
                raise CyberOSError(
                    ErrorCode.REPORT_BUDGET_EXCEEDED, "Reporting page budget exceeded."
                )
            page: EvidenceQueryPage = self.evidence_queries.query(query)
            pages += 1
            records.extend(page.items)
            metadata_bytes += sum(
                len(
                    json.dumps(
                        dict(record.metadata), separators=(",", ":"), ensure_ascii=False
                    ).encode("utf-8")
                )
                for record in page.items
                if record.metadata is not None
            )
            if len(records) > budget.max_evidence_records:
                raise CyberOSError(
                    ErrorCode.REPORT_BUDGET_EXCEEDED, "Reporting evidence budget exceeded."
                )
            if not page.has_more:
                return tuple(records), pages, metadata_bytes
            if page.next_cursor is None:
                raise CyberOSError(
                    ErrorCode.REPORT_DATA_INCONSISTENT, "Evidence page cursor is missing."
                )
            query = replace(query, cursor=page.next_cursor)

    def _validate_context(self, context: ReconReportContext) -> None:
        with SQLiteUnitOfWork(self.factory) as unit:
            if SQLiteScopeRepository(unit).get(context.scope_id) is None:
                raise CyberOSError(
                    ErrorCode.REPORT_QUERY_INVALID, "Report Scope context is invalid."
                )
            if context.target_id is not None:
                target = SQLiteTargetRepository(unit).get(context.target_id)
                if target is None or target.scope_id != context.scope_id:
                    raise CyberOSError(
                        ErrorCode.REPORT_QUERY_INVALID, "Report target context is invalid."
                    )
            if context.task_id is not None:
                task_record = SQLiteTaskRepository(unit).get(context.task_id)
                if (
                    task_record is None
                    or task_record.task.scope_id != context.scope_id
                    or (
                        context.target_id is not None
                        and task_record.task.target_id != context.target_id
                    )
                ):
                    raise CyberOSError(
                        ErrorCode.REPORT_QUERY_INVALID, "Report task context is invalid."
                    )
            unit.rollback()

    @staticmethod
    def _select_task_bundles(
        bundles: tuple[ReconAssetReadBundle, ...], task_id: TaskId | None
    ) -> tuple[ReconAssetReadBundle, ...]:
        if task_id is None:
            return bundles
        return tuple(
            ReconAssetReadBundle(
                bundle.asset,
                tuple(
                    observation
                    for observation in bundle.observations
                    if observation.task_id == task_id
                ),
            )
            for bundle in bundles
            if any(observation.task_id == task_id for observation in bundle.observations)
        )

    @staticmethod
    def _provenance(dataset: _ReportDataset) -> ProvenanceAuditSummary:
        evidence = dataset.evidence
        asset_ids = {bundle.asset.id for bundle in dataset.bundles}
        observation_ids = {
            observation.id for bundle in dataset.bundles for observation in bundle.observations
        }
        context = dataset.context
        cross_context = sum(
            record.scope_id != context.scope_id
            or (context.target_id is not None and record.target_id != context.target_id)
            or (context.task_id is not None and record.task_id != context.task_id)
            for record in evidence
        )
        missing_parent = sum(
            record.asset_id not in asset_ids
            or (record.observation_id is not None and record.observation_id not in observation_ids)
            for record in evidence
        )
        synthetic = sum(_is_synthetic(record) for record in evidence)
        return ProvenanceAuditSummary(
            total_evidence=len(evidence),
            active_evidence=len(dataset.active_evidence),
            archived_evidence=len(dataset.archived_evidence),
            distinct_task_count=len({record.task_id for record in evidence}),
            distinct_asset_count=len({record.asset_id for record in evidence}),
            distinct_observation_count=len(
                {record.observation_id for record in evidence if record.observation_id is not None}
            ),
            distinct_plugin_count=len(
                {(record.source_plugin_id, record.source_plugin_version) for record in evidence}
            ),
            distinct_pipeline_count=len(
                {
                    (record.pipeline_id, record.pipeline_version)
                    for record in evidence
                    if record.pipeline_id
                }
            ),
            cross_context_violation_count=cross_context,
            missing_parent_count=missing_parent,
            synthetic_record_count=synthetic,
            redaction_applied=True,
        )
