from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from cyberos.application.recon_ingestion import ReconIngestionService
from cyberos.application.scope_validation import ExecutionAuthorization
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.time import utc_now
from cyberos.domain.recon.model import AssetAggregate, AssetKind
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.primitives import TargetId, TargetRule
from cyberos.domain.task.model import Task
from cyberos.domain.task.primitives import TaskStatus
from cyberos.domain.task.record import TaskRecord
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.recon_repository import SQLiteReconRepository
from cyberos.persistence.task_repository import SQLiteTaskRepository
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork
from cyberos.recon.contracts import (
    ExecutionLimits,
    PluginCapability,
    ReconInput,
    ReconResult,
    ReconStatus,
)
from cyberos.recon.host import PluginHost

_PIPELINE_ID_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


class PipelinePhase(StrEnum):
    VALIDATING = "validating"
    EXECUTING = "executing"
    INGESTING = "ingesting"
    NEXT_STEP = "next_step"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PipelineStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class PipelinePolicy:
    max_timeout_seconds: int = 3_600
    max_payload_bytes: int = 16_777_216
    max_assets: int = 1_000
    max_observations: int = 10_000

    def __post_init__(self) -> None:
        values = (
            self.max_timeout_seconds,
            self.max_payload_bytes,
            self.max_assets,
            self.max_observations,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in values
        ):
            raise CyberOSError(
                ErrorCode.PLUGIN_LIMIT_EXCEEDED, "Pipeline policy limits must be positive."
            )


@dataclass(frozen=True, slots=True)
class PipelineBudget:
    timeout_seconds: int
    payload_bytes: int
    assets: int
    observations: int
    consumed_payload_bytes: int = 0
    consumed_assets: int = 0
    consumed_observations: int = 0

    @classmethod
    def from_task(cls, task: Task, policy: PipelinePolicy) -> PipelineBudget:
        return cls(
            timeout_seconds=min(task.execution_spec.timeout_seconds, policy.max_timeout_seconds),
            payload_bytes=min(task.execution_spec.max_output_bytes, policy.max_payload_bytes),
            assets=policy.max_assets,
            observations=policy.max_observations,
        )

    @property
    def remaining_timeout(self) -> int:
        return self.timeout_seconds

    @property
    def remaining_payload_bytes(self) -> int:
        return self.payload_bytes - self.consumed_payload_bytes

    @property
    def remaining_assets(self) -> int:
        return self.assets - self.consumed_assets

    @property
    def remaining_observations(self) -> int:
        return self.observations - self.consumed_observations

    def limits_for_step(self) -> ExecutionLimits:
        if self.remaining_payload_bytes < 1 or self.remaining_observations < 1:
            raise CyberOSError(ErrorCode.PLUGIN_LIMIT_EXCEEDED, "Pipeline budget is exhausted.")
        return ExecutionLimits(
            timeout_seconds=max(1, self.remaining_timeout),
            max_input_bytes=self.remaining_payload_bytes,
            max_output_bytes=self.remaining_payload_bytes,
            max_observations=self.remaining_observations,
        )

    def reserve(self, result: ReconResult) -> PipelineBudget:
        payload = len(result.to_json().encode("utf-8"))
        observations = len(result.observations)
        assets = observations
        if payload > self.remaining_payload_bytes:
            raise CyberOSError(ErrorCode.PLUGIN_LIMIT_EXCEEDED, "Pipeline payload budget exceeded.")
        if observations > self.remaining_observations or assets > self.remaining_assets:
            raise CyberOSError(ErrorCode.PLUGIN_LIMIT_EXCEEDED, "Pipeline asset budget exceeded.")
        return replace(
            self,
            consumed_payload_bytes=self.consumed_payload_bytes + payload,
            consumed_assets=self.consumed_assets + assets,
            consumed_observations=self.consumed_observations + observations,
        )


class CancellationSignal:
    def __init__(self) -> None:
        self._cancelled = False

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        self._cancelled = True


@dataclass(frozen=True, slots=True)
class PipelineStepDefinition:
    step_id: str
    plugin_id: str
    required_capabilities: tuple[PluginCapability, ...] = ()
    input_asset_kinds: tuple[AssetKind, ...] = ()
    parameters: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.step_id or not self.plugin_id:
            raise CyberOSError(ErrorCode.INVALID_INPUT, "Pipeline step identity cannot be empty.")
        if not isinstance(self.required_capabilities, tuple) or any(
            not isinstance(value, PluginCapability) for value in self.required_capabilities
        ):
            raise CyberOSError(ErrorCode.INVALID_INPUT, "Pipeline capabilities are invalid.")
        if len(set(self.required_capabilities)) != len(self.required_capabilities):
            raise CyberOSError(ErrorCode.INVALID_INPUT, "Pipeline capabilities must be unique.")
        if not isinstance(self.input_asset_kinds, tuple) or any(
            not isinstance(value, AssetKind) for value in self.input_asset_kinds
        ):
            raise CyberOSError(ErrorCode.INVALID_INPUT, "Pipeline input asset kinds are invalid.")
        if len(set(self.input_asset_kinds)) != len(self.input_asset_kinds):
            raise CyberOSError(
                ErrorCode.INVALID_INPUT, "Pipeline input asset kinds must be unique."
            )


