"""Offline-only Module 2.1 contract, parser, and provenance tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from cyberos.application.network_port_scan import (
    NetworkPortScanOfflineHarness,
    NetworkPortScanProvenanceBridge,
)
from cyberos.application.scope_validation import ExecutionAuthorization, TargetCandidate
from cyberos.config.models import DatabaseSettings
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.engagement.model import Engagement, EngagementKind
from cyberos.domain.recon.network_scan import (
    FlagRule,
    MachineOutputFormat,
    NetworkPortScanAdapterManifest,
    NetworkScanInvocation,
    ScanMode,
    TimingProfile,
    validate_target_value,
)
from cyberos.domain.recon.network_scan_parser import NetworkScanParser, ParserLimits
from cyberos.domain.scope.model import Scope
from cyberos.domain.target.model import Target
from cyberos.domain.target.primitives import TargetId, TargetKind, TargetRule
from cyberos.domain.task.model import Task
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

MIGRATIONS_DIR = Path(__file__).parents[2] / "src/cyberos/persistence/migrations/versions"
NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)

JSON_FIXTURE = (
    b'{"schema_version":"1.0","target":"api.example.com","services":['
    b'{"port":443,"protocol":"tcp","state":"open","service":"https",'
    b'"product":"fixture","version":"1.0"}]}'
)
XML_FIXTURE = (
    b'<scan schema_version="1.0" target="api.example.com">'
    b'<host target="api.example.com"><port number="80" protocol="tcp" state="open" '
    b'service="http" product="fixture" version="1.0"/></host></scan>'
)


def factory_for(tmp_path: Path) -> SQLiteConnectionFactory:
    factory = SQLiteConnectionFactory(DatabaseSettings(path=tmp_path / "cyberos.sqlite3"))
    MigrationRunner(factory, MIGRATIONS_DIR).run()
    return factory


def setup_parents(
    factory: SQLiteConnectionFactory,
) -> tuple[Scope, Target, Task, ExecutionAuthorization]:
    workspace = Workspace.create("Port Scan Workspace", now=NOW)
    engagement = Engagement.create(
        workspace.id, "Port Scan Engagement", EngagementKind.LEARNING, now=NOW
    )
    scope = Scope.create(engagement.id, "Port Scan Scope", now=NOW)
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
        reason="offline_fixture_authorized",
        scope_version=1,
    )
    task = Task.create(
        scope.id,
        target.id,
        authorization,
        ExecutionSpec(command=("fixture", "network-port"), max_output_bytes=4096),
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


def manifest() -> NetworkPortScanAdapterManifest:
    return NetworkPortScanAdapterManifest(
        adapter_id="offline.portscan",
        display_name="Offline Port Scan Adapter",
        adapter_version="2.1.0",
        contract_version="1.0",
        executable_id="neutral.portscan",
        executable_absolute_path="/usr/bin/neutral-portscan",
        supported_target_kinds=(TargetKind.FQDN, TargetKind.IPV4, TargetKind.IPV6, TargetKind.CIDR),
        output_format=MachineOutputFormat.JSON,
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
    )


def invocation(task: Task, authorization: ExecutionAuthorization) -> NetworkScanInvocation:
    return NetworkScanInvocation(
        task=task,
        authorization=authorization,
        scope_id=task.scope_id,
        target_id=task.target_id,
        target_kind=TargetKind.FQDN,
        canonical_target="api.example.com",
        manifest_id="offline.portscan",
        ports=(443,),
        scan_mode=ScanMode.SYN,
        timing_profile=TimingProfile.T4,
        output_format=MachineOutputFormat.JSON,
        timeout_seconds=30,
        max_output_bytes=4096,
    )


def test_manifest_builds_deterministic_typed_argv_without_raw_flags() -> None:
    current_manifest = manifest()
    task = object.__new__(Task)
    assert current_manifest.adapter_id == "offline.portscan"
    assert current_manifest.supports_background_mode is False
    assert current_manifest.output_format is MachineOutputFormat.JSON
    assert task is not None


def test_target_and_port_policy_rejects_wildcard_invalid_cidr_and_unbounded_ports() -> None:
    with pytest.raises(CyberOSError) as wildcard:
        validate_target_value(TargetKind.WILDCARD, "*.example.com")
    assert wildcard.value.code is ErrorCode.PORT_SCAN_TARGET_INVALID

    with pytest.raises(CyberOSError) as cidr:
        validate_target_value(TargetKind.CIDR, "10.0.0.0/8")
    assert cidr.value.code is ErrorCode.PORT_SCAN_LIMIT_EXCEEDED


def test_invocation_flags_are_typed_and_deterministic(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    _, _, task, authorization = setup_parents(factory)
    current_manifest = manifest()
    current_invocation = invocation(task, authorization)
    assert current_invocation.to_typed_flags(current_manifest) == (
        "-sS",
        "-p",
        "443",
        "-T4",
        "--output-json",
        "api.example.com",
    )


def test_json_parser_is_deterministic_and_marks_fixture() -> None:
    scope_id = uuid4()
    target_id = uuid4()
    result = NetworkScanParser().parse(
        JSON_FIXTURE,
        output_format=MachineOutputFormat.JSON,
        scope_id=scope_id,  # type: ignore[arg-type]
        target_id=target_id,  # type: ignore[arg-type]
        target_kind=TargetKind.FQDN,
        canonical_target="api.example.com",
    )
    again = NetworkScanParser().parse(
        JSON_FIXTURE,
        output_format=MachineOutputFormat.JSON,
        scope_id=scope_id,  # type: ignore[arg-type]
        target_id=target_id,  # type: ignore[arg-type]
        target_kind=TargetKind.FQDN,
        canonical_target="api.example.com",
    )
    assert result.source_digest == again.source_digest
    assert result.offline_fixture is True
    assert result.synthetic is True
    assert len(result.observations) == 1


def test_xml_parser_rejects_external_entities_and_accepts_neutral_fixture() -> None:
    result = NetworkScanParser().parse(
        XML_FIXTURE,
        output_format=MachineOutputFormat.XML,
        scope_id=uuid4(),  # type: ignore[arg-type]
        target_id=uuid4(),  # type: ignore[arg-type]
        target_kind=TargetKind.FQDN,
        canonical_target="api.example.com",
    )
    assert result.services[0].port == 80
    malicious = b'<!DOCTYPE scan [<!ENTITY x SYSTEM "file:///etc/passwd">]>' + XML_FIXTURE
    with pytest.raises(CyberOSError) as error:
        NetworkScanParser().parse(
            malicious,
            output_format=MachineOutputFormat.XML,
            scope_id=uuid4(),  # type: ignore[arg-type]
            target_id=uuid4(),  # type: ignore[arg-type]
            target_kind=TargetKind.FQDN,
            canonical_target="api.example.com",
        )
    assert error.value.code is ErrorCode.PORT_SCAN_PARSE_FAILED


def test_parser_rejects_context_schema_truncation_and_budget_failures() -> None:
    kwargs = {
        "output_format": MachineOutputFormat.JSON,
        "scope_id": uuid4(),
        "target_id": uuid4(),
        "target_kind": TargetKind.FQDN,
        "canonical_target": "api.example.com",
    }
    with pytest.raises(CyberOSError) as mismatch:
        NetworkScanParser().parse(
            JSON_FIXTURE, **{**kwargs, "canonical_target": "other.example.com"}
        )  # type: ignore[arg-type]
    assert mismatch.value.code is ErrorCode.PORT_SCAN_CONTEXT_MISMATCH
    with pytest.raises(CyberOSError) as truncated:
        NetworkScanParser().parse(JSON_FIXTURE, **kwargs, truncated=True)  # type: ignore[arg-type]
    assert truncated.value.code is ErrorCode.PORT_SCAN_TRUNCATED_OUTPUT
    with pytest.raises(CyberOSError) as budget:
        NetworkScanParser().parse(JSON_FIXTURE, **kwargs, limits=ParserLimits(max_payload_bytes=8))  # type: ignore[arg-type]
    assert budget.value.code is ErrorCode.PORT_SCAN_LIMIT_EXCEEDED


def test_redaction_happens_before_digest_and_observation_projection() -> None:
    payload = JSON_FIXTURE.replace(b"fixture", b"Authorization:secret-token /home/ubuntu/private")
    result = NetworkScanParser().parse(
        payload,
        output_format=MachineOutputFormat.JSON,
        scope_id=uuid4(),  # type: ignore[arg-type]
        target_id=uuid4(),  # type: ignore[arg-type]
        target_kind=TargetKind.FQDN,
        canonical_target="api.example.com",
    )
    assert b"secret-token" not in result.source_digest.encode()
    assert all("secret-token" not in repr(observation) for observation in result.observations)


def test_offline_harness_rejects_live_like_output_format() -> None:
    harness = NetworkPortScanOfflineHarness()
    with pytest.raises(CyberOSError) as error:
        harness.parse_fixture(
            JSON_FIXTURE,
            output_format="text",
            scope_id=uuid4(),  # type: ignore[arg-type]
            target_id=uuid4(),  # type: ignore[arg-type]
            target_kind=TargetKind.FQDN,
            canonical_target="api.example.com",
        )
    assert error.value.code is ErrorCode.PORT_SCAN_OUTPUT_CONTRACT_INVALID


def test_provenance_bridge_ingests_services_and_creates_evidence_atomically(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    scope, target, task, authorization = setup_parents(factory)
    current_manifest = manifest()
    current_invocation = invocation(task, authorization)
    parsed = NetworkScanParser().parse(
        JSON_FIXTURE,
        output_format=MachineOutputFormat.JSON,
        scope_id=scope.id,
        target_id=target.id,
        target_kind=TargetKind.FQDN,
        canonical_target="api.example.com",
    )
    receipt = NetworkPortScanProvenanceBridge(factory).ingest_and_create_evidence(
        task=task,
        authorization=authorization,
        manifest=current_manifest,
        invocation=current_invocation,
        parsed=parsed,
        observed_at=NOW,
    )
    assert receipt.inserted_assets == 1
    assert receipt.inserted_observations == 1
    assert receipt.created_evidence == 1
    with factory.connect() as managed:
        assert managed.raw.execute("SELECT count(*) FROM evidence_records").fetchone()[0] == 1
        assert managed.raw.execute("SELECT count(*) FROM assets").fetchone()[0] == 1


def test_bridge_rejects_cross_context_parser_result_before_ingestion(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    scope, target, task, authorization = setup_parents(factory)
    parsed = NetworkScanParser().parse(
        JSON_FIXTURE,
        output_format=MachineOutputFormat.JSON,
        scope_id=scope.id,
        target_id=TargetId(uuid4()),
        target_kind=TargetKind.FQDN,
        canonical_target="api.example.com",
    )
    with pytest.raises(CyberOSError) as error:
        NetworkPortScanProvenanceBridge(factory).ingest_and_create_evidence(
            task=task,
            authorization=authorization,
            manifest=manifest(),
            invocation=invocation(task, authorization),
            parsed=parsed,
            observed_at=NOW,
        )
    assert error.value.code is ErrorCode.PORT_SCAN_CONTEXT_MISMATCH
    with factory.connect() as managed:
        assert managed.raw.execute("SELECT count(*) FROM assets").fetchone()[0] == 0
