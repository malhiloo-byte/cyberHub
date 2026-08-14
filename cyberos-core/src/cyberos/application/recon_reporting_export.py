from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from cyberos.application.recon_reporting import ReconReportingService
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.time import utc_now
from cyberos.domain.recon.report_export import (
    ExportContext,
    ExportKind,
    MetricClassification,
    ReconReportExportRequest,
    ReconReportJsonExport,
    ReconReportSnapshot,
    StructuredSummaryPresentation,
    SummaryMetric,
    SummarySection,
    SummarySectionId,
)
from cyberos.domain.recon.reporting import (
    AssetDistributionBreakdown,
    PipelineSourceSummary,
    PluginSourceSummary,
    ProvenanceAuditSummary,
    ReconReportBudget,
    ReconReportContext,
    ReportSourceWindow,
    TargetReconSummary,
)
from cyberos.persistence.connection import SQLiteConnectionFactory


def _canonical(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, tuple) or isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


def _digest_payload(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        _canonical(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_window(window: ReportSourceWindow) -> dict[str, int]:
    return {
        "pages_read": window.pages_read,
        "evidence_records_read": window.evidence_records_read,
        "assets_read": window.assets_read,
        "observations_read": window.observations_read,
        "metadata_bytes_read": window.metadata_bytes_read,
    }


def _plugin_sources(values: tuple[PluginSourceSummary, ...]) -> list[dict[str, object]]:
    return [
        {
            "plugin_id": value.plugin_id,
            "plugin_version": value.plugin_version,
            "evidence_count": value.evidence_count,
        }
        for value in values
    ]


def _pipeline_sources(values: tuple[PipelineSourceSummary, ...]) -> list[dict[str, object]]:
    return [
        {
            "pipeline_id": value.pipeline_id,
            "pipeline_version": value.pipeline_version,
            "evidence_count": value.evidence_count,
        }
        for value in values
    ]


def _provenance(value: ProvenanceAuditSummary) -> dict[str, object]:
    return {
        "total_evidence": value.total_evidence,
        "active_evidence": value.active_evidence,
        "archived_evidence": value.archived_evidence,
        "distinct_task_count": value.distinct_task_count,
        "distinct_asset_count": value.distinct_asset_count,
        "distinct_observation_count": value.distinct_observation_count,
        "distinct_plugin_count": value.distinct_plugin_count,
        "distinct_pipeline_count": value.distinct_pipeline_count,
        "cross_context_violation_count": value.cross_context_violation_count,
        "missing_parent_count": value.missing_parent_count,
        "synthetic_record_count": value.synthetic_record_count,
        "redaction_applied": value.redaction_applied,
    }


def _target_summary(value: TargetReconSummary) -> dict[str, object]:
    return {
        "scope_id": str(value.scope_id),
        "target_id": str(value.target_id) if value.target_id is not None else None,
        "generated_at": value.generated_at.isoformat(),
        "source_window": _source_window(value.source_window),
        "asset_count": value.asset_count,
        "observation_count": value.observation_count,
        "active_evidence_count": value.active_evidence_count,
        "archived_evidence_count": value.archived_evidence_count,
        "evidence_by_kind": {kind.value: count for kind, count in value.evidence_by_kind.items()},
        "assets_by_kind": {kind.value: count for kind, count in value.assets_by_kind.items()},
        "source_plugins": _plugin_sources(value.source_plugins),
        "pipelines": _pipeline_sources(value.pipelines),
        "provenance": _provenance(value.provenance),
        "synthetic_fixture_only": value.synthetic_fixture_only,
    }


def _asset_distribution(value: AssetDistributionBreakdown) -> dict[str, object]:
    return {
        "scope_id": str(value.scope_id),
        "target_id": str(value.target_id) if value.target_id is not None else None,
        "generated_at": value.generated_at.isoformat(),
        "total_assets": value.total_assets,
        "by_kind": [{"kind": item.kind.value, "count": item.count} for item in value.by_kind],
        "by_status": [
            {"status": item.status.value, "count": item.count} for item in value.by_status
        ],
        "observed_asset_count": value.observed_asset_count,
        "evidence_linked_asset_count": value.evidence_linked_asset_count,
        "unlinked_asset_count": value.unlinked_asset_count,
        "source_window": _source_window(value.source_window),
    }


class ReconReportingExportService:
    """Serialize safe Module 1.5 projections entirely in memory."""

    def __init__(
        self,
        factory: SQLiteConnectionFactory,
        *,
        reporting: ReconReportingService | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.reporting = reporting or ReconReportingService(factory, clock=clock)
        self.clock = clock

    def snapshot(
        self,
        context: ExportContext,
        *,
        budget: ReconReportBudget | None = None,
    ) -> ReconReportSnapshot:
        report_context = ReconReportContext(context.scope_id, context.target_id, context.task_id)
        generated_at = self.clock()
        reporting = ReconReportingService(
            self.reporting.factory,
            source=self.reporting.source,
            clock=lambda: generated_at,
        )
        target = reporting.target_recon_summary(report_context, budget=budget)
        distribution = reporting.asset_distribution_breakdown(report_context, budget=budget)
        provenance = reporting.provenance_audit_summary(report_context, budget=budget)
        if target.generated_at != distribution.generated_at or target.generated_at != generated_at:
            raise CyberOSError(
                ErrorCode.REPORT_EXPORT_INTEGRITY_INVALID,
                "Reporting projections were generated from inconsistent windows.",
            )
        if (
            provenance.total_evidence
            != target.active_evidence_count + target.archived_evidence_count
            or distribution.total_assets != target.asset_count
        ):
            raise CyberOSError(
                ErrorCode.REPORT_EXPORT_INTEGRITY_INVALID,
                "Reporting projection counts are inconsistent.",
            )
        fingerprint_payload = {
            "context": self._context_payload(context),
            "generated_at": target.generated_at.isoformat(),
            "target_summary": _target_summary(target),
            "asset_distribution": _asset_distribution(distribution),
            "provenance_audit": _provenance(provenance),
        }
        fingerprint = _digest_payload(fingerprint_payload)
        return ReconReportSnapshot(
            context,
            target.generated_at,
            target,
            distribution,
            provenance,
            fingerprint,
        )

    def export_json(
        self,
        request: ReconReportExportRequest,
        snapshot: ReconReportSnapshot,
    ) -> ReconReportJsonExport:
        self._validate_request_snapshot(request, snapshot)
        if request.export_kind is not ExportKind.JSON:
            raise CyberOSError(
                ErrorCode.REPORT_EXPORT_SERIALIZATION_FAILED, "JSON export kind is required."
            )
        payload: dict[str, object] = {
            "schema_version": "1.0",
            "export_kind": "recon-report",
            "context": self._context_payload(snapshot.context),
            "generated_at": snapshot.generated_at.isoformat(),
            "source_fingerprint": snapshot.source_fingerprint,
            "completeness": "complete",
            "target_summary": _target_summary(snapshot.target_summary),
            "asset_distribution": _asset_distribution(snapshot.asset_distribution),
            "provenance_audit": _provenance(snapshot.provenance_audit),
        }
        encoded_without_digest = self._encode(payload)
        if len(encoded_without_digest) > request.max_export_bytes:
            raise CyberOSError(
                ErrorCode.REPORT_EXPORT_SIZE_EXCEEDED,
                "Canonical report export exceeds the configured byte budget.",
            )
        export_digest = hashlib.sha256(encoded_without_digest).hexdigest()
        return ReconReportJsonExport(
            "1.0",
            "recon-report",
            snapshot.context,
            snapshot.generated_at,
            snapshot.source_fingerprint,
            "complete",
            payload,
            export_digest,
        )

    def serialize_json(self, export: ReconReportJsonExport, *, max_bytes: int = 262_144) -> str:
        payload = dict(export.payload)
        payload["export_digest"] = export.export_digest
        encoded = self._encode(payload)
        if len(encoded) > max_bytes:
            raise CyberOSError(
                ErrorCode.REPORT_EXPORT_SIZE_EXCEEDED, "Serialized export exceeds the byte budget."
            )
        return encoded.decode("utf-8")

    def structured_summary(
        self,
        request: ReconReportExportRequest,
        snapshot: ReconReportSnapshot,
    ) -> StructuredSummaryPresentation:
        self._validate_request_snapshot(request, snapshot)
        if request.export_kind is not ExportKind.STRUCTURED_SUMMARY:
            raise CyberOSError(
                ErrorCode.REPORT_EXPORT_SERIALIZATION_FAILED,
                "Structured summary export kind is required.",
            )
        target = snapshot.target_summary
        distribution = snapshot.asset_distribution
        provenance = snapshot.provenance_audit
        sections = (
            SummarySection(
                SummarySectionId.TARGET_RECON,
                "Target Recon",
                (
                    SummaryMetric(
                        "asset_count", "Assets", target.asset_count, MetricClassification.COUNT
                    ),
                    SummaryMetric(
                        "observation_count",
                        "Observations",
                        target.observation_count,
                        MetricClassification.COUNT,
                    ),
                    SummaryMetric(
                        "active_evidence_count",
                        "Active evidence",
                        target.active_evidence_count,
                        MetricClassification.COUNT,
                    ),
                ),
            ),
            SummarySection(
                SummarySectionId.ASSET_DISTRIBUTION,
                "Asset Distribution",
                (
                    SummaryMetric(
                        "total_assets",
                        "Total assets",
                        distribution.total_assets,
                        MetricClassification.COUNT,
                    ),
                    SummaryMetric(
                        "linked_assets",
                        "Evidence-linked assets",
                        distribution.evidence_linked_asset_count,
                        MetricClassification.COUNT,
                    ),
                    SummaryMetric(
                        "unlinked_assets",
                        "Unlinked assets",
                        distribution.unlinked_asset_count,
                        MetricClassification.COUNT,
                    ),
                ),
            ),
            SummarySection(
                SummarySectionId.PROVENANCE_AUDIT,
                "Provenance Audit",
                (
                    SummaryMetric(
                        "distinct_tasks",
                        "Distinct tasks",
                        provenance.distinct_task_count,
                        MetricClassification.COUNT,
                    ),
                    SummaryMetric(
                        "missing_parents",
                        "Missing parents",
                        provenance.missing_parent_count,
                        MetricClassification.COUNT,
                    ),
                    SummaryMetric(
                        "redaction_applied",
                        "Redaction applied",
                        provenance.redaction_applied,
                        MetricClassification.BOOLEAN,
                    ),
                ),
            ),
        )
        return StructuredSummaryPresentation(
            "1.0",
            "CyberOS Recon Summary",
            snapshot.context,
            snapshot.generated_at,
            sections,
            snapshot.source_fingerprint,
            True,
        )

    @staticmethod
    def _context_payload(context: ExportContext) -> dict[str, str | None]:
        return {
            "scope_id": str(context.scope_id),
            "target_id": str(context.target_id) if context.target_id is not None else None,
            "task_id": str(context.task_id) if context.task_id is not None else None,
        }

    @staticmethod
    def _encode(payload: Mapping[str, object]) -> bytes:
        try:
            return json.dumps(
                _canonical(payload),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError, UnicodeError) as exc:
            raise CyberOSError(
                ErrorCode.REPORT_EXPORT_SERIALIZATION_FAILED,
                "Report projection could not be serialized safely.",
            ) from exc

    @staticmethod
    def _validate_request_snapshot(
        request: ReconReportExportRequest, snapshot: ReconReportSnapshot
    ) -> None:
        if request.context != snapshot.context:
            raise CyberOSError(
                ErrorCode.REPORT_EXPORT_CONTEXT_INVALID,
                "Export request context does not match the report snapshot.",
            )