@dataclass(frozen=True, slots=True)
class PipelineDefinition:
    pipeline_id: str
    pipeline_version: str
    steps: tuple[PipelineStepDefinition, ...]

    def __post_init__(self) -> None:
        if _PIPELINE_ID_RE.fullmatch(self.pipeline_id) is None:
            raise CyberOSError(ErrorCode.INVALID_INPUT, "Pipeline identity is invalid.")
        if not re.fullmatch(r"\d+\.\d+\.\d+", self.pipeline_version):
            raise CyberOSError(ErrorCode.INVALID_INPUT, "Pipeline version must be SemVer.")
        if not isinstance(self.steps, tuple) or not self.steps or len(self.steps) > 32:
            raise CyberOSError(ErrorCode.INVALID_INPUT, "Pipeline must contain 1 to 32 steps.")
        if any(not isinstance(step, PipelineStepDefinition) for step in self.steps):
            raise CyberOSError(ErrorCode.INVALID_INPUT, "Pipeline steps are invalid.")
        ids = [step.step_id for step in self.steps]
        if len(set(ids)) != len(ids):
            raise CyberOSError(ErrorCode.INVALID_INPUT, "Pipeline step IDs must be unique.")


@dataclass(frozen=True, slots=True)
class PipelineInputBundle:
    assets: tuple[AssetAggregate, ...]

    def to_parameters(self) -> tuple[tuple[str, str], ...]:
        payload: list[dict[str, str]] = []
        for asset in self.assets:
            if "?" in asset.canonical_value or "#" in asset.canonical_value:
                raise CyberOSError(
                    ErrorCode.PLUGIN_INPUT_INVALID,
                    "Raw query or fragment cannot enter a pipeline bundle.",
                )
            payload.append(
                {
                    "asset_id": str(asset.id),
                    "asset_kind": asset.asset_kind.value,
                    "canonical_value": asset.canonical_value,
                }
            )
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 1_024:
            raise CyberOSError(
                ErrorCode.PLUGIN_LIMIT_EXCEEDED,
                "Pipeline input bundle exceeds the parameter limit.",
            )
        return (("pipeline_assets", encoded),) if payload else ()


@dataclass(frozen=True, slots=True)
class PipelineContext:
    task: Task
    authorization: ExecutionAuthorization
    definition: PipelineDefinition
    step: PipelineStepDefinition
    phase: PipelinePhase
    budget: PipelineBudget
    input_bundle: PipelineInputBundle


@dataclass(frozen=True, slots=True)
class StepReceipt:
    step_id: str
    plugin_id: str
    status: str
    committed_assets: int = 0
    committed_observations: int = 0


@dataclass(frozen=True, slots=True)
class PipelineFailure:
    code: str
    message: str
    step_id: str | None = None


@dataclass(frozen=True, slots=True)
class PipelineExecutionReport:
    pipeline_id: str
    pipeline_version: str
    task: Task
    status: PipelineStatus
    step_receipts: tuple[StepReceipt, ...]
    committed_asset_count: int
    committed_observation_count: int
    failure: PipelineFailure | None = None
    timeout_exceeded: bool = False


class PipelineAssetReader(Protocol):
    def list_assets(self, scope_id: ScopeId, target_id: TargetId) -> tuple[AssetAggregate, ...]: ...


class SQLitePipelineAssetReader:
    def __init__(self, factory: SQLiteConnectionFactory) -> None:
        self.factory = factory

    def list_assets(self, scope_id: ScopeId, target_id: TargetId) -> tuple[AssetAggregate, ...]:
        with SQLiteUnitOfWork(self.factory) as unit:
            assets = SQLiteReconRepository(unit).list_assets(scope_id, target_id)
            unit.rollback()
        return assets


