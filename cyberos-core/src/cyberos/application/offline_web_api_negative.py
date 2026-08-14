from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from cyberos.application.scope_validation import ScopeValidationService, TargetCandidate
from cyberos.application.services.scope import ScopeService
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.time import ensure_utc, utc_now
from cyberos.domain.engagement.model import Engagement, EngagementKind
from cyberos.domain.recon.model import AssetKind
from cyberos.domain.scope.model import Scope
from cyberos.domain.target.model import Target
from cyberos.domain.target.primitives import TargetKind, TargetRule
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
    PipelineDefinition,
    PipelineExecutionReport,
    PipelineStepDefinition,
    ReconPipelineOrchestrator,
)


class OfflineNegativeCaseKind(StrEnum):
    SYNTHETIC_RATE_LIMIT_429 = "synthetic_rate_limit_429"
    SYNTHETIC_AUTHENTICATION_REJECTION_401 = "synthetic_authentication_rejection_401"
    SYNTHETIC_AUTHORIZATION_REJECTION_403 = "synthetic_authorization_rejection_403"
    UNEXPECTED_PAYLOAD_SHAPE = "unexpected_payload_shape"
    PARAMETER_BOUNDARY_FAILURE = "parameter_boundary_failure"


class SyntheticPayloadShape(StrEnum):
    OBJECT = "object"
    ARRAY = "array"
    NULL = "null"
    SCALAR = "scalar"
    MALFORMED = "malformed"


def _bounded(value: str, field: str, maximum: int, *, allow_empty: bool = False) -> str:
    if (
        not isinstance(value, str)
        or (not allow_empty and not value.strip())
        or len(value) > maximum
    ):
        raise CyberOSError(
            ErrorCode.OFFLINE_NEGATIVE_FIXTURE_INVALID, f"Negative fixture {field} is invalid."
        )
    if any(ord(character) < 32 for character in value):
        raise CyberOSError(
            ErrorCode.OFFLINE_NEGATIVE_FIXTURE_INVALID, f"Negative fixture {field} is invalid."
        )
    return value.strip()


@dataclass(frozen=True, slots=True)
class MultiWebApiNegativeScenario:
    case_kind: OfflineNegativeCaseKind
    scenario_id: str = "offline.web.api.negative"
    fixture_version: str = "1.0.0"
    target_value: str = "api.example.com"
    retry_after_seconds: int | None = None
    authentication_state: str = "missing"
    authorization_state: str = "insufficient_scope"
    payload_shape: SyntheticPayloadShape = SyntheticPayloadShape.ARRAY
    parameter_name: str = ""
    parameter_location: str = "query"
    now: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.case_kind, OfflineNegativeCaseKind):
            raise CyberOSError(
                ErrorCode.OFFLINE_NEGATIVE_FIXTURE_INVALID, "Negative case kind is invalid."
            )
        _bounded(self.scenario_id, "scenario_id", 100)
        _bounded(self.fixture_version, "fixture_version", 32)
        _bounded(self.target_value, "target_value", 253)
        if self.retry_after_seconds is not None and (
            not isinstance(self.retry_after_seconds, int)
            or isinstance(self.retry_after_seconds, bool)
            or not 0 <= self.retry_after_seconds <= 3_600
        ):
            raise CyberOSError(
                ErrorCode.OFFLINE_NEGATIVE_FIXTURE_INVALID, "Retry-after fixture value is invalid."
            )
        if not isinstance(self.payload_shape, SyntheticPayloadShape):
            raise CyberOSError(
                ErrorCode.OFFLINE_NEGATIVE_PAYLOAD_INVALID, "Payload shape is invalid."
            )
        if (
            self.case_kind is OfflineNegativeCaseKind.SYNTHETIC_AUTHENTICATION_REJECTION_401
            and self.authentication_state
            not in {
                "missing",
                "invalid",
            }
        ):
            raise CyberOSError(
                ErrorCode.OFFLINE_NEGATIVE_FIXTURE_INVALID, "Authentication state is invalid."
            )
        if (
            self.case_kind is OfflineNegativeCaseKind.SYNTHETIC_AUTHORIZATION_REJECTION_403
            and self.authorization_state
            not in {
                "insufficient_scope",
                "target_policy_denied",
            }
        ):
            raise CyberOSError(
                ErrorCode.OFFLINE_NEGATIVE_FIXTURE_INVALID, "Authorization state is invalid."
            )
        if self.case_kind is OfflineNegativeCaseKind.PARAMETER_BOUNDARY_FAILURE:
            if (
                not self.parameter_name
                or len(self.parameter_name) > 80
                or any(ord(character) < 32 for character in self.parameter_name)
            ):
                raise CyberOSError(
                    ErrorCode.OFFLINE_NEGATIVE_PARAMETER_INVALID,
                    "Synthetic parameter name boundary is invalid.",
                )
            if self.parameter_location not in {"query", "path", "json_body"}:
                raise CyberOSError(
                    ErrorCode.OFFLINE_NEGATIVE_PARAMETER_INVALID,
                    "Synthetic parameter location boundary is invalid.",
                )
        object.__setattr__(self, "now", ensure_utc(self.now) if self.now else utc_now())


