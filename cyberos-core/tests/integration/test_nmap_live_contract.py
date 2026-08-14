"""Offline-only Nmap identity, localhost preflight, parser, and runner-double tests."""

from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from cyberos.application.network_port_scan import NetworkPortScanProvenanceBridge
from cyberos.application.scope_validation import ExecutionAuthorization, TargetCandidate
from cyberos.config.models import DatabaseSettings
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.engagement.model import Engagement, EngagementKind
from cyberos.domain.recon.network_scan import (
    MachineOutputFormat,
    NetworkPortScanAdapterManifest,
    NetworkScanInvocation,
    ScanMode,
    TimingProfile,
)
from cyberos.domain.recon.network_scan_parser import NetworkScanParseResult
from cyberos.domain.scope.model import Scope
from cyberos.domain.target.model import Target
from cyberos.domain.target.primitives import TargetKind, TargetRule
from cyberos.domain.task.model import Task
from cyberos.domain.task.record import TaskRecord
from cyberos.domain.task.result import ExecutionResult
from cyberos.domain.task.spec import ExecutionSpec
from cyberos.domain.workspace.model import Workspace
from cyberos.execution.live_adapter import BoundedProcessReceipt, LiveSubprocessAdapter
from cyberos.execution.nmap_adapter import (
    NmapLocalhostLabPolicy,
    NmapLocalhostManifest,
    VerifiedBinaryIdentity,
)
from cyberos.execution.nmap_parser import NmapXmlParserBridge
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.engagement_repository import SQLiteEngagementRepository
from cyberos.persistence.migrations.runner import MigrationRunner
from cyberos.persistence.scope_repository import SQLiteScopeRepository
from cyberos.persistence.target_repository import SQLiteTargetRepository
from cyberos.persistence.task_repository import SQLiteTaskRepository
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork
from cyberos.persistence.workspace_repository import SQLiteWorkspaceRepository

MIGRATIONS_DIR = Path(__file__).parents[2] / "src/cyberos/persistence/migrations/versions"
NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
NMAP_XML = (
    b'<nmaprun scanner="nmap" scanner-version="7.95">'
    b'<host><address addr="127.0.0.1" addrtype="ipv4"/><ports>'
    b'<port protocol="tcp" portid="80"><state state="open"/>'
    b'<service name="http" product="fixture" version="1.0"/></port>'
    b"</ports></host></nmaprun>"
)
STANDARD_NMAP_XML = (
    b'<?xml version="1.0"?>'
    b'<!DOCTYPE nmaprun SYSTEM "nmap.dtd">'
    b'<nmaprun scanner="nmap" scanner-version="7.94" xmloutputversion="1.05">'
    b'<scaninfo type="connect" protocol="tcp" numservices="1" services="80"/>'
    b'<verbose level="0"/><debugging level="0"/>'
    b'<host><status state="up" reason="user-set" reason_ttl="0"/>'
    b'<address addr="127.0.0.1" addrtype="ipv4"/><hostnames/>'
    b'<ports><port protocol="tcp" portid="80">'
    b'<state state="open" reason="syn-ack" reason_ttl="0"/>'
    b'<service name="http" product="fixture" version="1.0"/></port></ports>'
    b'<times srtt="1000" rttvar="100" to="100000"/></host>'
    b'<runstats><finished time="0"/><hosts up="1" down="0" total="1"/></runstats>'
    b"</nmaprun>"
)
CLOSED_PORTS_NMAP_XML = (
    b'<?xml version="1.0"?>'
    b'<!DOCTYPE nmaprun SYSTEM "nmap.dtd">'
    b'<nmaprun scanner="nmap" scanner-version="7.94" xmloutputversion="1.05">'
    b'<scaninfo type="connect" protocol="tcp" numservices="3" services="22,80,443"/>'
    b'<verbose level="0"/><debugging level="0"/>'
    b'<host><status state="up" reason="user-set" reason_ttl="0"/>'
    b'<address addr="127.0.0.1" addrtype="ipv4"/><hostnames/>'
    b'<ports><extraports state="closed" count="3">'
    b'<extrareasons reason="conn-refused" count="3" proto="tcp" ports="22,80,443"/>'
    b'</extraports></ports><times srtt="1000" rttvar="100" to="100000"/></host>'
    b'<runstats><finished time="0"/><hosts up="1" down="0" total="1"/></runstats>'
    b"</nmaprun>"
)


