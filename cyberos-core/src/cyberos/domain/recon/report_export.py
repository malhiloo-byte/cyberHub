from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.recon.reporting import (
    AssetDistributionBreakdown,
    ProvenanceAuditSummary,
    TargetReconSummary,
)
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.primitives import TargetId
from cyberos.domain.task.primitives import TaskId


class ExportKind(StrEnum):
    JSON = "json"
    STRUCTURED_SUMMARY = "structured_summary"


class SummarySectionId(StrEnum):
    TARGET_RECON = "target_recon"
    ASSET_DISTRIBUTION = "asset_distribution"
    PROVENANCE_AUDIT = "provenance_audit"


class MetricClassification(StrEnum):
    COUNT = "count"
    IDENTITY = "identity"
    STATUS = "status"
    DIGEST = "digest"
    BOOLEAN = "boolean"


def _uuid4(value: UUID, field: str) -> None:
    if not isinstance(value, UUID) or value.version != 4:
        raise CyberOSError(ErrorCode.REPORT_EXPORT_CONTEXT_INVALID, f"{field} must be UUID4.")


def _digest(value: str, field: str, code: ErrorCode) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise CyberOSError(code, f"{field} must be a SHA-256 hex digest.")


@dataclass(frozen=True, slots=True)
class ExportContext:
    scope_id: ScopeId
    target_id: TargetId | None = None
    task_id: TaskId | None = None

    def __post_init__(self) -> None:
        _uuid4(self.scope_id, "scope_id")
        if self.target_id is not None:
            _uuid4(self.target_id, "target_id")
        if self.task_id is not None:
            _uuid4(self.task_id, "task_id")


@dataclass(frozen=True, slots=True)
class ReconReportExportRequest:
    context: ExportContext
    export_kind: ExportKind
    max_export_bytes: int = 262_144

    def __post_init__(self) -> None:
        if not isinstance(self.context, ExportContext) or not isinstance(
            self.export_kind, ExportKind
        ):
            raise CyberOSError(
                ErrorCode.REPORT_EXPORT_CONTEXT_INVALID, "Export request is invalid."
            )
        if (
            not isinstance(self.max_export_bytes, int)
            or isinstance(self.max_export_bytes, bool)
            or self.max_export_bytes < 1
            or self.max_export_bytes > 262_144
        ):
            raise CyberOSError(
                ErrorCode.REPORT_EXPORT_SIZE_EXCEEDED,
                "Export byte budget must be between 1 and 262144 bytes.",
            )


@dataclass(frozen=True, slots=True)
class ReconReportSnapshot:
    context: ExportContext
    generated_at: datetime
    target_summary: TargetReconSummary
    asset_distribution: AssetDistributionBreakdown
    provenance_audit: ProvenanceAuditSummary
    source_fingerprint: str

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise CyberOSError(
                ErrorCode.REPORT_EXPORT_INTEGRITY_INVALID, "Snapshot time must be UTC-aware."
            )
        if (
            self.target_summary.scope_id != self.context.scope_id
            or self.asset_distribution.scope_id != self.context.scope_id
        ):
            raise CyberOSError(
                ErrorCode.REPORT_EXPORT_CONTEXT_INVALID, "Snapshot Scope context is invalid."
            )
        for projection in (self.target_summary, self.asset_distribution):
            if (
                self.context.target_id is not None
                and projection.target_id != self.context.target_id
            ):
                raise CyberOSError(
                    ErrorCode.REPORT_EXPORT_CONTEXT_INVALID, "Snapshot Target context is invalid."
                )
        _digest(
            self.source_fingerprint, "source_fingerprint", ErrorCode.REPORT_EXPORT_INTEGRITY_INVALID
        )


@dataclass(frozen=True, slots=True)
class ReconReportJsonExport:
    schema_version: str
    export_kind: str
    context: ExportContext
    generated_at: datetime
    source_fingerprint: str
    completeness: str
    payload: Mapping[str, object]
    export_digest: str

    def __post_init__(self) -> None:
        if self.schema_version != "1.0" or self.export_kind != "recon-report":
            raise CyberOSError(
                ErrorCode.REPORT_EXPORT_SERIALIZATION_FAILED, "Export schema is invalid."
            )
        if self.completeness != "complete":
            raise CyberOSError(
                ErrorCode.REPORT_EXPORT_INTEGRITY_INVALID, "Only complete exports are supported."
            )
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise CyberOSError(
                ErrorCode.REPORT_EXPORT_SERIALIZATION_FAILED, "Export time must be UTC-aware."
            )
        _digest(
            self.source_fingerprint, "source_fingerprint", ErrorCode.REPORT_EXPORT_INTEGRITY_INVALID
        )
        _digest(self.export_digest, "export_digest", ErrorCode.REPORT_EXPORT_INTEGRITY_INVALID)
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


@dataclass(frozen=True, slots=True)
class SummaryMetric:
    metric_id: str
    label: str
    value: str | int | bool
    classification: MetricClassification


@dataclass(frozen=True, slots=True)
class SummarySection:
    section_id: SummarySectionId
    label: str
    metrics: tuple[SummaryMetric, ...]


@dataclass(frozen=True, slots=True)
class StructuredSummaryPresentation:
    schema_version: str
    title: str
    context: ExportContext
    generated_at: datetime
    sections: tuple[SummarySection, ...]
    source_fingerprint: str
    redaction_applied: bool

    def __post_init__(self) -> None:
        if self.schema_version != "1.0" or not self.title.strip():
            raise CyberOSError(
                ErrorCode.REPORT_EXPORT_SERIALIZATION_FAILED, "Presentation schema is invalid."
            )
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise CyberOSError(
                ErrorCode.REPORT_EXPORT_SERIALIZATION_FAILED, "Presentation time must be UTC-aware."
            )
        if not isinstance(self.redaction_applied, bool):
            raise CyberOSError(
                ErrorCode.REPORT_EXPORT_REDACTION_FAILED, "Redaction status is invalid."
            )
        _digest(
            self.source_fingerprint, "source_fingerprint", ErrorCode.REPORT_EXPORT_INTEGRITY_INVALID
        )
