from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Protocol
from uuid import UUID

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.recon.evidence import EvidenceKind
from cyberos.domain.recon.model import AssetAggregate, AssetKind, AssetObservation, AssetStatus
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.primitives import TargetId
from cyberos.domain.task.primitives import TaskId


def _uuid4(value: UUID, field: str) -> None:
    if not isinstance(value, UUID) or value.version != 4:
        raise CyberOSError(ErrorCode.REPORT_QUERY_INVALID, f"{field} must be UUID4.")


def _positive(value: int, field: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise CyberOSError(ErrorCode.REPORT_QUERY_INVALID, f"{field} must be positive.")


@dataclass(frozen=True, slots=True)
class ReconReportContext:
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
class ReconReportBudget:
    max_evidence_records: int = 2_000
    max_assets: int = 2_000
    max_observations: int = 5_000
    max_metadata_bytes: int = 65_536
    max_pages: int = 100

    def __post_init__(self) -> None:
        for field in (
            "max_evidence_records",
            "max_assets",
            "max_observations",
            "max_metadata_bytes",
            "max_pages",
        ):
            _positive(getattr(self, field), field)


@dataclass(frozen=True, slots=True)
class ReportSourceWindow:
    pages_read: int
    evidence_records_read: int
    assets_read: int
    observations_read: int
    metadata_bytes_read: int

    def __post_init__(self) -> None:
        for field in (
            "pages_read",
            "evidence_records_read",
            "assets_read",
            "observations_read",
            "metadata_bytes_read",
        ):
            if not isinstance(getattr(self, field), int) or getattr(self, field) < 0:
                raise CyberOSError(
                    ErrorCode.REPORT_PROJECTION_INVALID, "Report source window is invalid."
                )


@dataclass(frozen=True, slots=True)
class PluginSourceSummary:
    plugin_id: str
    plugin_version: str
    evidence_count: int


@dataclass(frozen=True, slots=True)
class PipelineSourceSummary:
    pipeline_id: str
    pipeline_version: str
    evidence_count: int


@dataclass(frozen=True, slots=True)
class AssetKindDistribution:
    kind: AssetKind
    count: int


@dataclass(frozen=True, slots=True)
class AssetStatusDistribution:
    status: AssetStatus
    count: int


@dataclass(frozen=True, slots=True)
class ReconAssetReadBundle:
    asset: AssetAggregate
    observations: tuple[AssetObservation, ...]


class ReconReportSourcePort(Protocol):
    def read_assets(
        self, scope_id: ScopeId, target_id: TargetId | None = None
    ) -> tuple[ReconAssetReadBundle, ...]: ...


@dataclass(frozen=True, slots=True)
class TargetReconSummary:
    scope_id: ScopeId
    target_id: TargetId | None
    generated_at: datetime
    source_window: ReportSourceWindow
    asset_count: int
    observation_count: int
    active_evidence_count: int
    archived_evidence_count: int
    evidence_by_kind: Mapping[EvidenceKind, int]
    assets_by_kind: Mapping[AssetKind, int]
    source_plugins: tuple[PluginSourceSummary, ...]
    pipelines: tuple[PipelineSourceSummary, ...]
    provenance: ProvenanceAuditSummary
    synthetic_fixture_only: bool

    def __post_init__(self) -> None:
        _uuid4(self.scope_id, "scope_id")
        if self.target_id is not None:
            _uuid4(self.target_id, "target_id")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise CyberOSError(
                ErrorCode.REPORT_PROJECTION_INVALID, "generated_at must be UTC-aware."
            )
        if any(
            not isinstance(value, int) or value < 0
            for value in (
                self.asset_count,
                self.observation_count,
                self.active_evidence_count,
                self.archived_evidence_count,
            )
        ):
            raise CyberOSError(ErrorCode.REPORT_PROJECTION_INVALID, "Report counts are invalid.")
        object.__setattr__(self, "evidence_by_kind", MappingProxyType(dict(self.evidence_by_kind)))
        object.__setattr__(self, "assets_by_kind", MappingProxyType(dict(self.assets_by_kind)))


@dataclass(frozen=True, slots=True)
class AssetDistributionBreakdown:
    scope_id: ScopeId
    target_id: TargetId | None
    generated_at: datetime
    total_assets: int
    by_kind: tuple[AssetKindDistribution, ...]
    by_status: tuple[AssetStatusDistribution, ...]
    observed_asset_count: int
    evidence_linked_asset_count: int
    unlinked_asset_count: int
    source_window: ReportSourceWindow


@dataclass(frozen=True, slots=True)
class ProvenanceAuditSummary:
    total_evidence: int
    active_evidence: int
    archived_evidence: int
    distinct_task_count: int
    distinct_asset_count: int
    distinct_observation_count: int
    distinct_plugin_count: int
    distinct_pipeline_count: int
    cross_context_violation_count: int
    missing_parent_count: int
    synthetic_record_count: int
    redaction_applied: bool
