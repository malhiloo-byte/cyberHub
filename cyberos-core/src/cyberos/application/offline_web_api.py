from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from cyberos.application.recon_evidence import ReconEvidenceService
from cyberos.application.recon_reporting import ReconReportingService
from cyberos.application.scope_validation import (
    ExecutionAuthorization,
    ScopeValidationService,
    TargetCandidate,
)
from cyberos.application.services.scope import ScopeService
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.time import ensure_utc, utc_now
from cyberos.domain.engagement.model import Engagement, EngagementKind
from cyberos.domain.recon.evidence import EvidenceKind, EvidenceRecord
from cyberos.domain.recon.model import AssetKind
from cyberos.domain.recon.reporting import ReconReportContext, TargetReconSummary
from cyberos.domain.scope.model import Scope
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.model import Target
from cyberos.domain.target.primitives import TargetId, TargetKind, TargetRule
from cyberos.domain.task.model import Task
from cyberos.domain.task.record import TaskRecord
from cyberos.domain.task.spec import ExecutionSpec
from cyberos.domain.workspace.model import Workspace
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.engagement_repository import SQLiteEngagementRepository
from cyberos.persistence.recon_repository import SQLiteReconRepository
from cyberos.persistence.scope_repository import SQLiteScopeRepository
from cyberos.persistence.target_repository import SQLiteTargetRepository
from cyberos.persistence.task_repository import SQLiteTaskRepository
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork
from cyberos.persistence.workspace_repository import SQLiteWorkspaceRepository
from cyberos.recon.contracts import (
    PluginCapability,
    PluginDeclaredLimits,
    PluginInvocation,
    PluginManifest,
    PluginRequirements,
    ReconError,
    ReconObservation,
    ReconPlugin,
    ReconResult,
)
from cyberos.recon.host import PluginHost
from cyberos.recon.pipeline import (
    CancellationSignal,
    PipelineDefinition,
    PipelineExecutionReport,
    PipelineStepDefinition,
    ReconPipelineOrchestrator,
)

_SAFE_HEADERS = frozenset({"content-type", "server-family", "cache-control", "x-fixture-id"})
_FORBIDDEN_HEADERS = frozenset({"authorization", "cookie", "set-cookie", "proxy-authorization"})
_METHODS = frozenset({"GET", "POST", "PUT", "DELETE"})
_PARAMETER_LOCATIONS = frozenset({"query", "path", "json_body"})


class OfflineWebApiStepKind(StrEnum):
    REST_ENDPOINT_INVENTORY = "rest_endpoint_inventory"
    SYNTHETIC_RESPONSE_HEADERS = "synthetic_response_headers"
    PARAMETER_NAME_DISCOVERY = "parameter_name_discovery"


