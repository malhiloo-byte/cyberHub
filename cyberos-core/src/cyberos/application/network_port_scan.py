"""Application bridge and neutral harness for Module 2.1.

Style note: this module consumes only offline parser output or explicitly
host-created contracts. It reuses ReconIngestionService and ReconEvidenceService,
keeps raw XML/JSON ephemeral, performs no subprocess/network operation, and
never creates authorization or a background scan.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from cyberos.application.recon_evidence import ReconEvidenceService
from cyberos.application.recon_ingestion import ReconIngestionService
from cyberos.application.scope_validation import ExecutionAuthorization
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.time import utc_now
from cyberos.domain.recon.evidence import EvidenceKind
from cyberos.domain.recon.network_scan import (
    NetworkPortScanAdapterManifest,
    NetworkScanInvocation,
)
from cyberos.domain.recon.network_scan_parser import (
    NetworkScanParser,
    NetworkScanParseResult,
    ParserLimits,
)
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.primitives import TargetId
from cyberos.domain.task.model import Task
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.recon_repository import SQLiteReconRepository
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork
from cyberos.recon.contracts import ExecutionLimits, ReconResult

__all__ = [
    "NetworkPortScanOfflineHarness",
    "NetworkPortScanReceipt",
    "NetworkPortScanProvenanceBridge",
]


_PLUGIN_VERSION: Final[str] = "2.1.0"
_DEFAULT_PARSER_LIMITS = ParserLimits()


@dataclass(frozen=True, slots=True)
class NetworkPortScanReceipt:
    adapter_id: str
    task_id: object
    scope_id: ScopeId
    target_id: TargetId
    output_format: str
    source_digest: str
    parsed_services: int
    parsed_observations: int
    inserted_assets: int = 0
    inserted_observations: int = 0
    created_evidence: int = 0
    synthetic: bool = True
    offline_fixture: bool = True

    def __post_init__(self) -> None:
        if not self.synthetic or not self.offline_fixture:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_OUTPUT_CONTRACT_INVALID,
                "Module 2.1 receipts require synthetic/offline markers.",
            )
        if not isinstance(self.parsed_services, int) or self.parsed_services < 0:
            raise CyberOSError(ErrorCode.PORT_SCAN_PARSE_FAILED, "Parsed service count is invalid.")
        if not isinstance(self.parsed_observations, int) or self.parsed_observations < 0:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_PARSE_FAILED, "Parsed observation count is invalid."
            )


class NetworkPortScanOfflineHarness:
    """Execute parser-only scenarios against deterministic XML/JSON bytes."""

    def __init__(self, parser: NetworkScanParser | None = None) -> None:
        self.parser = parser or NetworkScanParser()

    def parse_fixture(
        self,
        payload: bytes,
        *,
        output_format: str,
        scope_id: ScopeId,
        target_id: TargetId,
        target_kind: object,
        canonical_target: str,
        limits: ParserLimits = _DEFAULT_PARSER_LIMITS,
        truncated: bool = False,
    ) -> NetworkScanParseResult:
        from cyberos.domain.recon.network_scan import MachineOutputFormat
        from cyberos.domain.target.primitives import TargetKind

        if not isinstance(target_kind, TargetKind):
            raise CyberOSError(
                ErrorCode.PORT_SCAN_TARGET_INVALID, "Fixture target kind is invalid."
            )
        try:
            format_value = MachineOutputFormat(output_format)
        except ValueError as exc:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_OUTPUT_CONTRACT_INVALID,
                "Fixture output format is unsupported.",
            ) from exc
        return self.parser.parse(
            payload,
            output_format=format_value,
            scope_id=scope_id,
            target_id=target_id,
            target_kind=target_kind,
            canonical_target=canonical_target,
            limits=limits,
            truncated=truncated,
        )


class NetworkPortScanProvenanceBridge:
    """Convert accepted offline parser output into existing Recon/Evidence flows."""

    def __init__(self, factory: SQLiteConnectionFactory) -> None:
        self.factory = factory
        self.ingestion = ReconIngestionService(factory)
        self.evidence = ReconEvidenceService(factory)

    def ingest_and_create_evidence(
        self,
        *,
        task: Task,
        authorization: ExecutionAuthorization,
        manifest: NetworkPortScanAdapterManifest,
        invocation: NetworkScanInvocation,
        parsed: NetworkScanParseResult,
        observed_at: datetime | None = None,
    ) -> NetworkPortScanReceipt:
        self._validate_alignment(task, authorization, manifest, invocation, parsed)
        timestamp = observed_at or utc_now()
        result = ReconResult.success(
            task_id=task.id,
            scope_id=task.scope_id,
            target_id=task.target_id,
            plugin_id=manifest.adapter_id,
            plugin_version=manifest.adapter_version,
            contract_version=manifest.contract_version,
            observations=parsed.observations,
        )
        effective_limits = ExecutionLimits(
            timeout_seconds=min(invocation.timeout_seconds, manifest.limits.max_timeout_seconds),
            max_input_bytes=max(1, len(invocation.canonical_target.encode())),
            max_output_bytes=min(invocation.max_output_bytes, manifest.limits.max_output_bytes),
            max_observations=min(len(parsed.observations) or 1, manifest.limits.max_observations),
        )
        ingestion_receipt = self.ingestion.ingest(
            task=task,
            authorization=authorization,
            result=result,
            effective_limits=effective_limits,
            observed_at=timestamp,
        )
        created = 0
        with SQLiteUnitOfWork(self.factory) as unit:
            assets = SQLiteReconRepository(unit).list_assets(task.scope_id, task.target_id)
            asset_observations = tuple(
                (asset, observation)
                for asset in assets
                for observation in SQLiteReconRepository(unit).list_observations(asset.id)
                if observation.task_id == task.id and observation.plugin_id == manifest.adapter_id
            )
            unit.rollback()
        for asset, observation in asset_observations:
            self.evidence.create_from_observation(
                task,
                authorization,
                asset,
                observation,
                kind=EvidenceKind.SERVICE_METADATA,
                title="Offline network service observation",
                metadata={
                    "synthetic": True,
                    "offline_fixture": True,
                    "source_digest": parsed.source_digest,
                    "output_format": parsed.output_format.value,
                },
                pipeline_id=manifest.adapter_id,
                pipeline_version=manifest.adapter_version,
                collected_at=timestamp,
            )
            created += 1
        return NetworkPortScanReceipt(
            adapter_id=manifest.adapter_id,
            task_id=task.id,
            scope_id=task.scope_id,
            target_id=task.target_id,
            output_format=parsed.output_format.value,
            source_digest=parsed.source_digest,
            parsed_services=len(parsed.services),
            parsed_observations=len(parsed.observations),
            inserted_assets=ingestion_receipt.inserted_assets,
            inserted_observations=ingestion_receipt.inserted_observations,
            created_evidence=created,
        )

    @staticmethod
    def _validate_alignment(
        task: Task,
        authorization: ExecutionAuthorization,
        manifest: NetworkPortScanAdapterManifest,
        invocation: NetworkScanInvocation,
        parsed: NetworkScanParseResult,
    ) -> None:
        if invocation.scope_id != task.scope_id or invocation.target_id != task.target_id:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_CONTEXT_MISMATCH, "Invocation is not Task-bound."
            )
        if (
            parsed.scope_id != task.scope_id
            or parsed.target_id != task.target_id
            or parsed.canonical_target != invocation.canonical_target
        ):
            raise CyberOSError(
                ErrorCode.PORT_SCAN_CONTEXT_MISMATCH, "Parsed result is not context-bound."
            )
        if manifest.adapter_id != invocation.manifest_id:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_MANIFEST_INVALID, "Manifest identity does not match."
            )
        if parsed.output_format is not manifest.output_format:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_OUTPUT_CONTRACT_INVALID, "Output format does not match."
            )
        if (
            authorization.scope_id != task.scope_id
            or authorization.matched_target_id != task.target_id
        ):
            raise CyberOSError(
                ErrorCode.PORT_SCAN_TARGET_UNAUTHORIZED, "Authorization is not Task-bound."
            )
        if parsed.source_digest == "":
            raise CyberOSError(ErrorCode.PORT_SCAN_PARSE_FAILED, "Parser source digest is empty.")