@dataclass(frozen=True, slots=True)
class OfflineNegativeReceipt:
    scenario_id: str
    fixture_version: str
    step_id: str
    case_kind: OfflineNegativeCaseKind
    synthetic: bool
    offline_fixture: bool
    expected_status_code: int | None
    outcome_code: str
    committed_assets_before: int
    committed_observations_before: int
    committed_assets_after: int
    committed_observations_after: int

    def __post_init__(self) -> None:
        if not self.synthetic or not self.offline_fixture or not self.outcome_code.strip():
            raise CyberOSError(
                ErrorCode.OFFLINE_NEGATIVE_FIXTURE_INVALID, "Negative receipt labels are invalid."
            )
        if self.expected_status_code is not None and not 400 <= self.expected_status_code <= 599:
            raise CyberOSError(
                ErrorCode.OFFLINE_NEGATIVE_FIXTURE_INVALID, "Negative status code is invalid."
            )
        if any(
            not isinstance(value, int) or value < 0
            for value in (
                self.committed_assets_before,
                self.committed_observations_before,
                self.committed_assets_after,
                self.committed_observations_after,
            )
        ):
            raise CyberOSError(
                ErrorCode.OFFLINE_NEGATIVE_FIXTURE_INVALID, "Negative receipt counts are invalid."
            )


class _EndpointFixturePlugin(ReconPlugin):
    @property
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            plugin_id="offline.web.api.negative.endpoint",
            display_name="Synthetic Negative Endpoint Fixture",
            description="Deterministic synthetic endpoint preceding a negative fixture.",
            plugin_version="1.0.0",
            contract_version="1.0",
            capabilities=(PluginCapability.OFFLINE_DETERMINISTIC,),
            supported_target_kinds=(TargetKind.FQDN,),
            requirements=PluginRequirements(),
            declared_limits=PluginDeclaredLimits(
                max_input_bytes=4_096,
                max_output_bytes=8_192,
                max_observations=1,
                timeout_seconds=10,
            ),
        )

    def execute(self, invocation: PluginInvocation) -> ReconResult:
        return ReconResult.success(
            task_id=invocation.task.id,
            scope_id=invocation.input.scope_id,
            target_id=invocation.input.target_id,
            plugin_id=self.manifest.plugin_id,
            plugin_version=self.manifest.plugin_version,
            contract_version=self.manifest.contract_version,
            observations=(
                ReconObservation(
                    "http_endpoint",
                    f"https://{invocation.input.candidate.raw_value}/api/v1/items",
                    (
                        ("offline_fixture", "true"),
                        ("synthetic", "true"),
                        ("scenario_id", "negative"),
                        ("step_id", "endpoint"),
                        ("port", "443"),
                        ("status_code", "200"),
                    ),
                ),
            ),
        )


class _NegativeFixturePlugin(ReconPlugin):
    def __init__(self, scenario: MultiWebApiNegativeScenario) -> None:
        self.scenario = scenario

    @property
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            plugin_id=f"offline.web.api.negative.{self.scenario.case_kind.value}",
            display_name="Synthetic Negative Web API Fixture",
            description="Controlled deterministic negative outcome; no live side effects.",
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
        code = ErrorCode.PLUGIN_EXECUTION_FAILED
        field = "case"
        message = "Synthetic negative fixture rejected the request."
        if self.scenario.case_kind is OfflineNegativeCaseKind.UNEXPECTED_PAYLOAD_SHAPE:
            code = ErrorCode.PLUGIN_RESULT_INVALID
            field = "payload_shape"
            message = "Synthetic payload shape is unexpected."
        elif self.scenario.case_kind is OfflineNegativeCaseKind.PARAMETER_BOUNDARY_FAILURE:
            code = ErrorCode.PLUGIN_INPUT_INVALID
            field = "parameter"
            message = "Synthetic parameter boundary failed."
        return ReconResult.failure(
            task_id=invocation.task.id,
            scope_id=invocation.input.scope_id,
            target_id=invocation.input.target_id,
            plugin_id=self.manifest.plugin_id,
            plugin_version=self.manifest.plugin_version,
            contract_version=self.manifest.contract_version,
            errors=(ReconError(code=code, message=message, field=field),),
        )