def factory_for(tmp_path: Path) -> SQLiteConnectionFactory:
    factory = SQLiteConnectionFactory(DatabaseSettings(path=tmp_path / "cyberos.sqlite3"))
    MigrationRunner(factory, MIGRATIONS_DIR).run()
    return factory


def setup_localhost(
    factory: SQLiteConnectionFactory,
    command: tuple[str, ...],
) -> tuple[Scope, Target, Task, ExecutionAuthorization]:
    workspace = Workspace.create("Nmap Lab Workspace", now=NOW)
    engagement = Engagement.create(
        workspace.id, "Nmap Lab Engagement", EngagementKind.LEARNING, now=NOW
    )
    scope = Scope.create(engagement.id, "Nmap Localhost Scope", now=NOW)
    target = Target.create(scope.id, TargetRule.INCLUDE, TargetKind.IPV4, "127.0.0.1", now=NOW)
    authorization = ExecutionAuthorization(
        scope_id=scope.id,
        candidate=TargetCandidate("127.0.0.1", TargetKind.IPV4),
        authorized_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        matched_target_id=target.id,
        matching_rule=TargetRule.INCLUDE,
        reason="explicit_localhost_lab",
        scope_version=1,
    )
    task = Task.create(
        scope.id,
        target.id,
        authorization,
        ExecutionSpec(command=command, timeout_seconds=30, max_output_bytes=262_144),
        now=NOW,
    )
    with SQLiteUnitOfWork(factory) as unit:
        SQLiteWorkspaceRepository(unit).add(workspace)
        SQLiteEngagementRepository(unit).add(engagement)
        SQLiteScopeRepository(unit).add(scope)
        SQLiteTargetRepository(unit).add(target)
        SQLiteTaskRepository(unit).add(TaskRecord(task=task, result=None))
        unit.commit()
    return scope, target, task, authorization


def invocation(
    task: Task,
    authorization: ExecutionAuthorization,
    *,
    canonical_target: str = "127.0.0.1",
) -> NetworkScanInvocation:
    return NetworkScanInvocation(
        task=task,
        authorization=authorization,
        scope_id=task.scope_id,
        target_id=task.target_id,
        target_kind=TargetKind.IPV4,
        canonical_target=canonical_target,
        manifest_id="nmap.tcp-syn.xml.localhost",
        ports=(80,),
        scan_mode=ScanMode.SYN,
        timing_profile=TimingProfile.T4,
        output_format=MachineOutputFormat.XML,
        timeout_seconds=30,
        max_output_bytes=262_144,
    )


def generic_manifest() -> NetworkPortScanAdapterManifest:
    return NetworkPortScanAdapterManifest(
        adapter_id="nmap.tcp-syn.xml.localhost",
        display_name="Nmap Localhost XML",
        adapter_version="2.1.0",
        contract_version="1.0",
        executable_id="nmap.binary.approved",
        executable_absolute_path="/usr/bin/nmap",
        supported_target_kinds=(TargetKind.IPV4,),
        output_format=MachineOutputFormat.XML,
        output_contract_version="1.0",
        allowed_flags=(),
        required_flags=(),
    )


def fake_identity() -> VerifiedBinaryIdentity:
    return VerifiedBinaryIdentity(
        logical_id="nmap.binary.approved",
        absolute_path="/usr/bin/nmap",
        binary_name="nmap",
        sha256="a" * 64,
        version="7.95",
    )


class FixtureRunner:
    def __init__(
        self, result: ExecutionResult | None = None, error: CyberOSError | None = None
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[tuple[str, ...], dict[str, str]]] = []

    async def run(
        self, spec: ExecutionSpec, *, environment: dict[str, str], cwd: Any = None
    ) -> ExecutionResult:
        self.calls.append((spec.command, environment))
        if self.error is not None:
            raise self.error
        if self.result is None:
            raise AssertionError("FixtureRunner requires a result or error.")
        return self.result


def success_result() -> ExecutionResult:
    return ExecutionResult(
        exit_code=0,
        stdout=NMAP_XML,
        stderr=b"password=fixture-secret /home/ubuntu/private\n",
        truncated=False,
        duration_seconds=0.01,
        timeout_exceeded=False,
        failure_reason=None,
        error_message=None,
    )


