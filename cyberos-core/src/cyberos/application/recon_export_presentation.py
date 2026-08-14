"""Read-only presentation adaptation over Module 1.6 export contracts.

Style note: this application adapter produces renderer-neutral scalar views
only. It must never acquire persistence, filesystem, network, or subprocess
capabilities.
"""

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.recon.presentation import (
    PresentationMetricClassification,
    PresentationMetricView,
    PresentationSectionId,
    PresentationSectionView,
    ReconPresentationRequest,
    ReconPresentationView,
    context_matches,
    safe_payload_mapping,
)
from cyberos.domain.recon.report_export import (
    MetricClassification,
    ReconReportJsonExport,
    StructuredSummaryPresentation,
    SummaryMetric,
)

_SECTION_COPY: dict[PresentationSectionId, tuple[str, str]] = {
    PresentationSectionId.TARGET_RECON: (
        "Target Recon",
        "Bounded counts derived from the authorized target reconstruction summary.",
    ),
    PresentationSectionId.ASSET_DISTRIBUTION: (
        "Asset Distribution",
        "Bounded distribution counts for assets in the authorized scope context.",
    ),
    PresentationSectionId.PROVENANCE_AUDIT: (
        "Provenance Audit",
        "Bounded integrity and provenance counts with redaction applied.",
    ),
}


