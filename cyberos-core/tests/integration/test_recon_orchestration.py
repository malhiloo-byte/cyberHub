from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from cyberos.application.recon_task_result import ReconTaskResultAdapter
from cyberos.application.scope_validation import ExecutionAuthorization, TargetCandidate
from cyberos.config.models import DatabaseSettings
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.engagement.model import Engagement, EngagementKind
from cyberos.domain.recon.model import AssetAggregate, AssetKind, AssetStatus, new_asset_id
from cyberos.domain.scope.model import Scope
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.model import Target
from cyberos.domain.target.primitives import TargetId, TargetKind, TargetRule
from cyberos.domain.task.model import Task
from cyberos.domain.task.primitives import TaskStatus
from cyberos.domain.task.record import TaskRecord
from cyberos.domain.task.spec import ExecutionSpec
from cyberos.domain.workspace.model import Workspace
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.engagement_repository import SQLiteEngagementRepository
from cyberos.persistence.migrations.runner import MigrationRunner
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
    ReconInput,
    ReconObservation,
    ReconResult,
)
from cyberos.recon.host import PluginHost
from cyberos.recon.pipeline import (
    CancellationSignal,
    PipelineDefinition,
    PipelineExecutionReport,
    PipelineInputResolver,
    PipelinePolicy,
    PipelineStatus,
    PipelineStepDefinition,
    ReconPipelineOrchestrator,
)

MIGRATIONS_DIR = Path(__file__).parents[2] / "src/cyberos/persistence/migrations/versions"
NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


class StaticReconPlugin:
    def __init__(
        self,
        plugin_id: str,
        *,
        fail: bool = False,
        observations: int = 1,
        cancel_signal: CancellationSignal | None = None,
    ) -> None:
        self.plugin_id = plugin_id
        self.fail = fail
        self.observation_count = observations
        self.cancel_signal = cancel_signal
        self.calls = 0

    @property
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            plugin_id=self.plugin_id,
            display_name="Static Recon Test Plugin",
            description="Offline deterministic fixture for orchestration tests.",
            plugin_version="1.0.0",
            contract_version="1.0",
            capabilities=(PluginCapability.OFFLINE_DETERMINISTIC,),
            supported_target_kinds=(TargetKind.FQDN,),
            requirements=PluginRequirements(),
            declared_limits=PluginDeclaredLimits(
                max_input_bytes=8_192,
                max_output_bytes=8_192,
                max_observations=32,
                timeout_seconds=30,
            ),
        )

    def execute(self, invocation: PluginInvocation) -> ReconResult:
        self.calls += 1
        if self.cancel_signal is not None:
            self.cancel_signal.cancel()
        if self.fail:
            return ReconResult.failure(
                task_id=invocation.task.id,
                scope_id=invocation.input.scope_id,
                target_id=invocation.input.target_id,
                plugin_id=self.plugin_id,
                plugin_version="1.0.0",
                contract_version="1.0",
                errors=(ReconError(ErrorCode.PLUGIN_EXECUTION_FAILED, "fixture failure"),),
            )
        observations = tuple(
            ReconObservation(
                observation_type="subdomain",
                value=f"dev-{index}.example.com",
                metadata=(("parent_domain", "example.com"),),
            )
            for index in range(self.observation_count)
        )
        return ReconResult.success(
            task_id=invocation.task.id,
            scope_id=invocation.input.scope_id,
            target_id=invocation.input.target_id,
            plugin_id=self.plugin_id,
            plugin_version="1.0.0",
            contract_version="1.0",
            observations=observations,
        )


def factory_for(tmp_path: Path) -> SQLiteConnectionFactory:
    factory = SQLiteConnectionFactory(DatabaseSettings(path=tmp_path / "cyberos.sqlite3"))
    MigrationRunner(factory, MIGRATIONS_DIR).run()
    return factory