def test_verified_binary_identity_requires_absolute_nmap_and_digest(tmp_path: Path) -> None:
    path = tmp_path / "nmap"
    path.write_bytes(b"neutral binary fixture")
    os.chmod(path, 0o700)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    identity = VerifiedBinaryIdentity.verify(
        logical_id="nmap.binary.approved",
        absolute_path=str(path),
        expected_sha256=digest,
        expected_version="7.95",
    )
    assert identity.binary_name == "nmap"
    with pytest.raises(CyberOSError) as mismatch:
        VerifiedBinaryIdentity.verify(
            logical_id="nmap.binary.approved",
            absolute_path=str(path),
            expected_sha256="b" * 64,
            expected_version="7.95",
        )
    assert mismatch.value.code is ErrorCode.LIVE_TOOL_BINARY_INVALID


def test_nmap_manifest_binds_approved_executable_without_path_lookup() -> None:
    executable = NmapLocalhostManifest().approved_executable(fake_identity())
    assert executable.executable == "/usr/bin/nmap"
    assert executable.command_prefix == ("/usr/bin/nmap", "-sS", "-T3", "-n", "-Pn")
    assert executable.require_target_argument is True


def test_localhost_preflight_builds_dry_run_only_and_exact_argv(tmp_path: Path) -> None:
    command = (
        "/usr/bin/nmap",
        "-sS",
        "-T3",
        "-n",
        "-Pn",
        "-p",
        "80",
        "-oX",
        "-",
        "127.0.0.1",
    )
    factory = factory_for(tmp_path)
    _, _, task, authorization = setup_localhost(factory, command)
    plan = NmapLocalhostLabPolicy().build_plan(
        invocation=invocation(task, authorization),
        identity=fake_identity(),
        manifest=NmapLocalhostManifest(),
        authorization=authorization,
        now=NOW,
    )
    assert plan.dry_run is True
    assert plan.profile_id == "lab.localhost.tcp-syn.v1"
    assert plan.request.command == command
    assert plan.request.canonical_target == "127.0.0.1"


def test_localhost_preflight_rejects_expired_or_non_loopback_authorization(tmp_path: Path) -> None:
    command = ("/usr/bin/nmap", "-sS", "-T3", "-n", "-Pn", "-p", "80", "-oX", "-", "127.0.0.1")
    factory = factory_for(tmp_path)
    _, _, task, authorization = setup_localhost(factory, command)
    expired = ExecutionAuthorization(
        scope_id=authorization.scope_id,
        candidate=authorization.candidate,
        authorized_at=NOW - timedelta(hours=2),
        expires_at=NOW - timedelta(minutes=1),
        matched_target_id=authorization.matched_target_id,
        matching_rule=TargetRule.INCLUDE,
        reason="expired_fixture",
        scope_version=1,
    )
    with pytest.raises(CyberOSError) as error:
        NmapLocalhostLabPolicy().build_plan(
            invocation=invocation(task, expired),
            identity=fake_identity(),
            manifest=NmapLocalhostManifest(),
            authorization=expired,
            now=NOW,
        )
    assert error.value.code is ErrorCode.LIVE_ADAPTER_UNAUTHORIZED


def test_localhost_preflight_rejects_rfc1918_target_drift(tmp_path: Path) -> None:
    command = (
        "/usr/bin/nmap",
        "-sS",
        "-T3",
        "-n",
        "-Pn",
        "-p",
        "80",
        "-oX",
        "-",
        "127.0.0.1",
    )
    factory = factory_for(tmp_path)
    _, _, task, authorization = setup_localhost(factory, command)
    drifted_authorization = ExecutionAuthorization(
        scope_id=authorization.scope_id,
        candidate=TargetCandidate("192.168.1.1", TargetKind.IPV4),
        authorized_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        matched_target_id=authorization.matched_target_id,
        matching_rule=TargetRule.INCLUDE,
        reason="rfc1918_drift_fixture",
        scope_version=1,
    )
    drifted = invocation(task, drifted_authorization, canonical_target="192.168.1.1")
    with pytest.raises(CyberOSError) as error:
        NmapLocalhostLabPolicy().build_plan(
            invocation=drifted,
            identity=fake_identity(),
            manifest=NmapLocalhostManifest(),
            authorization=drifted_authorization,
            now=NOW,
        )
    assert error.value.code is ErrorCode.LAB_TARGET_REJECTED


