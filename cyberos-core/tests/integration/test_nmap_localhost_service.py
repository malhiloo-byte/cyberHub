from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from cyberos.application.nmap_localhost import NmapLocalhostScanService
from cyberos.cli.app import app
from cyberos.config.models import DatabaseSettings
from cyberos.domain.engagement.model import Engagement, EngagementKind
from cyberos.domain.scope.model import Scope
from cyberos.domain.target.model import Target
from cyberos.domain.target.primitives import TargetKind, TargetRule
from cyberos.domain.task.result import ExecutionResult
from cyberos.domain.workspace.model import Workspace
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.engagement_repository import SQLiteEngagementRepository
from cyberos.persistence.migrations.runner import MigrationRunner
from cyberos.persistence.scope_repository import SQLiteScopeRepository
from cyberos.persistence.target_repository import SQLiteTargetRepository
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork
from cyberos.persistence.workspace_repository import SQLiteWorkspaceRepository

ROOT = Path(__file__).parents[2]
MIGRATIONS = ROOT / "src/cyberos/persistence/migrations/versions"
NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
NMAP_XML = (
    b'<?xml version="1.0"?><!DOCTYPE nmaprun SYSTEM "nmap.dtd">'
    b'<nmaprun scanner="nmap" scanner-version="7.94">'
    b'<host><address addr="127.0.0.1" addrtype="ipv4"/><ports>'
    b'<port protocol="tcp" portid="80"><state state="open"/>'
    b'<service name="http" product="fixture" version="1.0"/></port>'
    b"</ports></host></nmaprun>"
)


class FixtureRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    async def run(
        self, spec: Any, *, environment: dict[str, str], cwd: Any = None
    ) -> ExecutionResult:
        self.calls.append(spec.command)
        return ExecutionResult(
            exit_code=0,
            stdout=NMAP_XML,
            stderr=b"password=fixture-secret /home/ubuntu/private\n",
            truncated=False,
            duration_seconds=0.01,
            timeout_exceeded=False,
        )


def make_authorized_localhost(
    tmp_path: Path,
) -> tuple[SQLiteConnectionFactory, Scope, Target]:
    factory = SQLiteConnectionFactory(DatabaseSettings(path=tmp_path / "cyberos.sqlite3"))
    MigrationRunner(factory, MIGRATIONS).run()
    workspace = Workspace.create("Nmap g Workspace", now=NOW)
    engagement = Engagement.create(
        workspace.id, "Nmap g Engagement", EngagementKind.LEARNING, now=NOW
    )
    scope = Scope.create(engagement.id, "Nmap g Scope", now=NOW)
    target = Target.create(scope.id, TargetRule.INCLUDE, TargetKind.IPV4, "127.0.0.1", now=NOW)
    with SQLiteUnitOfWork(factory) as unit:
        SQLiteWorkspaceRepository(unit).add(workspace)
        SQLiteEngagementRepository(unit).add(engagement)
        SQLiteScopeRepository(unit).add(scope)
        SQLiteTargetRepository(unit).add(target)
        unit.commit()
    validated = scope.mark_validated(at=NOW + timedelta(seconds=1))
    authorized = validated.authorize(
        "explicit-localhost-lab",
        at=NOW + timedelta(seconds=2),
        expires_at=NOW + timedelta(hours=1),
    )
    with SQLiteUnitOfWork(factory) as unit:
        SQLiteScopeRepository(unit).update(validated, expected_version=scope.version)
        SQLiteScopeRepository(unit).update(authorized, expected_version=validated.version)
        unit.commit()
    return factory, authorized, target


def test_service_wires_injected_runner_to_provenance(tmp_path: Path) -> None:
    factory, scope, target = make_authorized_localhost(tmp_path)
    nmap = tmp_path / "nmap"
    nmap.write_bytes(b"neutral nmap binary fixture")
    os.chmod(nmap, 0o700)
    digest = hashlib.sha256(nmap.read_bytes()).hexdigest()
    runner = FixtureRunner()

    result = NmapLocalhostScanService(factory, runner=runner, clock=lambda: NOW).run(
        scope.id,
        target.id,
        binary_path=str(nmap),
        expected_sha256=digest,
        expected_version="7.94",
        ports=(80,),
    )

    assert result.ok is True
    assert result.data is not None
    assert result.data.profile_id == "lab.localhost.tcp-connect.v1"
    assert result.data.parsed_observations == 1
    assert result.data.created_evidence == 1
    assert runner.calls == [
        (str(nmap), "-sT", "-T3", "-n", "-Pn", "-p", "80", "-oX", "-", "127.0.0.1")
    ]


def test_cli_exposes_localhost_command_without_live_execution() -> None:
    result = CliRunner().invoke(app, ["recon", "--help"])

    assert result.exit_code == 0
    assert "nmap-localhost" in result.stdout


def test_cli_rejects_port_outside_localhost_allowlist() -> None:
    result = CliRunner().invoke(
        app,
        [
            "recon",
            "nmap-localhost",
            "00000000-0000-4000-8000-000000000000",
            "00000000-0000-4000-8000-000000000001",
            "--nmap-sha256",
            "a" * 64,
            "--nmap-version",
            "7.94",
            "--ports",
            "25",
        ],
    )

    assert result.exit_code != 0
    assert "Only ports 22, 80, and 443" in result.stdout