class PipelineInputResolver:
    def __init__(self, asset_reader: PipelineAssetReader) -> None:
        self.asset_reader = asset_reader

    def resolve(self, task: Task, step: PipelineStepDefinition) -> PipelineInputBundle:
        assets = self.asset_reader.list_assets(task.scope_id, task.target_id)
        same_task = tuple(
            asset
            for asset in assets
            if asset.last_seen_task_id == task.id
            and asset.scope_id == task.scope_id
            and asset.target_id == task.target_id
            and asset.status.value == "active"
            and (not step.input_asset_kinds or asset.asset_kind in step.input_asset_kinds)
        )
        if step.input_asset_kinds and not same_task:
            raise CyberOSError(
                ErrorCode.PLUGIN_INPUT_INVALID, "Pipeline step has no approved same-target inputs."
            )
        bundle = PipelineInputBundle(assets=same_task)
        bundle.to_parameters()
        return bundle


class ReconPipelineOrchestrator:
    def __init__(
        self,
        factory: SQLiteConnectionFactory,
        host: PluginHost,
        *,
        input_resolver: PipelineInputResolver | None = None,
        policy: PipelinePolicy | None = None,
        ingestion_service: ReconIngestionService | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.factory = factory
        self.host = host
        self.input_resolver = input_resolver or PipelineInputResolver(
            SQLitePipelineAssetReader(factory)
        )
        self.policy = policy or PipelinePolicy()
        self.ingestion_service = ingestion_service or ReconIngestionService(factory)
        self.clock = clock

    def execute(
        self,
        task: Task,
        authorization: ExecutionAuthorization,
        definition: PipelineDefinition,
        cancellation: CancellationSignal | None = None,
    ) -> PipelineExecutionReport:
        signal = cancellation or CancellationSignal()
        self._validate_start(task, authorization, definition)
        if signal.is_cancelled:
            cancelled = task.transition(TaskStatus.CANCELLED, at=self.clock())
            report = PipelineExecutionReport(
                definition.pipeline_id,
                definition.pipeline_version,
                cancelled,
                PipelineStatus.CANCELLED,
                (),
                0,
                0,
            )
            self._persist_terminal(
                report,
                started_at=cancelled.updated_at,
                expected_version=task.version,
            )
            return report

        started_at = self.clock()
        running = task.transition(TaskStatus.RUNNING, at=started_at)
        self._persist_task(running, expected_version=task.version)
        budget = PipelineBudget.from_task(running, self.policy)
        receipts: list[StepReceipt] = []
        committed_assets = 0
        committed_observations = 0

        for step in definition.steps:
            try:
                elapsed = (self.clock() - started_at).total_seconds()
                if elapsed > budget.timeout_seconds:
                    raise CyberOSError(
                        ErrorCode.PLUGIN_LIMIT_EXCEEDED,
                        "Pipeline timeout budget exceeded.",
                    )
                if signal.is_cancelled:
                    cancelled = running.transition(TaskStatus.CANCELLED, at=self.clock())
                    report = PipelineExecutionReport(
                        definition.pipeline_id,
                        definition.pipeline_version,
                        cancelled,
                        PipelineStatus.CANCELLED,
                        tuple(receipts),
                        committed_assets,
                        committed_observations,
                    )
                    self._persist_terminal(
                        report,
                        started_at=started_at,
                        expected_version=running.version,
                    )
                    return report
                bundle = self.input_resolver.resolve(running, step)
                context = PipelineContext(
                    running,
                    authorization,
                    definition,
                    step,
                    PipelinePhase.EXECUTING,
                    budget,
                    bundle,
                )
                recon_input = ReconInput(
                    scope_id=running.scope_id,
                    target_id=running.target_id,
                    candidate=authorization.candidate,
                    parameters=step.parameters + bundle.to_parameters(),
                )
                input_size = len(
                    json.dumps(
                        recon_input.to_payload(), sort_keys=True, separators=(",", ":")
                    ).encode("utf-8")
                )
                if input_size > budget.remaining_payload_bytes:
                    raise CyberOSError(
                        ErrorCode.PLUGIN_LIMIT_EXCEEDED,
                        "Pipeline input exceeds the remaining payload budget.",
                    )
                result = self.host.invoke_running(
                    step.plugin_id,
                    task=context.task,
                    authorization=context.authorization,
                    input=recon_input,
                    now=self.clock(),
                )
                if signal.is_cancelled:
                    cancelled = running.transition(TaskStatus.CANCELLED, at=self.clock())
                    report = PipelineExecutionReport(
                        definition.pipeline_id,
                        definition.pipeline_version,
                        cancelled,
                        PipelineStatus.CANCELLED,
                        tuple(receipts),
                        committed_assets,
                        committed_observations,
                    )
                    self._persist_terminal(
                        report,
                        started_at=started_at,
                        expected_version=running.version,
                    )
                    return report
                step_limits = budget.limits_for_step()
                result.validate_within(step_limits)
                if result.status is not ReconStatus.SUCCESS:
                    raise CyberOSError(
                        ErrorCode.PLUGIN_EXECUTION_FAILED,
                        "Plugin returned a controlled failure result.",
                    )
                budget = budget.reserve(result)
                ingestion = self.ingestion_service.ingest(
                    task=running,
                    authorization=authorization,
                    result=result,
                    effective_limits=step_limits,
                    observed_at=self.clock(),
                )
                receipts.append(
                    StepReceipt(
                        step.step_id,
                        step.plugin_id,
                        "committed",
                        ingestion.inserted_assets,
                        ingestion.inserted_observations,
                    )
                )
                committed_assets += ingestion.inserted_assets
                committed_observations += ingestion.inserted_observations
            except CyberOSError as error:
                failed = running.transition(TaskStatus.FAILED, at=self.clock())
                report = PipelineExecutionReport(
                    definition.pipeline_id,
                    definition.pipeline_version,
                    failed,
                    PipelineStatus.FAILED,
                    tuple(receipts),
                    committed_assets,
                    committed_observations,
                    PipelineFailure(error.code.value, "Pipeline step failed safely.", step.step_id),
                    error.code is ErrorCode.PLUGIN_LIMIT_EXCEEDED
                    and (self.clock() - started_at).total_seconds() > budget.timeout_seconds,
                )
                self._persist_terminal(
                    report,
                    started_at=started_at,
                    expected_version=running.version,
                )
                return report
            except Exception:
                failed = running.transition(TaskStatus.FAILED, at=self.clock())
                report = PipelineExecutionReport(
                    definition.pipeline_id,
                    definition.pipeline_version,
                    failed,
                    PipelineStatus.FAILED,
                    tuple(receipts),
                    committed_assets,
                    committed_observations,
                    PipelineFailure(
                        ErrorCode.INVALID_INPUT.value, "Pipeline step failed safely.", step.step_id
                    ),
                )
                self._persist_terminal(
                    report,
                    started_at=started_at,
                    expected_version=running.version,
                )
                return report

        completed = running.transition(TaskStatus.COMPLETED, at=self.clock())
        report = PipelineExecutionReport(
            definition.pipeline_id,
            definition.pipeline_version,
            completed,
            PipelineStatus.COMPLETED,
            tuple(receipts),
            committed_assets,
            committed_observations,
        )
        self._persist_terminal(
            report,
            started_at=started_at,
            expected_version=running.version,
        )
        return report

    def _validate_start(
        self,
        task: Task,
        authorization: ExecutionAuthorization,
        definition: PipelineDefinition,
    ) -> None:
        if task.status is not TaskStatus.PENDING:
            raise CyberOSError(
                ErrorCode.TASK_INVALID_TRANSITION, "Pipeline requires a pending Task."
            )
        if (
            task.scope_id != authorization.scope_id
            or task.target_id != authorization.matched_target_id
        ):
            raise CyberOSError(
                ErrorCode.PLUGIN_AUTHORIZATION_INVALID, "Pipeline authorization is not Task-bound."
            )
        if authorization.matching_rule is not TargetRule.INCLUDE:
            raise CyberOSError(
                ErrorCode.PLUGIN_AUTHORIZATION_INVALID,
                "Pipeline requires Include authorization.",
            )
        if authorization.expires_at is not None and authorization.expires_at <= self.clock():
            raise CyberOSError(
                ErrorCode.PLUGIN_AUTHORIZATION_INVALID, "Pipeline authorization is expired."
            )
        for step in definition.steps:
            manifest = self.host.get_manifest(step.plugin_id)
            if not set(step.required_capabilities).issubset(manifest.capabilities):
                raise CyberOSError(
                    ErrorCode.PLUGIN_CAPABILITY_DENIED,
                    "Pipeline step requires capabilities not declared by its Plugin.",
                )

    def _persist_task(self, task: Task, *, expected_version: int) -> None:
        with SQLiteUnitOfWork(self.factory) as unit:
            repository = SQLiteTaskRepository(unit)
            repository.update_status_and_result(
                TaskRecord(task=task, result=None), expected_version=expected_version
            )
            unit.commit()

    def _persist_terminal(
        self,
        report: PipelineExecutionReport,
        *,
        started_at: datetime,
        expected_version: int,
    ) -> None:
        from cyberos.application.recon_task_result import ReconTaskResultAdapter

        result = ReconTaskResultAdapter.from_pipeline_report(
            report,
            started_at=started_at,
            finished_at=self.clock(),
        )
        with SQLiteUnitOfWork(self.factory) as unit:
            repository = SQLiteTaskRepository(unit)
            repository.update_status_and_result(
                TaskRecord(task=report.task, result=result),
                expected_version=expected_version,
            )
            unit.commit()