def parents(factory: SQLiteConnectionFactory) -> tuple[Scope, Target, Task, ExecutionAuthorization]:
    workspace = Workspace.create("Orchestration Workspace", now=NOW)
    engagement = Engagement.create(
        workspace.id, "Orchestration Engagement", EngagementKind.LEARNING, now=NOW
    )
    scope = Scope.create(engagement.id, "Orchestration Scope", now=NOW)
    target = Target.create(
        scope.id, TargetRule.INCLUDE, TargetKind.FQDN, "api.example.com", now=NOW
    )
    authorization = ExecutionAuthorization(
        scope_id=scope.id,
        candidate=TargetCandidate("api.example.com", TargetKind.FQDN),
        authorized_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        matched_target_id=target.id,
        matching_rule=TargetRule.INCLUDE,
        reason="orchestration_test",
        scope_version=1,
    )
    task = Task.create(
        scope.id,
        target.id,
        authorization,
        ExecutionSpec(command=("fixture", "offline"), max_output_bytes=8_192),
        now=NOW,
    )
    with SQLiteUnitOfWork(factory) as unit:
        SQLiteWorkspaceRepository(unit).add(workspace)
        SQLiteEngagementRepository(unit).add(engagement)
        SQLiteScopeRepository(unit).add(scope)
        SQLiteTargetRepository(unit).add(target)
        SQLiteTaskRepository(unit).add(TaskRecord(task=task))
        unit.commit()
    return scope, target, task, authorization


def definition(*step_ids: str, with_inputs: bool = False) -> PipelineDefinition:
    return PipelineDefinition(
        pipeline_id="fixture.pipeline",
        pipeline_version="1.0.0",
        steps=tuple(
            PipelineStepDefinition(
                step_id=step_id,
                plugin_id=step_id,
                input_asset_kinds=(AssetKind.SUBDOMAIN,) if with_inputs and index > 0 else (),
            )
            for index, step_id in enumerate(step_ids)
        ),
    )