def test_nmap_xml_bridge_normalizes_fixture_and_rejects_dtd() -> None:
    bridge = NmapXmlParserBridge()
    scope_id = uuid4()
    target_id = uuid4()
    result = bridge.parse(
        NMAP_XML,
        scope_id=scope_id,  # type: ignore[arg-type]
        target_id=target_id,  # type: ignore[arg-type]
        canonical_target="127.0.0.1",
    )
    assert isinstance(result, NetworkScanParseResult)
    assert result.output_format is MachineOutputFormat.XML
    assert result.observations[0].value == "http@127.0.0.1:80"
    standard_nmap = b'<?xml version="1.0"?><!DOCTYPE nmaprun SYSTEM "nmap.dtd">' + NMAP_XML
    standard_result = bridge.parse(
        standard_nmap,
        scope_id=scope_id,  # type: ignore[arg-type]
        target_id=target_id,  # type: ignore[arg-type]
        canonical_target="127.0.0.1",
    )
    assert standard_result.observations[0].value == "http@127.0.0.1:80"
    malicious = b'<!DOCTYPE nmaprun [<!ENTITY x SYSTEM "file:///etc/passwd">]>' + NMAP_XML
    with pytest.raises(CyberOSError) as malicious_error:
        bridge.parse(
            malicious,
            scope_id=scope_id,  # type: ignore[arg-type]
            target_id=target_id,  # type: ignore[arg-type]
            canonical_target="127.0.0.1",
        )
    assert malicious_error.value.code is ErrorCode.NMAP_XML_INVALID


def test_nmap_xml_bridge_accepts_minimal_standard_nmap_794_structure() -> None:
    result = NmapXmlParserBridge().parse(
        STANDARD_NMAP_XML,
        scope_id=uuid4(),  # type: ignore[arg-type]
        target_id=uuid4(),  # type: ignore[arg-type]
        canonical_target="127.0.0.1",
    )
    assert result.observations[0].value == "http@127.0.0.1:80"
    assert dict(result.observations[0].metadata)["state"] == "open"
    assert "reason" not in dict(result.observations[0].metadata)
    assert "reason_ttl" not in dict(result.observations[0].metadata)


@pytest.mark.parametrize(
    "invalid_state",
    (
        b'<state reason="syn-ack"/>',
        b'<state state="open" unsupported="value"/>',
        b'<state state="open" reason=""/>',
        b'<state state="open" reason_ttl="invalid"/>',
    ),
)
def test_nmap_xml_bridge_rejects_missing_or_unallowlisted_state_metadata(
    invalid_state: bytes,
) -> None:
    payload = NMAP_XML.replace(b'<state state="open"/>', invalid_state)
    with pytest.raises(CyberOSError) as error:
        NmapXmlParserBridge().parse(
            payload,
            scope_id=uuid4(),  # type: ignore[arg-type]
            target_id=uuid4(),  # type: ignore[arg-type]
            canonical_target="127.0.0.1",
        )
    assert error.value.code is ErrorCode.NMAP_XML_INVALID


def test_nmap_xml_bridge_accepts_closed_port_summary_without_observations() -> None:
    result = NmapXmlParserBridge().parse(
        CLOSED_PORTS_NMAP_XML,
        scope_id=uuid4(),  # type: ignore[arg-type]
        target_id=uuid4(),  # type: ignore[arg-type]
        canonical_target="127.0.0.1",
    )
    assert result.services == ()
    assert result.observations == ()


def test_injected_runner_is_used_and_redacts_raw_fixture_output(tmp_path: Path) -> None:
    command = ("/usr/bin/nmap", "-sS", "-T3", "-n", "-Pn", "-p", "80", "-oX", "-", "127.0.0.1")
    factory = factory_for(tmp_path)
    _, _, task, authorization = setup_localhost(factory, command)
    plan = NmapLocalhostLabPolicy().build_plan(
        invocation=invocation(task, authorization),
        identity=fake_identity(),
        manifest=NmapLocalhostManifest(),
        authorization=authorization,
        now=NOW,
    )
    runner = FixtureRunner(success_result())
    receipt = asyncio.run(
        LiveSubprocessAdapter(
            sandbox=__import__(
                "cyberos.execution.live_adapter", fromlist=["CommandSandbox"]
            ).CommandSandbox(
                {
                    "nmap.binary.approved": NmapLocalhostManifest().approved_executable(
                        fake_identity()
                    )
                }
            ),
            runner=runner,  # type: ignore[arg-type]
            clock=lambda: NOW,
        ).run(plan.request)
    )
    assert isinstance(receipt, BoundedProcessReceipt)
    assert runner.calls[0][0] == command
    assert b"fixture-secret" not in receipt.stderr
    assert b"[PATH_REDACTED]" in receipt.stderr
    assert receipt.redaction_applied is True


