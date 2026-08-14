"""Offline schema/version drift fixtures for the final Phase 1 slice.

Style note: this harness is deterministic and in-process. Its negative step
must fail before ingestion, Evidence, or repository projection and must never
retry, negotiate, renew authorization, or use live transport.
"""

from dataclasses import dataclass
from datetime import timedelta

from cyberos.application.scope_validation import ScopeValidationService, TargetCandidate
from cyberos.application.services.scope import ScopeService
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.engagement.model import Engagement, EngagementKind
from cyberos.domain.recon.model import AssetKind
from cyberos.domain.recon.schema_drift import (
    MultiWebApiSchemaDriftScenario,
    SchemaDriftCaseKind,
    SchemaDriftReceipt,
)
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


def _drift_error(case_kind: SchemaDriftCaseKind) -> ErrorCode:
    return {
        SchemaDriftCaseKind.DEPRECATED_FIELD_REMOVED: (
            ErrorCode.SCHEMA_DRIFT_DEPRECATED_FIELD_REMOVED
        ),
        SchemaDriftCaseKind.UNEXPECTED_CONTRACT_SHIFT: ErrorCode.SCHEMA_DRIFT_CONTRACT_SHIFT,
        SchemaDriftCaseKind.SYNTHETIC_API_VERSION_MISMATCH: (
            ErrorCode.SCHEMA_DRIFT_VERSION_MISMATCH
        ),
        SchemaDriftCaseKind.STRUCTURAL_ENVELOPE_CHANGED: ErrorCode.SCHEMA_DRIFT_ENVELOPE_CHANGED,
    }[case_kind]


class _DriftEndpointFixturePlugin(ReconPlugin):
    @property
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            plugin_id="offline.web.api.drift.endpoint",
            display_name="Synthetic Drift Prior Endpoint Fixture",
            description="Deterministic synthetic endpoint preceding a drift step.",
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
                        ("scenario_id", "schema-drift-prior"),
                        ("step_id", "prior"),
                        ("port", "443"),
                        ("status_code", "200"),
                    ),
                ),
            ),
        )


class _SchemaDriftFixturePlugin(ReconPlugin):
    def __init__(self, scenario: MultiWebApiSchemaDriftScenario) -> None:
        self.scenario = scenario

    @property
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            plugin_id=f"offline.web.api.drift.{self.scenario.case_kind.value}",
            display_name="Synthetic Schema Drift Fixture",
            description="Controlled deterministic schema drift; no live side effects.",
            plugin_version=self.scenario.fixture_version,
            contract_version=self.scenario.presented_contract_version,
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
        code = _drift_error(self.scenario.case_kind)
        field = {
            SchemaDriftCaseKind.DEPRECATED_FIELD_REMOVED: "required_field",
            SchemaDriftCaseKind.UNEXPECTED_CONTRACT_SHIFT: "contract_shift",
            SchemaDriftCaseKind.SYNTHETIC_API_VERSION_MISMATCH: "version",
            SchemaDriftCaseKind.STRUCTURAL_ENVELOPE_CHANGED: "envelope",
        }[self.scenario.case_kind]
        return ReconResult.failure(
            task_id=invocation.task.id,
            scope_id=invocation.input.scope_id,
            target_id=invocation.input.target_id,
            plugin_id=self.manifest.plugin_id,
            plugin_version=self.manifest.plugin_version,
            contract_version=self.manifest.contract_version,
            errors=(
                ReconError(
                    code=code,
                    message="Synthetic schema drift rejected the contract safely.",
                    field=field,
                ),
            ),
        )


@dataclass(frozen=True, slots=True)
class SchemaDriftResult:
    task: Task
    report: PipelineExecutionReport
    receipt: SchemaDriftReceipt


class MultiWebApiSchemaDriftHarness:
    """Run one committed synthetic step followed by one rejected drift step."""

    def __init__(self, factory: SQLiteConnectionFactory) -> None:
        self.factory = factory

    def run(self, scenario: MultiWebApiSchemaDriftScenario) -> SchemaDriftResult:
        now = scenario.now
        if now is None:
            raise CyberOSError(
                ErrorCode.SCHEMA_DRIFT_FIXTURE_INVALID, "Drift scenario clock is missing."
            )
        workspace = Workspace.create("Offline Drift Workspace", now=now)
        engagement = Engagement.create(
            workspace.id, "Offline Drift Engagement", EngagementKind.LEARNING, now=now
        )
        scope = Scope.create(engagement.id, "Offline Drift Scope", now=now)
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
            scope.id, "offline-drift-approval", expires_at=now + timedelta(days=1)
        )
        if not authorized.ok or authorized.data is None:
            raise CyberOSError(
                ErrorCode.SCHEMA_DRIFT_FIXTURE_INVALID, "Drift Scope authorization failed."
            )
        authorization = ScopeValidationService(self.factory).authorize_execution(
            scope.id, TargetCandidate(saved_target.value, TargetKind.FQDN)
        )
        task = Task.create(
            scope.id,
            saved_target.id,
            authorization,
            ExecutionSpec(command=("offline.web.api.drift",), max_output_bytes=8_192),
            now=now,
        )
        with SQLiteUnitOfWork(self.factory) as unit:
            SQLiteTaskRepository(unit).add(TaskRecord(task=task))
            unit.commit()

        host = PluginHost()
        host.register(_DriftEndpointFixturePlugin())
        drift = _SchemaDriftFixturePlugin(scenario)
        host.register(drift)
        report = ReconPipelineOrchestrator(self.factory, host).execute(
            task,
            authorization,
            PipelineDefinition(
                pipeline_id=scenario.scenario_id,
                pipeline_version=scenario.fixture_version,
                steps=(
                    PipelineStepDefinition(
                        step_id="prior",
                        plugin_id="offline.web.api.drift.endpoint",
                        required_capabilities=(PluginCapability.OFFLINE_DETERMINISTIC,),
                    ),
                    PipelineStepDefinition(
                        step_id="drift",
                        plugin_id=drift.manifest.plugin_id,
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
        if len(assets) != 1 or len(observations) != 1:
            raise CyberOSError(
                ErrorCode.SCHEMA_DRIFT_EXPECTATION_FAILED,
                "Prior committed state was not preserved.",
            )
        receipt = SchemaDriftReceipt(
            scenario.scenario_id,
            scenario.fixture_version,
            "drift",
            scenario.case_kind,
            True,
            True,
            scenario.expected_schema_version,
            scenario.presented_schema_version,
            scenario.expected_contract_version,
            scenario.presented_contract_version,
            scenario.expected_envelope,
            scenario.presented_envelope,
            _drift_error(scenario.case_kind).value,
            1,
            1,
            len(assets),
            len(observations),
        )
        return SchemaDriftResult(report.task, report, receipt)