def _canonical(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
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


def _digest(value: object) -> str:
    encoded = json.dumps(
        _canonical(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or any(ord(char) < 32 for char in value):
        raise CyberOSError(
            ErrorCode.PRESENTATION_MODEL_INVALID, f"Presentation {field} is invalid."
        )
    return value.strip()


def _scalar(value: object, field: str) -> str | int | bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return _text(value, field)
    raise CyberOSError(ErrorCode.PRESENTATION_MODEL_INVALID, f"Presentation {field} is invalid.")


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise CyberOSError(
            ErrorCode.PRESENTATION_MODEL_INVALID, f"Presentation {field} is invalid."
        )
    return value


def _metric_classification(value: MetricClassification) -> PresentationMetricClassification:
    try:
        return PresentationMetricClassification(value.value)
    except ValueError as error:
        raise CyberOSError(
            ErrorCode.PRESENTATION_MODEL_INVALID, "Presentation metric classification is invalid."
        ) from error


def _structured_metric(metric: SummaryMetric) -> PresentationMetricView:
    if not isinstance(metric, SummaryMetric):
        raise CyberOSError(ErrorCode.PRESENTATION_MODEL_INVALID, "Summary metric is invalid.")
    return PresentationMetricView(
        metric.metric_id,
        metric.label,
        metric.value,
        _metric_classification(metric.classification),
    )


def _section_id(value: object) -> PresentationSectionId:
    if isinstance(value, PresentationSectionId):
        return value
    if isinstance(value, str):
        try:
            return PresentationSectionId(value)
        except ValueError as error:
            raise CyberOSError(
                ErrorCode.PRESENTATION_MODEL_INVALID, "Section identifier is invalid."
            ) from error
    raise CyberOSError(ErrorCode.PRESENTATION_MODEL_INVALID, "Section identifier is invalid.")


def _json_metric(
    metric_id: str, label: str, value: object, classification: str
) -> PresentationMetricView:
    try:
        parsed_classification = PresentationMetricClassification(classification)
    except ValueError as error:
        raise CyberOSError(
            ErrorCode.PRESENTATION_MODEL_INVALID, "Presentation metric classification is invalid."
        ) from error
    return PresentationMetricView(
        metric_id, label, _scalar(value, "metric value"), parsed_classification
    )


class ReconExportPresentationService:
    """Adapt approved Module 1.6 exports to safe in-memory presentation views."""

    def present(
        self,
        request: ReconPresentationRequest,
        export: ReconReportJsonExport | StructuredSummaryPresentation,
    ) -> ReconPresentationView:
        if not isinstance(request, ReconPresentationRequest):
            raise CyberOSError(
                ErrorCode.PRESENTATION_CONTEXT_INVALID, "Presentation request is invalid."
            )
        if not isinstance(export, (ReconReportJsonExport, StructuredSummaryPresentation)):
            raise CyberOSError(ErrorCode.PRESENTATION_MODEL_INVALID, "Export model is invalid.")
        if not context_matches(request.context, export.context):
            raise CyberOSError(
                ErrorCode.PRESENTATION_CONTEXT_INVALID, "Presentation context does not align."
            )
        if isinstance(export, ReconReportJsonExport):
            return self._from_json(request, export)
        return self._from_structured(request, export)

    def _from_structured(
        self, request: ReconPresentationRequest, export: StructuredSummaryPresentation
    ) -> ReconPresentationView:
        if not export.redaction_applied:
            raise CyberOSError(ErrorCode.PRESENTATION_INTEGRITY_INVALID, "Export is not redacted.")
        if len(export.sections) > request.max_sections:
            raise CyberOSError(
                ErrorCode.PRESENTATION_BUDGET_EXCEEDED, "Presentation section budget exceeded."
            )
        sections: list[PresentationSectionView] = []
        for source_section in export.sections:
            if len(source_section.metrics) > request.max_metrics_per_section:
                raise CyberOSError(
                    ErrorCode.PRESENTATION_BUDGET_EXCEEDED, "Section metric budget exceeded."
                )
            section_id = _section_id(source_section.section_id)
            label, description = _SECTION_COPY[section_id]
            sections.append(
                PresentationSectionView(
                    section_id,
                    label,
                    description,
                    tuple(_structured_metric(metric) for metric in source_section.metrics),
                )
            )
        export_digest = _digest(
            {
                "schema_version": export.schema_version,
                "title": export.title,
                "context": {
                    "scope_id": str(export.context.scope_id),
                    "target_id": str(export.context.target_id)
                    if export.context.target_id
                    else None,
                    "task_id": str(export.context.task_id) if export.context.task_id else None,
                },
                "generated_at": export.generated_at,
                "sections": [
                    {
                        "section_id": section.section_id.value,
                        "label": section.label,
                        "metrics": [
                            {
                                "metric_id": metric.metric_id,
                                "label": metric.label,
                                "value": metric.value,
                                "classification": metric.classification.value,
                            }
                            for metric in section.metrics
                        ],
                    }
                    for section in export.sections
                ],
                "source_fingerprint": export.source_fingerprint,
            }
        )
        return self._view(
            request,
            export.schema_version,
            export.title,
            export.generated_at,
            tuple(sections),
            export.source_fingerprint,
            export_digest,
            export.redaction_applied,
        )

    def _from_json(
        self, request: ReconPresentationRequest, export: ReconReportJsonExport
    ) -> ReconPresentationView:
        payload = safe_payload_mapping(export.payload)
        if (
            payload.get("source_fingerprint") != export.source_fingerprint
            or payload.get("completeness") != "complete"
        ):
            raise CyberOSError(
                ErrorCode.PRESENTATION_INTEGRITY_INVALID, "Export integrity fields do not align."
            )
        context_payload = _mapping(payload.get("context"), "context")
        if (
            context_payload.get("scope_id") != str(export.context.scope_id)
            or context_payload.get("target_id")
            != (str(export.context.target_id) if export.context.target_id else None)
            or context_payload.get("task_id")
            != (str(export.context.task_id) if export.context.task_id else None)
        ):
            raise CyberOSError(
                ErrorCode.PRESENTATION_CONTEXT_INVALID, "Export context payload does not align."
            )
        sections = (
            self._json_target_section(payload),
            self._json_distribution_section(payload),
            self._json_provenance_section(payload),
        )
        if len(sections) > request.max_sections or any(
            len(section.metrics) > request.max_metrics_per_section for section in sections
        ):
            raise CyberOSError(
                ErrorCode.PRESENTATION_BUDGET_EXCEEDED, "Presentation budget exceeded."
            )
        provenance = _mapping(payload.get("provenance_audit"), "provenance_audit")
        redaction = provenance.get("redaction_applied")
        if redaction is not True:
            raise CyberOSError(
                ErrorCode.PRESENTATION_INTEGRITY_INVALID, "Export redaction marker is invalid."
            )
        return self._view(
            request,
            export.schema_version,
            "CyberOS Recon Summary",
            export.generated_at,
            sections,
            export.source_fingerprint,
            export.export_digest,
            True,
        )

    def _json_target_section(self, payload: Mapping[str, object]) -> PresentationSectionView:
        source = _mapping(payload.get("target_summary"), "target_summary")
        return PresentationSectionView(
            PresentationSectionId.TARGET_RECON,
            *_SECTION_COPY[PresentationSectionId.TARGET_RECON],
            (
                _json_metric("asset_count", "Assets", source.get("asset_count"), "count"),
                _json_metric(
                    "observation_count", "Observations", source.get("observation_count"), "count"
                ),
                _json_metric(
                    "active_evidence_count",
                    "Active evidence",
                    source.get("active_evidence_count"),
                    "count",
                ),
            ),
        )

    def _json_distribution_section(self, payload: Mapping[str, object]) -> PresentationSectionView:
        source = _mapping(payload.get("asset_distribution"), "asset_distribution")
        return PresentationSectionView(
            PresentationSectionId.ASSET_DISTRIBUTION,
            *_SECTION_COPY[PresentationSectionId.ASSET_DISTRIBUTION],
            (
                _json_metric("total_assets", "Total assets", source.get("total_assets"), "count"),
                _json_metric(
                    "linked_assets",
                    "Evidence-linked assets",
                    source.get("evidence_linked_asset_count"),
                    "count",
                ),
                _json_metric(
                    "unlinked_assets",
                    "Unlinked assets",
                    source.get("unlinked_asset_count"),
                    "count",
                ),
            ),
        )

    def _json_provenance_section(self, payload: Mapping[str, object]) -> PresentationSectionView:
        source = _mapping(payload.get("provenance_audit"), "provenance_audit")
        return PresentationSectionView(
            PresentationSectionId.PROVENANCE_AUDIT,
            *_SECTION_COPY[PresentationSectionId.PROVENANCE_AUDIT],
            (
                _json_metric(
                    "distinct_tasks", "Distinct tasks", source.get("distinct_task_count"), "count"
                ),
                _json_metric(
                    "missing_parents",
                    "Missing parents",
                    source.get("missing_parent_count"),
                    "count",
                ),
                _json_metric(
                    "redaction_applied",
                    "Redaction applied",
                    source.get("redaction_applied"),
                    "boolean",
                ),
            ),
        )

    @staticmethod
    def _view(
        request: ReconPresentationRequest,
        schema_version: str,
        title: str,
        generated_at: datetime,
        sections: tuple[PresentationSectionView, ...],
        source_fingerprint: str,
        export_digest: str,
        redaction_applied: bool,
    ) -> ReconPresentationView:
        return ReconPresentationView(
            schema_version,
            request.view_kind,
            request.context,
            generated_at,
            title,
            sections,
            source_fingerprint,
            export_digest,
            "complete",
            redaction_applied,
        )