def test_adapter_emits_pipeline_summary_without_raw_streams(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    _, _, task, _ = parents(factory)
    report = PipelineExecutionReport(
        "fixture.pipeline",
        "1.0.0",
        task,
        PipelineStatus.COMPLETED,
        (),
        2,
        2,
    )
    result = ReconTaskResultAdapter.from_pipeline_report(
        report, started_at=NOW, finished_at=NOW + timedelta(milliseconds=125)
    )
    assert result.exit_code == 0
    assert result.stdout.startswith(b"{")
    assert result.stderr == b""
    assert result.duration_seconds == 0.125
    assert b"raw" not in result.stdout.lower()


def test_host_running_route_is_additive_and_pending_route_stays_strict(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    _, _, task, authorization = parents(factory)
    plugin = StaticReconPlugin("running.fixture")
    host = PluginHost()
    host.register(plugin)
    running = task.transition(TaskStatus.RUNNING, at=NOW)
    input_value = ReconInput(task.scope_id, task.target_id, authorization.candidate)
    with pytest.raises(CyberOSError) as legacy_error:
        host.invoke(
            plugin.plugin_id,
            task=running,
            authorization=authorization,
            input=input_value,
            now=NOW,
        )
    assert legacy_error.value.code is ErrorCode.PLUGIN_AUTHORIZATION_INVALID
    result = host.invoke_running(
        plugin.plugin_id,
        task=running,
        authorization=authorization,
        input=input_value,
        now=NOW,
    )
    assert result.status.value == "success"


def test_pipeline_success_chains_and_persists_terminal_summary(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    _, _, task, authorization = parents(factory)
    first = StaticReconPlugin("first.step")
    second = StaticReconPlugin("second.step")
    host = PluginHost()
    host.register(first)
    host.register(second)
    orchestrator = ReconPipelineOrchestrator(factory, host)
    report = orchestrator.execute(
        task, authorization, definition("first.step", "second.step", with_inputs=True)
    )
    assert report.status is PipelineStatus.COMPLETED
    assert len(report.step_receipts) == 2
    with SQLiteUnitOfWork(factory) as unit:
        stored = SQLiteTaskRepository(unit).get(task.id)
        assets = unit.raw.execute("SELECT count(*) FROM assets").fetchone()[0]
        unit.rollback()
    assert stored is not None
    assert stored.task.status.value == "completed"
    assert stored.result is not None
    assert b"fixture.pipeline" in stored.result.stdout
    assert assets == 1


def test_pipeline_budget_rejects_result_without_truncation(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    _, _, task, authorization = parents(factory)
    plugin = StaticReconPlugin("large.step", observations=2)
    host = PluginHost()
    host.register(plugin)
    report = ReconPipelineOrchestrator(
        factory,
        host,
        policy=PipelinePolicy(max_assets=1, max_observations=1),
    ).execute(task, authorization, definition("large.step"))
    assert report.status is PipelineStatus.FAILED
    assert report.failure is not None
    assert report.failure.code == ErrorCode.PLUGIN_LIMIT_EXCEEDED.value
    assert report.task.status is TaskStatus.FAILED


def test_pipeline_budget_rejects_input_before_plugin_call(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    _, _, task, authorization = parents(factory)
    plugin = StaticReconPlugin("input.limit")
    host = PluginHost()
    host.register(plugin)
    report = ReconPipelineOrchestrator(
        factory,
        host,
        policy=PipelinePolicy(max_payload_bytes=1),
    ).execute(task, authorization, definition("input.limit"))
    assert report.status is PipelineStatus.FAILED
    assert report.failure is not None
    assert report.failure.code == ErrorCode.PLUGIN_LIMIT_EXCEEDED.value
    assert plugin.calls == 0


def test_pipeline_partial_failure_retains_prior_committed_step(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    _, _, task, authorization = parents(factory)
    first = StaticReconPlugin("first.success")
    second = StaticReconPlugin("second.failure", fail=True)
    host = PluginHost()
    host.register(first)
    host.register(second)
    report = ReconPipelineOrchestrator(factory, host).execute(
        task, authorization, definition("first.success", "second.failure", with_inputs=True)
    )
    assert report.status is PipelineStatus.FAILED
    assert len(report.step_receipts) == 1
    with SQLiteUnitOfWork(factory) as unit:
        asset_count = unit.raw.execute("SELECT count(*) FROM assets").fetchone()[0]
        observation_count = unit.raw.execute("SELECT count(*) FROM asset_observations").fetchone()[
            0
        ]
        unit.rollback()
    assert asset_count == 1
    assert observation_count == 1


def test_pipeline_cancellation_before_start_is_terminal_and_does_not_call_plugin(
    tmp_path: Path,
) -> None:
    factory = factory_for(tmp_path)
    _, _, task, authorization = parents(factory)
    plugin = StaticReconPlugin("cancel.step")
    host = PluginHost()
    host.register(plugin)
    signal = CancellationSignal()
    signal.cancel()
    report = ReconPipelineOrchestrator(factory, host).execute(
        task, authorization, definition("cancel.step"), signal
    )
    assert report.status is PipelineStatus.CANCELLED
    assert plugin.calls == 0
    with SQLiteUnitOfWork(factory) as unit:
        stored = SQLiteTaskRepository(unit).get(task.id)
        unit.rollback()
    assert stored is not None
    assert stored.task.status is TaskStatus.CANCELLED
    assert stored.result is not None
    assert stored.result.exit_code == 130


def test_pipeline_cancellation_after_plugin_return_discards_uncommitted_result(
    tmp_path: Path,
) -> None:
    factory = factory_for(tmp_path)
    _, _, task, authorization = parents(factory)
    signal = CancellationSignal()
    plugin = StaticReconPlugin("cancel.after", cancel_signal=signal)
    host = PluginHost()
    host.register(plugin)
    report = ReconPipelineOrchestrator(factory, host).execute(
        task, authorization, definition("cancel.after"), signal
    )
    assert report.status is PipelineStatus.CANCELLED
    with SQLiteUnitOfWork(factory) as unit:
        asset_count = unit.raw.execute("SELECT count(*) FROM assets").fetchone()[0]
        unit.rollback()
    assert asset_count == 0


class EmptyAssetReader:
    def list_assets(self, scope_id: object, target_id: object) -> tuple[object, ...]:
        return ()


def test_input_resolver_requires_declared_same_target_inputs(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    _, _, task, _ = parents(factory)
    resolver = PipelineInputResolver(EmptyAssetReader())  # type: ignore[arg-type]
    with pytest.raises(CyberOSError) as error:
        resolver.resolve(
            task,
            PipelineStepDefinition(
                "needs-subdomain",
                "offline.fixture",
                required_capabilities=(),
                input_asset_kinds=(AssetKind.SUBDOMAIN,),
            ),
        )
    assert error.value.code is ErrorCode.PLUGIN_INPUT_INVALID


def test_pipeline_rejects_capability_not_declared_by_registered_plugin(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    _, _, task, authorization = parents(factory)
    plugin = StaticReconPlugin("capability.step")
    host = PluginHost()
    host.register(plugin)
    with pytest.raises(CyberOSError) as error:
        ReconPipelineOrchestrator(factory, host).execute(
            task,
            authorization,
            PipelineDefinition(
                "capability.pipeline",
                "1.0.0",
                (
                    PipelineStepDefinition(
                        "capability.step",
                        "capability.step",
                        required_capabilities=(PluginCapability.NETWORK_DNS,),
                    ),
                ),
            ),
        )
    assert error.value.code is ErrorCode.PLUGIN_CAPABILITY_DENIED


def test_input_resolver_rejects_cross_scope_asset_even_with_matching_task_provenance() -> None:
    scope_id = ScopeId(uuid4())
    target_id = TargetId(uuid4())
    task_id = uuid4()
    wrong_scope_asset = AssetAggregate(
        id=new_asset_id(),
        scope_id=ScopeId(uuid4()),
        target_id=target_id,
        asset_kind=AssetKind.SUBDOMAIN,
        canonical_value="dev.example.com",
        display_value="dev.example.com",
        status=AssetStatus.ACTIVE,
        first_seen_at=NOW,
        last_seen_at=NOW,
        first_seen_task_id=task_id,
        last_seen_task_id=task_id,
        created_at=NOW,
        updated_at=NOW,
        archived_at=None,
        version=1,
    )

    class SingleAssetReader:
        def list_assets(
            self, requested_scope: ScopeId, requested_target: TargetId
        ) -> tuple[AssetAggregate, ...]:
            return (wrong_scope_asset,)

    task = type("TaskInput", (), {"scope_id": scope_id, "target_id": target_id, "id": task_id})()
    resolver = PipelineInputResolver(SingleAssetReader())
    with pytest.raises(CyberOSError) as error:
        resolver.resolve(
            task,
            PipelineStepDefinition(
                "scope.bound",
                "offline.fixture",
                input_asset_kinds=(AssetKind.SUBDOMAIN,),
            ),
        )
    assert error.value.code is ErrorCode.PLUGIN_INPUT_INVALID


def test_pipeline_redacts_unexpected_plugin_exception_from_report(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    _, _, task, authorization = parents(factory)

    class ExplodingPlugin(StaticReconPlugin):
        def execute(self, invocation: PluginInvocation) -> ReconResult:
            raise RuntimeError("credential=top-secret")

    plugin = ExplodingPlugin("explode.step")
    host = PluginHost()
    host.register(plugin)
    report = ReconPipelineOrchestrator(factory, host).execute(
        task, authorization, definition("explode.step")
    )
    assert report.status is PipelineStatus.FAILED
    assert report.failure is not None
    assert "top-secret" not in report.failure.message
    assert report.failure.message == "Pipeline step failed safely."