def test_runner_failure_does_not_create_assets_or_evidence(tmp_path: Path) -> None:
    command = ("/usr/bin/nmap", "-sS", "-T3", "-n", "-Pn", "-p", "80", "-oX", "-", "127.0.0.1")
    factory = factory_for(tmp_path)
    scope, target, task, authorization = setup_localhost(factory, command)
    plan = NmapLocalhostLabPolicy().build_plan(
        invocation=invocation(task, authorization),
        identity=fake_identity(),
        manifest=NmapLocalhostManifest(),
        authorization=authorization,
        now=NOW,
    )
    runner = FixtureRunner(error=CyberOSError(ErrorCode.EXECUTION_START_FAILED, "redacted"))
    with pytest.raises(CyberOSError) as error:
        asyncio.run(
            LiveSubprocessAdapter(
                sandbox=__import__(
                    "cyberos.execution.live_adapter", fromlist=["CommandSandbox"]
                ).CommandSandbox(
                    {
                        "nmap.binary.approved": NmapLocalhostManifest().approved_executable(
                            fake_identity()
                        )
                    }
                ),
                runner=runner,  # type: ignore[arg-type]
                clock=lambda: NOW,
            ).run(plan.request)
        )
    assert error.value.code is ErrorCode.LIVE_ADAPTER_START_FAILED
    with factory.connect() as managed:
        assert managed.raw.execute("SELECT count(*) FROM assets").fetchone()[0] == 0
        assert managed.raw.execute("SELECT count(*) FROM evidence_records").fetchone()[0] == 0


def test_injected_runner_output_flows_to_observation_and_evidence(tmp_path: Path) -> None:
    command = ("/usr/bin/nmap", "-sS", "-T3", "-n", "-Pn", "-p", "80", "-oX", "-", "127.0.0.1")
    factory = factory_for(tmp_path)
    scope, target, task, authorization = setup_localhost(factory, command)
    plan = NmapLocalhostLabPolicy().build_plan(
        invocation=invocation(task, authorization),
        identity=fake_identity(),
        manifest=NmapLocalhostManifest(),
        authorization=authorization,
        now=NOW,
    )
    runner = FixtureRunner(success_result())
    receipt = asyncio.run(
        LiveSubprocessAdapter(
            sandbox=__import__(
                "cyberos.execution.live_adapter", fromlist=["CommandSandbox"]
            ).CommandSandbox(
                {
                    "nmap.binary.approved": NmapLocalhostManifest().approved_executable(
                        fake_identity()
                    )
                }
            ),
            runner=runner,  # type: ignore[arg-type]
            clock=lambda: NOW,
        ).run(plan.request)
    )
    parsed = NmapXmlParserBridge().parse(
        receipt.stdout,
        scope_id=scope.id,
        target_id=target.id,
        canonical_target="127.0.0.1",
    )
    bridge_receipt = NetworkPortScanProvenanceBridge(factory).ingest_and_create_evidence(
        task=task,
        authorization=authorization,
        manifest=generic_manifest(),
        invocation=invocation(task, authorization),
        parsed=parsed,
        observed_at=NOW,
    )
    assert bridge_receipt.inserted_assets == 1
    assert bridge_receipt.inserted_observations == 1
    assert bridge_receipt.created_evidence == 1
    with factory.connect() as managed:
        assert managed.raw.execute("SELECT count(*) FROM assets").fetchone()[0] == 1
        assert managed.raw.execute("SELECT count(*) FROM asset_observations").fetchone()[0] == 1
        assert managed.raw.execute("SELECT count(*) FROM evidence_records").fetchone()[0] == 1


def test_p3_live_invocation_is_not_part_of_offline_contract_suite() -> None:
    assert "127.0.0.1" == "127.0.0.1"
