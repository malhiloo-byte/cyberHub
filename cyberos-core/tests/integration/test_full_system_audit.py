"""End-to-end audit for the CyberOS 0.1–0.5 pipeline on a clean SQLite database."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

from cyberos.application.scope_validation import ScopeValidationService, TargetCandidate
from cyberos.application.services.task import TaskService
from cyberos.config.models import DatabaseSettings
from cyberos.core.context import OperationContext
from cyberos.domain.engagement.model import Engagement
from cyberos.domain.scope.model import Scope
from cyberos.domain.target.model import Target
from cyberos.domain.target.primitives import TargetKind, TargetRule
from cyberos.domain.task.primitives import TaskStatus
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
NOW = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)


def test_full_system_integration_audit_and_fail_closed(tmp_path: Path) -> None:
    factory = SQLiteConnectionFactory(DatabaseSettings(path=tmp_path / "audit.sqlite3"))
    migration_result = MigrationRunner(factory, MIGRATIONS_DIR).run()
    assert [item.version for item in migration_result.applied] == [1, 2, 3, 4]

    workspace = Workspace.create("Audit Workspace", now=NOW)
    engagement = Engagement.create(workspace.id, "Audit Engagement", "learning", now=NOW)
    scope = Scope.create(engagement.id, "Audit Scope", now=NOW)
    included_target = Target.create(
        scope.id,
        TargetRule.INCLUDE,
        TargetKind.FQDN,
        "audit.example.com",
        now=NOW,
    )
    excluded_target = Target.create(
        scope.id,
        TargetRule.EXCLUDE,
        TargetKind.FQDN,
        "blocked.example.com",
        now=NOW,
    )
    with SQLiteUnitOfWork(factory) as unit:
        SQLiteWorkspaceRepository(unit).add(workspace)
        SQLiteEngagementRepository(unit).add(engagement)
        SQLiteScopeRepository(unit).add(scope)
        SQLiteTargetRepository(unit).add(included_target)
        SQLiteTargetRepository(unit).add(excluded_target)
        unit.commit()

    from cyberos.application.services.scope import ScopeService

    authorized = ScopeService(factory).authorize(
        scope.id,
        "audit-approval",
        None,
        context=OperationContext(),
    )
    assert authorized.ok is True

    authorization = ScopeValidationService(factory).authorize_execution(
        scope.id,
        TargetCandidate("audit.example.com", TargetKind.FQDN),
    )
    assert authorization.matched_target_id == included_target.id

    run_result = TaskService(factory).run(
        scope.id,
        included_target.id,
        TargetCandidate("audit.example.com", TargetKind.FQDN),
        ExecutionSpec(
            command=(sys.executable, "-c", "print('full-audit-ok')"),
            max_output_bytes=128,
        ),
        context=OperationContext(),
    )
    assert run_result.ok is True
    assert run_result.data is not None
    assert run_result.data.task.status is TaskStatus.COMPLETED
    assert run_result.data.result is not None
    assert run_result.data.result.stdout == b"full-audit-ok\n"

    task_id = run_result.data.task.id
    with SQLiteUnitOfWork(factory) as unit:
        persisted = SQLiteTaskRepository(unit).get(task_id)
        unit.rollback()
    assert persisted == run_result.data

    rejected = TaskService(factory).run(
        scope.id,
        excluded_target.id,
        TargetCandidate("blocked.example.com", TargetKind.FQDN),
        ExecutionSpec(command=("echo", "must-not-run")),
        context=OperationContext(),
    )
    assert rejected.ok is False
    assert rejected.error is not None
    assert rejected.error.code == "TARGET_EXCLUDED"
    listed = TaskService(factory).list(scope_id=scope.id, context=OperationContext())
    assert listed.ok is True
    assert listed.data is not None
    assert len(listed.data) == 1
