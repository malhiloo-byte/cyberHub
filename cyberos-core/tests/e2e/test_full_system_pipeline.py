"""Zero-state E2E audit for the complete Module 0 pipeline."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from typer.testing import CliRunner

from cyberos.application.scope_validation import (
    ExecutionAuthorization,
    ScopeValidationService,
    TargetCandidate,
)
from cyberos.cli.app import app
from cyberos.config.models import DatabaseSettings
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.ids import new_id
from cyberos.domain.engagement.model import Engagement
from cyberos.domain.scope.model import Scope
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.model import Target
from cyberos.domain.target.primitives import TargetId, TargetKind, TargetRule
from cyberos.domain.task.model import Task
from cyberos.domain.task.primitives import TaskId, TaskStatus
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
RUNNER = CliRunner()
NOW = datetime.now(UTC)


def config_file(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(
        "[database]\n"
        f'path = "{tmp_path / "cyberos.sqlite3"}"\n'
        "[runtime]\n"
        f'data_dir = "{tmp_path}"\n'
        f'log_dir = "{tmp_path}"\n',
        encoding="utf-8",
    )
    return path


def invoke(tmp_path: Path, args: list[str]):
    return RUNNER.invoke(app, [*args, "--file", str(config_file(tmp_path))])


def task_run_cli(
    tmp_path: Path,
    scope_id: str,
    target_id: str,
    value: str,
    *command: str,
):
    return RUNNER.invoke(
        app,
        [
            "task",
            "run",
            scope_id,
            target_id,
            "--kind",
            "fqdn",
            "--value",
            value,
            "--json",
            "--file",
            str(config_file(tmp_path)),
            "--",
            *command,
        ],
    )


def test_full_system_pipeline_zero_state_and_security_matrix(tmp_path: Path) -> None:
    database = tmp_path / "cyberos.sqlite3"
    factory = SQLiteConnectionFactory(DatabaseSettings(path=database))
    applied = MigrationRunner(factory, MIGRATIONS_DIR).run()
    assert [migration.version for migration in applied.applied] == [1, 2, 3, 4]
    with factory.connect() as managed:
        assert managed.raw.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert managed.raw.execute("PRAGMA foreign_key_check").fetchall() == []
        assert managed.health().schema_version == 4

    workspace = invoke(tmp_path, ["workspace", "create", "Zero State Workspace", "--json"])
    assert workspace.exit_code == 0
    workspace_id = json.loads(workspace.stdout)["data"]["id"]
    engagement = invoke(
        tmp_path,
        [
            "engagement",
            "create",
            workspace_id,
            "Zero State Engagement",
            "--kind",
            "learning",
            "--json",
        ],
    )
    assert engagement.exit_code == 0
    engagement_id = json.loads(engagement.stdout)["data"]["id"]
    scope = invoke(tmp_path, ["scope", "create", engagement_id, "Zero State Scope", "--json"])
    assert scope.exit_code == 0
    scope_id = json.loads(scope.stdout)["data"]["id"]

    target_specs = [
        ("include", "fqdn", "audit.example.com"),
        ("include", "wildcard", "*.lab.example.com"),
        ("include", "ipv4", "192.0.2.10"),
        ("include", "cidr", "198.51.100.0/24"),
        ("include", "url", "https://app.example.com:8443/path?x=1"),
        ("exclude", "fqdn", "blocked.example.com"),
    ]
    target_ids: dict[str, str] = {}
    for rule, kind, value in target_specs:
        added = invoke(
            tmp_path,
            [
                "target",
                "add",
                scope_id,
                "--rule",
                rule,
                "--kind",
                kind,
                "--value",
                value,
                "--json",
            ],
        )
        assert added.exit_code == 0
        target_ids[value] = json.loads(added.stdout)["data"]["id"]

    authorized = invoke(
        tmp_path,
        [
            "scope",
            "authorize",
            scope_id,
            "--authorization-reference",
            "zero-state-approval",
            "--expires-at",
            (NOW + timedelta(hours=1)).isoformat(),
            "--json",
        ],
    )
    assert authorized.exit_code == 0
    assert json.loads(authorized.stdout)["data"]["status"] == "authorized"

    matrix = ScopeValidationService(factory)
    candidates = [
        ("audit.example.com", TargetKind.FQDN),
        ("api.lab.example.com", TargetKind.FQDN),
        ("192.0.2.10", TargetKind.IPV4),
        ("198.51.100.25", TargetKind.IPV4),
        ("https://app.example.com:8443/path?x=1", TargetKind.URL),
    ]
    for raw_value, kind in candidates:
        result = matrix.evaluate_candidate(
            ScopeId_from_string(scope_id),
            TargetCandidate(raw_value, kind),
        )
        assert result.decision.value == "included"

    excluded_eval = matrix.evaluate_candidate(
        ScopeId_from_string(scope_id),
        TargetCandidate("blocked.example.com", TargetKind.FQDN),
    )
    assert excluded_eval.decision.value == "excluded"
    authorization = matrix.authorize_execution(
        ScopeId_from_string(scope_id),
        TargetCandidate("audit.example.com", TargetKind.FQDN),
    )
    assert authorization.matched_target_id == TargetId_from_string(target_ids["audit.example.com"])
    assert authorization.expires_at is not None

    command_payload = "; echo INJECTION && echo PIPE | echo REDIRECT"
    executed = task_run_cli(
        tmp_path,
        scope_id,
        target_ids["audit.example.com"],
        "audit.example.com",
        sys.executable,
        "-c",
        "import sys; print(sys.argv[1])",
        command_payload,
    )
    assert executed.exit_code == 0
    executed_payload = json.loads(executed.stdout)
    assert executed_payload["data"]["status"] == "completed"
    assert executed_payload["data"]["result"]["stdout"] == f"{command_payload}\n"
    task_id = executed_payload["data"]["id"]

    listed = invoke(tmp_path, ["task", "list", "--scope-id", scope_id, "--json"])
    assert listed.exit_code == 0
    assert len(json.loads(listed.stdout)["data"]) == 1
    shown = invoke(tmp_path, ["task", "show", task_id, "--json"])
    assert shown.exit_code == 0
    assert json.loads(shown.stdout)["data"]["result"]["exit_code"] == 0

    with SQLiteUnitOfWork(factory) as unit:
        persisted = SQLiteTaskRepository(unit).get(TaskId_from_string(task_id))
        unit.rollback()
    assert persisted is not None
    assert persisted.task.status is TaskStatus.COMPLETED
    with SQLiteUnitOfWork(factory) as unit:
        with pytest.raises(CyberOSError) as stale_error:
            SQLiteTaskRepository(unit).update_status_and_result(
                persisted,
                expected_version=1,
            )
    assert stale_error.value.code is ErrorCode.CONCURRENCY_CONFLICT

    rejected = task_run_cli(
        tmp_path,
        scope_id,
        target_ids["blocked.example.com"],
        "blocked.example.com",
        "echo",
        "must-not-run",
    )
    assert rejected.exit_code == 2
    assert json.loads(rejected.stdout)["error"]["code"] == "TARGET_EXCLUDED"

    task_list_after_rejection = invoke(tmp_path, ["task", "list", "--scope-id", scope_id, "--json"])
    assert len(json.loads(task_list_after_rejection.stdout)["data"]) == 1


def test_full_system_fail_closed_guards_and_stale_version(tmp_path: Path) -> None:
    factory = SQLiteConnectionFactory(DatabaseSettings(path=tmp_path / "guards.sqlite3"))
    MigrationRunner(factory, MIGRATIONS_DIR).run()
    workspace = Workspace.create("Guard Workspace", now=NOW)
    engagement = Engagement.create(workspace.id, "Guard Engagement", "learning", now=NOW)
    scope_time = NOW - timedelta(hours=2)
    draft_scope = Scope.create(engagement.id, "Draft Scope", now=scope_time)
    target = Target.create(
        draft_scope.id,
        TargetRule.INCLUDE,
        TargetKind.FQDN,
        "guard.example.com",
        now=scope_time,
    )
    with SQLiteUnitOfWork(factory) as unit:
        SQLiteWorkspaceRepository(unit).add(workspace)
        SQLiteEngagementRepository(unit).add(engagement)
        SQLiteScopeRepository(unit).add(draft_scope)
        SQLiteTargetRepository(unit).add(target)
        unit.commit()

    with pytest.raises(CyberOSError) as draft_error:
        ScopeValidationService(factory).authorize_execution(
            draft_scope.id,
            TargetCandidate("guard.example.com", TargetKind.FQDN),
        )
    assert draft_error.value.code is ErrorCode.SCOPE_NOT_AUTHORIZED

    validated = draft_scope.mark_validated(at=scope_time + timedelta(minutes=1))
    with SQLiteUnitOfWork(factory) as unit:
        SQLiteScopeRepository(unit).update(validated, expected_version=draft_scope.version)
        unit.commit()
    expired = validated.authorize(
        "expired-approval",
        expires_at=NOW - timedelta(minutes=1),
        at=scope_time + timedelta(minutes=1),
    )
    with SQLiteUnitOfWork(factory) as unit:
        SQLiteScopeRepository(unit).update(expired, expected_version=validated.version)
        unit.commit()
    with pytest.raises(CyberOSError) as expired_error:
        ScopeValidationService(factory).authorize_execution(
            expired.id,
            TargetCandidate("guard.example.com", TargetKind.FQDN),
        )
    assert expired_error.value.code is ErrorCode.SCOPE_EXPIRED

    other_target_id = TargetId(new_id())
    authorization = ExecutionAuthorization(
        scope_id=draft_scope.id,
        candidate=TargetCandidate("guard.example.com", TargetKind.FQDN),
        authorized_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        matched_target_id=target.id,
        matching_rule=TargetRule.INCLUDE,
        reason="test",
        scope_version=1,
    )
    with pytest.raises(CyberOSError) as cross_target_error:
        Task.create(
            draft_scope.id,
            other_target_id,
            authorization,
            ExecutionSpec(command=("echo", "blocked")),
        )
    assert cross_target_error.value.code is ErrorCode.TASK_AUTHORIZATION_TARGET_MISMATCH


def ScopeId_from_string(value: str) -> ScopeId:
    return ScopeId(UUID(value))


def TargetId_from_string(value: str) -> TargetId:
    return TargetId(UUID(value))


def TaskId_from_string(value: str) -> TaskId:
    return TaskId(UUID(value))