@dataclass(frozen=True, slots=True)
class OfflineNegativeResult:
    task: Task
    report: PipelineExecutionReport
    receipt: OfflineNegativeReceipt


class MultiWebApiNegativeHarness:
    """Runs one controlled negative step after one committed synthetic endpoint."""

    def __init__(self, factory: SQLiteConnectionFactory) -> None:
        self.factory = factory

    def run(self, scenario: MultiWebApiNegativeScenario) -> OfflineNegativeResult:
        now = scenario.now
        if now is None:
            raise CyberOSError(
                ErrorCode.OFFLINE_NEGATIVE_FIXTURE_INVALID, "Negative scenario clock is missing."
            )
        workspace = Workspace.create("Offline Negative Workspace", now=now)
        engagement = Engagement.create(
            workspace.id, "Offline Negative Engagement", EngagementKind.LEARNING, now=now
        )
        scope = Scope.create(engagement.id, "Offline Negative Scope", now=now)
        target = Target.create(
            scope.id, TargetRule.INCLUDE, TargetKind.FQDN, scenario.target_value, now=now
        )
        with SQLiteUnitOfWork(self.factory) as unit:
            SQLiteWorkspaceRepository(unit).add(workspace)
            SQLiteEngagementRepository(unit).add(engagement)
            SQLiteScopeRepository(unit).add(scope)
            saved_target = SQLiteTargetRepository(unit).add(target)
            unit.commit()
        authorized = ScopeService(self.factory).authorize(
            scope.id, "offline-negative-approval", expires_at=now + timedelta(days=1)
        )
        if not authorized.ok or authorized.data is None:
            raise CyberOSError(
                ErrorCode.OFFLINE_NEGATIVE_FIXTURE_INVALID,
                "Negative fixture Scope authorization failed.",
            )
        authorization = ScopeValidationService(self.factory).authorize_execution(
            scope.id, TargetCandidate(saved_target.value, TargetKind.FQDN)
        )
        task = Task.create(
            scope.id,
            saved_target.id,
            authorization,
            ExecutionSpec(command=("offline.web.api.negative",), max_output_bytes=8_192),
            now=now,
        )
        with SQLiteUnitOfWork(self.factory) as unit:
            SQLiteTaskRepository(unit).add(TaskRecord(task=task))
            unit.commit()
        host = PluginHost()
        host.register(_EndpointFixturePlugin())
        negative = _NegativeFixturePlugin(scenario)
        host.register(negative)
        report = ReconPipelineOrchestrator(self.factory, host).execute(
            task,
            authorization,
            PipelineDefinition(
                pipeline_id=scenario.scenario_id,
                pipeline_version=scenario.fixture_version,
                steps=(
                    PipelineStepDefinition(
                        step_id="endpoint",
                        plugin_id="offline.web.api.negative.endpoint",
                        required_capabilities=(PluginCapability.OFFLINE_DETERMINISTIC,),
                    ),
                    PipelineStepDefinition(
                        step_id="negative",
                        plugin_id=negative.manifest.plugin_id,
                        required_capabilities=(PluginCapability.OFFLINE_DETERMINISTIC,),
                        input_asset_kinds=(AssetKind.URL,),
                    ),
                ),
            ),
        )
        with SQLiteUnitOfWork(self.factory) as unit:
            assets = SQLiteReconRepository(unit).list_assets(scope.id, saved_target.id)
            observations = tuple(
                observation
                for asset in assets
                for observation in SQLiteReconRepository(unit).list_observations(asset.id)
            )
            unit.rollback()
        expected_status = {
            OfflineNegativeCaseKind.SYNTHETIC_RATE_LIMIT_429: 429,
            OfflineNegativeCaseKind.SYNTHETIC_AUTHENTICATION_REJECTION_401: 401,
            OfflineNegativeCaseKind.SYNTHETIC_AUTHORIZATION_REJECTION_403: 403,
        }.get(scenario.case_kind)
        receipt = OfflineNegativeReceipt(
            scenario.scenario_id,
            scenario.fixture_version,
            "negative",
            scenario.case_kind,
            True,
            True,
            expected_status,
            scenario.case_kind.value,
            1,
            1,
            len(assets),
            len(observations),
        )
        return OfflineNegativeResult(report.task, report, receipt)
