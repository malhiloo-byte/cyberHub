"""Immutable, renderer-neutral presentation contracts for recon exports.

Style note: this module intentionally models safe scalar views only. It must
remain in-memory, scope-rooted, redaction-safe, and independent of renderers,
filesystem APIs, SQL, network clients, and subprocess execution.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.recon.report_export import ExportContext


class PresentationViewKind(StrEnum):
    SUMMARY = "summary"
    AUDIT_SUMMARY = "audit_summary"


class PresentationSectionId(StrEnum):
    TARGET_RECON = "target_recon"
    ASSET_DISTRIBUTION = "asset_distribution"
    PROVENANCE_AUDIT = "provenance_audit"


class PresentationMetricClassification(StrEnum):
    COUNT = "count"
    IDENTITY = "identity"
    STATUS = "status"
    DIGEST = "digest"
    BOOLEAN = "boolean"


_MAX_SECTIONS = 3
_MAX_METRICS = 32
_MAX_LABEL_BYTES = 16_384
_MAX_SCALAR_BYTES = 65_536


def _uuid4(value: UUID, field: str) -> None:
    if not isinstance(value, UUID) or value.version != 4:
        raise CyberOSError(ErrorCode.PRESENTATION_CONTEXT_INVALID, f"{field} is invalid.")


def _digest(value: str, field: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise CyberOSError(ErrorCode.PRESENTATION_INTEGRITY_INVALID, f"{field} is invalid.")


def _text(value: str, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > maximum:
        raise CyberOSError(
            ErrorCode.PRESENTATION_MODEL_INVALID, f"Presentation {field} is invalid."
        )
    if any(ord(character) < 32 for character in value):
        raise CyberOSError(
            ErrorCode.PRESENTATION_MODEL_INVALID, f"Presentation {field} is invalid."
        )
    return value.strip()


def _scalar_bytes(value: str | int | bool) -> int:
    if isinstance(value, bool):
        return len(str(value).lower().encode("utf-8"))
    if isinstance(value, int):
        return len(str(value).encode("utf-8"))
    return len(value.encode("utf-8"))


@dataclass(frozen=True, slots=True)
class PresentationMetricView:
    metric_id: str
    label: str
    value: str | int | bool
    classification: PresentationMetricClassification
    sensitive: bool = False

    def __post_init__(self) -> None:
        _text(self.metric_id, "metric_id", 256)
        _text(self.label, "metric label", _MAX_LABEL_BYTES)
        if not isinstance(self.value, (str, int, bool)) or isinstance(self.value, float):
            raise CyberOSError(ErrorCode.PRESENTATION_MODEL_INVALID, "Metric value is invalid.")
        if isinstance(self.value, str) and any(ord(character) < 32 for character in self.value):
            raise CyberOSError(ErrorCode.PRESENTATION_MODEL_INVALID, "Metric value is invalid.")
        if not isinstance(self.classification, PresentationMetricClassification):
            raise CyberOSError(
                ErrorCode.PRESENTATION_MODEL_INVALID, "Metric classification is invalid."
            )
        if self.sensitive:
            raise CyberOSError(
                ErrorCode.PRESENTATION_MODEL_INVALID,
                "Sensitive presentation metrics are not supported.",
            )


@dataclass(frozen=True, slots=True)
class PresentationSectionView:
    section_id: PresentationSectionId
    label: str
    description: str
    metrics: tuple[PresentationMetricView, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.section_id, PresentationSectionId):
            raise CyberOSError(
                ErrorCode.PRESENTATION_MODEL_INVALID, "Section identifier is invalid."
            )
        _text(self.label, "section label", _MAX_LABEL_BYTES)
        _text(self.description, "section description", _MAX_LABEL_BYTES)
        if not isinstance(self.metrics, tuple) or len(self.metrics) > _MAX_METRICS:
            raise CyberOSError(
                ErrorCode.PRESENTATION_BUDGET_EXCEEDED, "Section metric budget exceeded."
            )
        if any(not isinstance(metric, PresentationMetricView) for metric in self.metrics):
            raise CyberOSError(ErrorCode.PRESENTATION_MODEL_INVALID, "Section metrics are invalid.")


@dataclass(frozen=True, slots=True)
class ReconPresentationView:
    schema_version: str
    view_kind: PresentationViewKind
    context: ExportContext
    generated_at: datetime
    title: str
    sections: tuple[PresentationSectionView, ...]
    source_fingerprint: str
    export_digest: str
    completeness: str
    redaction_applied: bool

    def __post_init__(self) -> None:
        if self.schema_version != "1.0" or not isinstance(self.view_kind, PresentationViewKind):
            raise CyberOSError(
                ErrorCode.PRESENTATION_MODEL_INVALID, "Presentation schema is invalid."
            )
        if not isinstance(self.context, ExportContext):
            raise CyberOSError(
                ErrorCode.PRESENTATION_CONTEXT_INVALID, "Presentation context is invalid."
            )
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise CyberOSError(
                ErrorCode.PRESENTATION_INTEGRITY_INVALID, "Presentation time is invalid."
            )
        _text(self.title, "title", _MAX_LABEL_BYTES)
        if not isinstance(self.sections, tuple) or len(self.sections) > _MAX_SECTIONS:
            raise CyberOSError(
                ErrorCode.PRESENTATION_BUDGET_EXCEEDED, "Presentation section budget exceeded."
            )
        if any(not isinstance(section, PresentationSectionView) for section in self.sections):
            raise CyberOSError(
                ErrorCode.PRESENTATION_MODEL_INVALID, "Presentation sections are invalid."
            )
        if self.completeness != "complete":
            raise CyberOSError(
                ErrorCode.PRESENTATION_INTEGRITY_INVALID,
                "Incomplete presentation is not supported.",
            )
        if not isinstance(self.redaction_applied, bool) or not self.redaction_applied:
            raise CyberOSError(
                ErrorCode.PRESENTATION_INTEGRITY_INVALID, "Presentation redaction is invalid."
            )
        _digest(self.source_fingerprint, "source_fingerprint")
        _digest(self.export_digest, "export_digest")
        label_bytes = sum(
            len(value.encode("utf-8"))
            for section in self.sections
            for value in (section.label, section.description)
            for _ in (0,)
        )
        scalar_bytes = sum(
            _scalar_bytes(metric.value) for section in self.sections for metric in section.metrics
        )
        if label_bytes > _MAX_LABEL_BYTES or scalar_bytes > _MAX_SCALAR_BYTES:
            raise CyberOSError(
                ErrorCode.PRESENTATION_BUDGET_EXCEEDED, "Presentation byte budget exceeded."
            )


@dataclass(frozen=True, slots=True)
class ReconPresentationRequest:
    context: ExportContext
    view_kind: PresentationViewKind
    max_sections: int = _MAX_SECTIONS
    max_metrics_per_section: int = _MAX_METRICS

    def __post_init__(self) -> None:
        if not isinstance(self.context, ExportContext) or not isinstance(
            self.view_kind, PresentationViewKind
        ):
            raise CyberOSError(
                ErrorCode.PRESENTATION_CONTEXT_INVALID, "Presentation request is invalid."
            )
        if (
            not isinstance(self.max_sections, int)
            or isinstance(self.max_sections, bool)
            or not 1 <= self.max_sections <= _MAX_SECTIONS
            or not isinstance(self.max_metrics_per_section, int)
            or isinstance(self.max_metrics_per_section, bool)
            or not 1 <= self.max_metrics_per_section <= _MAX_METRICS
        ):
            raise CyberOSError(
                ErrorCode.PRESENTATION_BUDGET_EXCEEDED, "Presentation budget is invalid."
            )


def context_matches(expected: ExportContext, actual: ExportContext) -> bool:
    """Return whether two presentation contexts are exactly aligned."""

    return (
        expected.scope_id == actual.scope_id
        and expected.target_id == actual.target_id
        and expected.task_id == actual.task_id
    )


def safe_payload_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise CyberOSError(ErrorCode.PRESENTATION_MODEL_INVALID, "Export payload is invalid.")
    return value
