"""
Module 2.1.g application boundary for the approved localhost Nmap workflow.

This service is the only supported orchestration path for the localhost
adapter. It creates a target-bound pending Task, validates the approved
binary/manifest and localhost policy, delegates process execution to
LiveSubprocessAdapter, parses only redacted bounded XML, then hands accepted
observations to the existing Recon/Evidence bridge. It never widens scope,
chooses a target implicitly, retries, or stores raw output.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, cast

from cyberos.application.network_port_scan import (
    NetworkPortScanProvenanceBridge,
)
from cyberos.application.scope_validation import ScopeValidationService, TargetCandidate
from cyberos.core.context import OperationContext
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.result import OperationResult
from cyberos.core.time import utc_now
from cyberos.domain.recon.network_scan import (
    FlagRule,
    MachineOutputFormat,
    NetworkPortScanAdapterManifest,
    NetworkScanInvocation,
    NetworkScanLimits,
    ScanMode,
    TimingProfile,
)
from cyberos.domain.target.model import Target
from cyberos.domain.target.primitives import TargetId, TargetKind, TargetStatus
from cyberos.domain.task.model import Task
from cyberos.domain.task.primitives import TaskId, TaskStatus
from cyberos.domain.task.record import TaskRecord
from cyberos.domain.task.result import ExecutionFailureReason, ExecutionResult
from cyberos.domain.task.spec import ExecutionSpec
from cyberos.execution.live_adapter import (
    BoundedProcessReceipt,
    CommandSandbox,
    LiveSubprocessAdapter,
)
from cyberos.execution.nmap_adapter import (
    NmapLocalhostLabPolicy,
    NmapLocalhostManifest,
    VerifiedBinaryIdentity,
)
from cyberos.execution.nmap_parser import NmapXmlParserBridge
from cyberos.execution.runner import SafeSubprocessRunner
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.target_repository import SQLiteTargetRepository
from cyberos.persistence.task_repository import SQLiteTaskRepository
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork

_LOCALHOST = "127.0.0.1"
_ALLOWED_PORTS = frozenset({22, 80, 443})
_DEFAULT_PORTS = (22, 80, 443)
_DEFAULT_TIMEOUT = 30
_DEFAULT_OUTPUT_BYTES = 262_144


class ProcessRunner(Protocol):
    async def run(
        self,
        spec: ExecutionSpec,
        *,
        environment: dict[str, str],
        cwd: str | None = None,
    ) -> ExecutionResult: ...


@dataclass(frozen=True, slots=True)
class NmapLocalhostScanReceipt:
    """Redacted, bounded result returned by the application boundary."""

    task_id: TaskId
    scope_id: object
    target_id: TargetId
    profile_id: str
    argv_digest: str
    exit_code: int | None
    timeout_exceeded: bool
    output_digest: str
    stdout_bytes: int
    stderr_bytes: int
    redaction_applied: bool
    parsed_services: int
    parsed_observations: int
    inserted_assets: int
    inserted_observations: int
    created_evidence: int
    task_status: str


class NmapLocalhostScanService:
    """Orchestrate one configured localhost Nmap task without target widening."""

    def __init__(
        self,
        factory: SQLiteConnectionFactory,
        *,
        runner: ProcessRunner | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.factory = factory
        self.runner = runner
        self.clock = clock

    def run(
        self,
        scope_id: object,
        target_id: TargetId,
        *,
        binary_path: str,
        expected_sha256: str,
        expected_version: str,
        ports: tuple[int, ...] = _DEFAULT_PORTS,
        context: OperationContext | None = None,
    ) -> OperationResult[NmapLocalhostScanReceipt]:
        started_at = time.perf_counter()
        operation_context = context or OperationContext()
        try:
            receipt = self._run(
                scope_id,
                target_id,
                binary_path=binary_path,
                expected_sha256=expected_sha256,
                expected_version=expected_version,
                ports=ports,
            )
            return OperationResult.success(receipt, operation_context, started_at)
        except CyberOSError as error:
            return OperationResult.failure(error, operation_context, started_at)

    def _run(
        self,
        scope_id: object,
        target_id: TargetId,
        *,
        binary_path: str,
        expected_sha256: str,
        expected_version: str,
        ports: tuple[int, ...],
    ) -> NmapLocalhostScanReceipt:
        if (
            not isinstance(ports, tuple)
            or not ports
            or any(port not in _ALLOWED_PORTS for port in ports)
        ):
            raise CyberOSError(
                ErrorCode.LAB_TARGET_REJECTED,
                "Only ports 22, 80, and 443 are allowed by the localhost profile.",
            )
        if len(ports) != len(set(ports)) or len(ports) > 3:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_LIMIT_EXCEEDED, "The localhost port budget was exceeded."
            )
        target = self._load_target(scope_id, target_id)
        if target.kind is not TargetKind.IPV4 or target.value != _LOCALHOST:
            raise CyberOSError(ErrorCode.LAB_TARGET_REJECTED, "Only 127.0.0.1 is allowed.")
        authorization = ScopeValidationService(self.factory).authorize_execution(
            target.scope_id,
            TargetCandidate(_LOCALHOST, TargetKind.IPV4),
            evaluated_at=self.clock(),
        )
        if authorization.matched_target_id != target_id:
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_UNAUTHORIZED, "Authorization target mismatch."
            )
        identity = VerifiedBinaryIdentity.verify(
            logical_id="nmap.binary.approved",
            absolute_path=binary_path,
            expected_sha256=expected_sha256,
            expected_version=expected_version,
        )
        manifest = NmapLocalhostManifest(
            adapter_id="nmap.tcp-connect.xml.localhost",
            scan_mode=ScanMode.CONNECT,
        )
        generic_manifest = NetworkPortScanAdapterManifest(
            adapter_id="nmap.tcp-connect.xml.localhost",
            display_name="Nmap localhost TCP Connect XML",
            adapter_version="2.1.0",
            contract_version="1.0",
            executable_id=manifest.executable_id,
            executable_absolute_path=identity.absolute_path,
            supported_target_kinds=(TargetKind.IPV4,),
            output_format=MachineOutputFormat.XML,
            output_contract_version="1.0",
            allowed_flags=(
                FlagRule.SCAN_MODE,
                FlagRule.PORT_SELECTION,
                FlagRule.TIMING,
                FlagRule.MACHINE_OUTPUT,
            ),
            required_flags=(
                FlagRule.SCAN_MODE,
                FlagRule.PORT_SELECTION,
                FlagRule.TIMING,
                FlagRule.MACHINE_OUTPUT,
            ),
            fixed_scan_mode=ScanMode.CONNECT,
            limits=NetworkScanLimits(
                max_ports=3,
                max_timeout_seconds=_DEFAULT_TIMEOUT,
                max_output_bytes=_DEFAULT_OUTPUT_BYTES,
            ),
        )
        command = (
            identity.absolute_path,
            "-sT",
            "-T3",
            "-n",
            "-Pn",
            "-p",
            ",".join(str(port) for port in sorted(ports)),
            "-oX",
            "-",
            _LOCALHOST,
        )
        task = Task.create(
            target.scope_id,
            target.id,
            authorization,
            ExecutionSpec(
                command=command,
                timeout_seconds=_DEFAULT_TIMEOUT,
                max_output_bytes=_DEFAULT_OUTPUT_BYTES,
            ),
            now=self.clock(),
        )
        with SQLiteUnitOfWork(self.factory) as unit:
            SQLiteTaskRepository(unit).add(TaskRecord(task))
            unit.commit()
        running_task = task.transition(TaskStatus.RUNNING, at=self.clock())
        with SQLiteUnitOfWork(self.factory) as unit:
            SQLiteTaskRepository(unit).update_status_and_result(
                TaskRecord(running_task), expected_version=task.version
            )
            unit.commit()
        invocation = NetworkScanInvocation(
            task=task,
            authorization=authorization,
            scope_id=task.scope_id,
            target_id=task.target_id,
            target_kind=TargetKind.IPV4,
            canonical_target=_LOCALHOST,
            manifest_id=generic_manifest.adapter_id,
            ports=ports,
            scan_mode=ScanMode.CONNECT,
            timing_profile=TimingProfile.T4,
            output_format=MachineOutputFormat.XML,
            timeout_seconds=_DEFAULT_TIMEOUT,
            max_output_bytes=_DEFAULT_OUTPUT_BYTES,
        )
        plan = NmapLocalhostLabPolicy().build_plan(
            invocation=invocation,
            identity=identity,
            manifest=manifest,
            authorization=authorization,
            now=self.clock(),
        )
        adapter = LiveSubprocessAdapter(
            sandbox=CommandSandbox(
                {manifest.executable_id: manifest.approved_executable(identity)}
            ),
            runner=cast(SafeSubprocessRunner | None, self.runner),
            clock=self.clock,
        )
        bounded = asyncio.run(adapter.run(plan.request))
        if bounded.timeout_exceeded:
            self._persist_failure(running_task, bounded, "SUBPROCESS_TIMEOUT")
            raise CyberOSError(ErrorCode.SUBPROCESS_TIMEOUT, "Nmap localhost execution timed out.")
        if bounded.stdout_truncated or bounded.stderr_truncated:
            self._persist_failure(running_task, bounded, "LIVE_ADAPTER_LIMIT_EXCEEDED")
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_LIMIT_EXCEEDED, "Nmap output exceeded the approved limit."
            )
        if bounded.exit_code != 0:
            self._persist_failure(running_task, bounded, "LIVE_ADAPTER_START_FAILED")
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_START_FAILED, "Nmap localhost execution failed."
            )
        try:
            parsed = NmapXmlParserBridge().parse(
                bounded.stdout,
                scope_id=task.scope_id,
                target_id=task.target_id,
                canonical_target=_LOCALHOST,
            )
            if not parsed.observations:
                saved = self._persist_completed(running_task, bounded)
                return NmapLocalhostScanReceipt(
                    task_id=saved.task.id,
                    scope_id=saved.task.scope_id,
                    target_id=saved.task.target_id,
                    profile_id=plan.profile_id,
                    argv_digest=plan.argv_digest,
                    exit_code=bounded.exit_code,
                    timeout_exceeded=bounded.timeout_exceeded,
                    output_digest=bounded.output_digest,
                    stdout_bytes=len(bounded.stdout),
                    stderr_bytes=len(bounded.stderr),
                    redaction_applied=bounded.redaction_applied,
                    parsed_services=len(parsed.services),
                    parsed_observations=0,
                    inserted_assets=0,
                    inserted_observations=0,
                    created_evidence=0,
                    task_status=saved.task.status.value,
                )
            provenance = NetworkPortScanProvenanceBridge(self.factory).ingest_and_create_evidence(
                task=task,
                authorization=authorization,
                manifest=generic_manifest,
                invocation=invocation,
                parsed=parsed,
                observed_at=self.clock(),
            )
        except CyberOSError as error:
            self._persist_failure(running_task, bounded, error.code.value)
            raise
        saved = self._persist_completed(running_task, bounded)
        return NmapLocalhostScanReceipt(
            task_id=saved.task.id,
            scope_id=saved.task.scope_id,
            target_id=saved.task.target_id,
            profile_id=plan.profile_id,
            argv_digest=plan.argv_digest,
            exit_code=bounded.exit_code,
            timeout_exceeded=bounded.timeout_exceeded,
            output_digest=bounded.output_digest,
            stdout_bytes=len(bounded.stdout),
            stderr_bytes=len(bounded.stderr),
            redaction_applied=bounded.redaction_applied,
            parsed_services=len(parsed.services),
            parsed_observations=len(parsed.observations),
            inserted_assets=provenance.inserted_assets,
            inserted_observations=provenance.inserted_observations,
            created_evidence=provenance.created_evidence,
            task_status=saved.task.status.value,
        )

    def _load_target(self, scope_id: object, target_id: TargetId) -> Target:
        with SQLiteUnitOfWork(self.factory) as unit:
            target = SQLiteTargetRepository(unit).get(target_id)
            unit.rollback()
        if target is None:
            raise CyberOSError(ErrorCode.TARGET_NOT_FOUND, "The Target does not exist.")
        if target.scope_id != scope_id:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_CONTEXT_MISMATCH, "Target is outside the requested Scope."
            )
        if target.status is not TargetStatus.ACTIVE:
            raise CyberOSError(ErrorCode.LAB_TARGET_REJECTED, "Archived Target cannot be scanned.")
        return target

    def _persist_failure(self, task: Task, bounded: BoundedProcessReceipt, message: str) -> None:
        result = self._execution_result(bounded, error_message=message)
        failed = task.transition(TaskStatus.FAILED, at=self.clock())
        with SQLiteUnitOfWork(self.factory) as unit:
            SQLiteTaskRepository(unit).update_status_and_result(
                TaskRecord(failed, result), expected_version=task.version
            )
            unit.commit()

    def _persist_completed(self, task: Task, bounded: BoundedProcessReceipt) -> TaskRecord:
        result = self._execution_result(bounded)
        completed = task.transition(TaskStatus.COMPLETED, at=self.clock())
        with SQLiteUnitOfWork(self.factory) as unit:
            saved = SQLiteTaskRepository(unit).update_status_and_result(
                TaskRecord(completed, result), expected_version=task.version
            )
            unit.commit()
        return saved

    @staticmethod
    def _execution_result(
        bounded: BoundedProcessReceipt, *, error_message: str | None = None
    ) -> ExecutionResult:
        failure_reason = (
            ExecutionFailureReason.TIMEOUT_EXCEEDED if bounded.timeout_exceeded else None
        )
        return ExecutionResult(
            exit_code=bounded.exit_code,
            stdout=bounded.stdout,
            stderr=bounded.stderr,
            truncated=bounded.stdout_truncated or bounded.stderr_truncated,
            duration_seconds=bounded.duration_ms / 1000,
            timeout_exceeded=bounded.timeout_exceeded,
            failure_reason=failure_reason,
            error_message=error_message,
        )