def _fixture_text(value: str, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise CyberOSError(
            ErrorCode.OFFLINE_FIXTURE_INVALID, f"Offline fixture {field} is invalid."
        )
    if any(ord(character) < 32 for character in value):
        raise CyberOSError(
            ErrorCode.OFFLINE_FIXTURE_INVALID, f"Offline fixture {field} is invalid."
        )
    return value.strip()


@dataclass(frozen=True, slots=True)
class OfflineWebApiStep:
    step_id: str
    kind: OfflineWebApiStepKind
    route_path: str = "/api/v1/items"
    method: str = "GET"
    safe_headers: tuple[tuple[str, str], ...] = ()
    parameters: tuple[tuple[str, str], ...] = ()
    fail: bool = False

    def __post_init__(self) -> None:
        _fixture_text(self.step_id, "step_id", 80)
        if not isinstance(self.kind, OfflineWebApiStepKind):
            raise CyberOSError(
                ErrorCode.OFFLINE_FIXTURE_INVALID, "Offline fixture step kind is invalid."
            )
        route = _fixture_text(self.route_path, "route_path", 200)
        if not route.startswith("/") or "?" in route or "#" in route:
            raise CyberOSError(
                ErrorCode.OFFLINE_FIXTURE_INVALID, "Offline fixture route is invalid."
            )
        object.__setattr__(self, "route_path", route)
        method = _fixture_text(self.method, "method", 8).upper()
        if method not in _METHODS:
            raise CyberOSError(
                ErrorCode.OFFLINE_FIXTURE_INVALID, "Offline fixture method is invalid."
            )
        object.__setattr__(self, "method", method)
        if self.kind is OfflineWebApiStepKind.SYNTHETIC_RESPONSE_HEADERS:
            self._validate_headers()
        elif self.safe_headers:
            raise CyberOSError(
                ErrorCode.OFFLINE_FIXTURE_INVALID, "Headers are invalid for this step."
            )
        if self.kind is OfflineWebApiStepKind.PARAMETER_NAME_DISCOVERY:
            self._validate_parameters()
        elif self.parameters:
            raise CyberOSError(
                ErrorCode.OFFLINE_FIXTURE_INVALID, "Parameters are invalid for this step."
            )

    def _validate_headers(self) -> None:
        seen: set[str] = set()
        for name, value in self.safe_headers:
            normalized = _fixture_text(name, "header name", 80).casefold()
            if normalized in _FORBIDDEN_HEADERS or normalized not in _SAFE_HEADERS:
                raise CyberOSError(
                    ErrorCode.OFFLINE_FIXTURE_INVALID, "Offline header is not allowlisted."
                )
            if normalized in seen:
                raise CyberOSError(
                    ErrorCode.OFFLINE_FIXTURE_INVALID, "Offline header is duplicated."
                )
            seen.add(normalized)
            _fixture_text(value, "header value", 256)

    def _validate_parameters(self) -> None:
        seen: set[str] = set()
        for name, location in self.parameters:
            normalized_name = _fixture_text(name, "parameter name", 80)
            normalized_location = _fixture_text(location, "parameter location", 16)
            if normalized_name in seen or normalized_location not in _PARAMETER_LOCATIONS:
                raise CyberOSError(
                    ErrorCode.OFFLINE_FIXTURE_INVALID, "Offline parameter is invalid."
                )
            seen.add(normalized_name)


@dataclass(frozen=True, slots=True)
class MultiWebApiOfflineScenario:
    scenario_id: str = "offline.web.api"
    fixture_version: str = "1.0.0"
    target_value: str = "api.example.com"
    steps: tuple[OfflineWebApiStep, ...] = ()
    now: datetime | None = None

    def __post_init__(self) -> None:
        _fixture_text(self.scenario_id, "scenario_id", 100)
        _fixture_text(self.fixture_version, "fixture_version", 32)
        _fixture_text(self.target_value, "target_value", 253)
        timestamp = ensure_utc(self.now) if self.now is not None else utc_now()
        object.__setattr__(self, "now", timestamp)
        if not self.steps:
            object.__setattr__(
                self,
                "steps",
                (
                    OfflineWebApiStep("endpoint", OfflineWebApiStepKind.REST_ENDPOINT_INVENTORY),
                    OfflineWebApiStep(
                        "headers",
                        OfflineWebApiStepKind.SYNTHETIC_RESPONSE_HEADERS,
                        safe_headers=(
                            ("content-type", "application/json"),
                            ("server-family", "fixture-server"),
                        ),
                    ),
                    OfflineWebApiStep(
                        "parameters",
                        OfflineWebApiStepKind.PARAMETER_NAME_DISCOVERY,
                        parameters=(("page", "query"), ("limit", "query")),
                    ),
                ),
            )
        if len(self.steps) != 3 or tuple(step.kind for step in self.steps) != (
            OfflineWebApiStepKind.REST_ENDPOINT_INVENTORY,
            OfflineWebApiStepKind.SYNTHETIC_RESPONSE_HEADERS,
            OfflineWebApiStepKind.PARAMETER_NAME_DISCOVERY,
        ):
            raise CyberOSError(
                ErrorCode.OFFLINE_FIXTURE_INVALID, "Offline Web API step sequence is invalid."
            )
        if len({step.step_id for step in self.steps}) != len(self.steps):
            raise CyberOSError(
                ErrorCode.OFFLINE_FIXTURE_INVALID, "Offline Web API step IDs are duplicated."
            )


@dataclass(frozen=True, slots=True)
class MultiWebApiOfflineResult:
    task: Task
    report: PipelineExecutionReport
    evidence: tuple[EvidenceRecord, ...]
    summary: TargetReconSummary | None


class _OfflineWebApiFixturePlugin(ReconPlugin):
    def __init__(
        self,
        step: OfflineWebApiStep,
        scenario: MultiWebApiOfflineScenario,
        signal: CancellationSignal,
        cancel_after_step_id: str | None,
    ) -> None:
        self.step = step
        self.scenario = scenario
        self.signal = signal
        self.cancel_after_step_id = cancel_after_step_id

    @property
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            plugin_id=f"offline.web.api.{self.step.step_id}",
            display_name=f"Synthetic {self.step.kind.value}",
            description="Deterministic synthetic Web API fixture; no live side effects.",
            plugin_version=self.scenario.fixture_version,
            contract_version="1.0",
            capabilities=(PluginCapability.OFFLINE_DETERMINISTIC,),
            supported_target_kinds=(TargetKind.FQDN,),
            requirements=PluginRequirements(),
            declared_limits=PluginDeclaredLimits(
                max_input_bytes=8_192,
                max_output_bytes=8_192,
                max_observations=1,
                timeout_seconds=10,
            ),
        )

    def execute(self, invocation: PluginInvocation) -> ReconResult:
        if self.step.fail:
            return ReconResult.failure(
                task_id=invocation.task.id,
                scope_id=invocation.input.scope_id,
                target_id=invocation.input.target_id,
                plugin_id=self.manifest.plugin_id,
                plugin_version=self.manifest.plugin_version,
                contract_version=self.manifest.contract_version,
                errors=(
                    ReconError(
                        code=ErrorCode.PLUGIN_EXECUTION_FAILED,
                        message="Synthetic Web API fixture step failed.",
                        field="step",
                    ),
                ),
            )
        metadata = {
            "offline_fixture": "true",
            "synthetic": "true",
            "scenario_id": self.scenario.scenario_id,
            "fixture_version": self.scenario.fixture_version,
            "step_id": self.step.step_id,
        }
        if self.step.kind is OfflineWebApiStepKind.REST_ENDPOINT_INVENTORY:
            observation = ReconObservation(
                "http_endpoint",
                f"https://{invocation.input.candidate.raw_value}{self.step.route_path}",
                tuple(
                    sorted(
                        {
                            **metadata,
                            "port": "443",
                            "status_code": "200",
                            "title": "synthetic offline endpoint",
                        }.items()
                    )
                ),
            )
        elif self.step.kind is OfflineWebApiStepKind.SYNTHETIC_RESPONSE_HEADERS:
            digest = hashlib.sha256(
                json.dumps(
                    dict(self.step.safe_headers), sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
            observation = ReconObservation(
                "http_endpoint",
                f"https://{invocation.input.candidate.raw_value}{self.step.route_path}",
                tuple(
                    sorted(
                        {
                            **metadata,
                            "header_names": ",".join(
                                sorted(name for name, _ in self.step.safe_headers)
                            ),
                            "header_digest": digest,
                            "port": "443",
                            "status_code": "200",
                        }.items()
                    )
                ),
            )
        else:
            observation = ReconObservation(
                "http_endpoint",
                f"https://{invocation.input.candidate.raw_value}{self.step.route_path}",
                tuple(
                    sorted(
                        {
                            **metadata,
                            "parameter_names": ",".join(
                                sorted(name for name, _ in self.step.parameters)
                            ),
                            "parameter_locations": ",".join(
                                location for _, location in self.step.parameters
                            ),
                            "port": "443",
                            "status_code": "200",
                        }.items()
                    )
                ),
            )
        result = ReconResult.success(
            task_id=invocation.task.id,
            scope_id=invocation.input.scope_id,
            target_id=invocation.input.target_id,
            plugin_id=self.manifest.plugin_id,
            plugin_version=self.manifest.plugin_version,
            contract_version=self.manifest.contract_version,
            observations=(observation,),
        )
        if self.step.step_id == self.cancel_after_step_id:
            self.signal.cancel()
        return result


class MultiWebApiOfflineHarness:
    """Executes the approved three-step synthetic Web API workflow in-process."""

    def __init__(self, factory: SQLiteConnectionFactory) -> None:
        self.factory = factory

    def run(
        self,
        scenario: MultiWebApiOfflineScenario | None = None,
        *,
        cancel_after_step_id: str | None = None,
    ) -> MultiWebApiOfflineResult:
        selected = scenario or MultiWebApiOfflineScenario()
        now = selected.now
        if now is None:
            raise CyberOSError(
                ErrorCode.OFFLINE_FIXTURE_INVALID, "Offline scenario clock is missing."
            )
        workspace = Workspace.create("Offline Web API Workspace", now=now)
        engagement = Engagement.create(
            workspace.id, "Offline Web API Engagement", EngagementKind.LEARNING, now=now
        )
        scope = Scope.create(engagement.id, "Offline Web API Scope", now=now)
        target = Target.create(
            scope.id, TargetRule.INCLUDE, TargetKind.FQDN, selected.target_value, now=now
        )
        with SQLiteUnitOfWork(self.factory) as unit:
            SQLiteWorkspaceRepository(unit).add(workspace)
            SQLiteEngagementRepository(unit).add(engagement)
            SQLiteScopeRepository(unit).add(scope)
            saved_target = SQLiteTargetRepository(unit).add(target)
            unit.commit()
        authorized = ScopeService(self.factory).authorize(
            scope.id, "offline-web-api-fixture-approval", expires_at=now + timedelta(days=1)
        )
        if not authorized.ok or authorized.data is None:
            raise CyberOSError(
                ErrorCode.OFFLINE_FIXTURE_CONTEXT_INVALID, "Offline Scope authorization failed."
            )
        authorization = ScopeValidationService(self.factory).authorize_execution(
            scope.id, TargetCandidate(saved_target.value, TargetKind.FQDN)
        )
        task = Task.create(
            scope.id,
            saved_target.id,
            authorization,
            ExecutionSpec(command=("offline.web.api.fixture",), max_output_bytes=8_192),
            now=now,
        )
        with SQLiteUnitOfWork(self.factory) as unit:
            SQLiteTaskRepository(unit).add(TaskRecord(task=task))
            unit.commit()

        host = PluginHost()
        signal = CancellationSignal()
        for step in selected.steps:
            host.register(_OfflineWebApiFixturePlugin(step, selected, signal, cancel_after_step_id))
        definition = PipelineDefinition(
            pipeline_id=selected.scenario_id,
            pipeline_version=selected.fixture_version,
            steps=tuple(
                PipelineStepDefinition(
                    step_id=step.step_id,
                    plugin_id=f"offline.web.api.{step.step_id}",
                    required_capabilities=(PluginCapability.OFFLINE_DETERMINISTIC,),
                    input_asset_kinds=(AssetKind.URL,) if index > 0 else (),
                    parameters=(
                        ("scenario_id", selected.scenario_id),
                        ("fixture_version", selected.fixture_version),
                        ("step_id", step.step_id),
                    ),
                )
                for index, step in enumerate(selected.steps)
            ),
        )
        report = ReconPipelineOrchestrator(self.factory, host).execute(
            task, authorization, definition, cancellation=signal
        )
        if report.status.value != "completed":
            return MultiWebApiOfflineResult(report.task, report, (), None)

        evidence = self._create_evidence(
            selected, report.task, authorization, scope.id, saved_target.id, now
        )
        summary = ReconReportingService(self.factory, clock=lambda: now).target_recon_summary(
            ReconReportContext(scope.id, saved_target.id, report.task.id)
        )
        return MultiWebApiOfflineResult(report.task, report, evidence, summary)

    def _create_evidence(
        self,
        scenario: MultiWebApiOfflineScenario,
        task: Task,
        authorization: ExecutionAuthorization,
        scope_id: ScopeId,
        target_id: TargetId,
        now: datetime,
    ) -> tuple[EvidenceRecord, ...]:
        with SQLiteUnitOfWork(self.factory) as unit:
            repository = SQLiteReconRepository(unit)
            assets = repository.list_assets(scope_id, target_id)
            pairs = tuple(
                (asset, observation)
                for asset in assets
                for observation in repository.list_observations(asset.id)
                if observation.task_id == task.id
            )
            unit.rollback()
        records: list[EvidenceRecord] = []
        for asset, observation in pairs:
            records.append(
                ReconEvidenceService(self.factory).create_from_observation(
                    task,
                    authorization,
                    asset,
                    observation,
                    kind=EvidenceKind.HTTP_METADATA,
                    title=f"Synthetic Web API {observation.plugin_id}",
                    metadata={
                        "offline_fixture": True,
                        "synthetic": True,
                        "scenario_id": scenario.scenario_id,
                        "fixture_version": scenario.fixture_version,
                        "step_id": observation.plugin_id.rsplit(".", 1)[-1],
                    },
                    pipeline_id=scenario.scenario_id,
                    pipeline_version=scenario.fixture_version,
                    collected_at=now,
                )
            )
        return tuple(records)
