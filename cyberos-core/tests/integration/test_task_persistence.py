"""Migration and repository integration tests for persisted TaskRecord snapshots."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cyberos.application.scope_validation import ExecutionAuthorization, TargetCandidate
from cyberos.config.models import DatabaseSettings
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.ids import new_id
from cyberos.domain.engagement.model import Engagement
from cyberos.domain.scope.model import Scope
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.model import Target
from cyberos.domain.target.primitives import TargetId, TargetKind, TargetRule
from cyberos.domain.task.model import Task
from cyberos.domain.task.primitives import TaskStatus
from cyberos.domain.task.record import TaskRecord
from cyberos.domain.task.result import ExecutionFailureReason, ExecutionResult
from cyberos.domain.task.spec import EnvPolicy, ExecutionSpec
from cyberos.domain.workspace.model import Workspace
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.engagement_repository import SQLiteEngagementRepository
from cyberos.persistence.migrations.loader import checksum_sql
from cyberos.persistence.migrations.runner import MigrationRunner
from cyberos.persistence.scope_repository import SQLiteScopeRepository
from cyberos.persistence.target_repository import SQLiteTargetRepository
from cyberos.persistence.task_repository import SQLiteTaskRepository
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork
from cyberos.persistence.workspace_repository import SQLiteWorkspaceRepository

MIGRATIONS_DIR = Path(__file__).parents[2] / "src/cyberos/persistence/migrations/versions"
NOW = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)


def factory_for(tmp_path: Path) -> SQLiteConnectionFactory:
    factory = SQLiteConnectionFactory(DatabaseSettings(path=tmp_path / "cyberos.sqlite3"))
    MigrationRunner(factory, MIGRATIONS_DIR).run()
    return factory


def parents(factory: SQLiteConnectionFactory) -> tuple[Scope, Target]:
    workspace = Workspace.create("Task Workspace", now=NOW)
    engagement = Engagement.create(workspace.id, "Task Engagement", "learning", now=NOW)
    scope = Scope.create(engagement.id, "Task Scope", now=NOW)
    target = Target.create(
        scope.id,
        TargetRule.INCLUDE,
        TargetKind.FQDN,
        "api.example.com",
        now=NOW,
    )
    with SQLiteUnitOfWork(factory) as unit:
        SQLiteWorkspaceRepository(unit).add(workspace)
        SQLiteEngagementRepository(unit).add(engagement)
        SQLiteScopeRepository(unit).add(scope)
        SQLiteTargetRepository(unit).add(target)
        unit.commit()
    return scope, target


def task_for(scope: Scope, target: Target, *, command: tuple[str, ...] = ("echo", "safe")) -> Task:
    authorization = ExecutionAuthorization(
        scope_id=scope.id,
        candidate=TargetCandidate("api.example.com", TargetKind.FQDN),
        authorized_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        matched_target_id=target.id,
        matching_rule=TargetRule.INCLUDE,
        reason="test_authorized",
        scope_version=1,
    )
    return Task.create(
        scope.id,
        target.id,
        authorization,
        ExecutionSpec(
            command=command,
            timeout_seconds=30,
            max_output_bytes=64,
            env_policy=EnvPolicy(allowed_keys=("LANG",)),
        ),
        now=NOW,
    )


def test_migration_0004_health_and_indexes_are_present(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    with factory.connect() as managed:
        assert managed.raw.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert managed.raw.execute("PRAGMA foreign_key_check").fetchall() == []
        indexes = {row[1] for row in managed.raw.execute("PRAGMA index_list(tasks)").fetchall()}
    assert "idx_tasks_scope_status" in indexes
    assert "idx_tasks_target_status" in indexes


def test_migration_0004_checksum_and_forward_only_behavior(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    source = (MIGRATIONS_DIR / "0004_tasks.sql").read_text(encoding="utf-8")
    with factory.connect() as managed:
        row = managed.raw.execute(
            "SELECT version, name, checksum FROM schema_migrations WHERE version = 4"
        ).fetchone()
    assert tuple(row) == (4, "tasks", checksum_sql(source))
    assert "IF NOT EXISTS" not in source.upper()
    assert "BEGIN" not in source.upper()
    assert "COMMIT" not in source.upper()
    assert MigrationRunner(factory, MIGRATIONS_DIR).run().applied == ()


def test_pending_task_round_trip_has_no_result(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    scope, target = parents(factory)
    task = task_for(scope, target)
    record = TaskRecord(task)

    with SQLiteUnitOfWork(factory) as unit:
        SQLiteTaskRepository(unit).add(record)
        unit.commit()
    with SQLiteUnitOfWork(factory) as unit:
        loaded = SQLiteTaskRepository(unit).get(task.id)
        unit.rollback()

    assert loaded == record
    assert loaded is not None
    assert loaded.result is None
    assert not isinstance(loaded, sqlite3.Row)


@pytest.mark.parametrize("terminal", ["completed", "failed"])
def test_terminal_task_round_trip_preserves_bounded_execution_result(
    tmp_path: Path,
    terminal: str,
) -> None:
    factory = factory_for(tmp_path)
    scope, target = parents(factory)
    task = task_for(scope, target)
    running = task.transition(TaskStatus.RUNNING, at=NOW + timedelta(seconds=1))
    if terminal == "completed":
        finished = running.transition(TaskStatus.COMPLETED, at=NOW + timedelta(seconds=2))
        result = ExecutionResult(
            exit_code=0,
            stdout=b"partial",
            stderr=b"",
            truncated=True,
            duration_seconds=0.123,
            timeout_exceeded=False,
        )
    else:
        finished = running.transition(TaskStatus.FAILED, at=NOW + timedelta(seconds=2))
        result = ExecutionResult(
            exit_code=-15,
            stdout=b"partial",
            stderr=b"timeout",
            truncated=True,
            duration_seconds=1.001,
            timeout_exceeded=True,
            failure_reason=ExecutionFailureReason.TIMEOUT_EXCEEDED,
            error_message="TIMEOUT_EXCEEDED",
        )
    record = TaskRecord(finished, result)

    with SQLiteUnitOfWork(factory) as unit:
        SQLiteTaskRepository(unit).add(record)
        unit.commit()
    with SQLiteUnitOfWork(factory) as unit:
        loaded = SQLiteTaskRepository(unit).get(task.id)
        unit.rollback()

    assert loaded == record
    assert loaded is not None
    assert loaded.result is not None
    assert loaded.result.stdout == b"partial"
    assert loaded.result.truncated is True
    assert loaded.result.duration_seconds == result.duration_seconds


def test_update_status_and_result_uses_optimistic_version(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    scope, target = parents(factory)
    task = task_for(scope, target)
    with SQLiteUnitOfWork(factory) as unit:
        repository = SQLiteTaskRepository(unit)
        repository.add(TaskRecord(task))
        running = task.transition(TaskStatus.RUNNING, at=NOW + timedelta(seconds=1))
        running_record = repository.update_status_and_result(
            TaskRecord(running), expected_version=task.version
        )
        unit.commit()

    assert running_record.task.status is TaskStatus.RUNNING
    with SQLiteUnitOfWork(factory) as unit:
        repository = SQLiteTaskRepository(unit)
        with pytest.raises(CyberOSError) as captured:
            repository.update_status_and_result(TaskRecord(running), expected_version=task.version)
    assert captured.value.code is ErrorCode.CONCURRENCY_CONFLICT


def test_scope_and_target_delete_are_restricted_by_task_fk(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    scope, target = parents(factory)
    task = task_for(scope, target)
    with SQLiteUnitOfWork(factory) as unit:
        SQLiteTaskRepository(unit).add(TaskRecord(task))
        with pytest.raises(sqlite3.IntegrityError):
            unit.raw.execute("DELETE FROM targets WHERE id = ?", (str(target.id),))
        with pytest.raises(sqlite3.IntegrityError):
            unit.raw.execute("DELETE FROM scopes WHERE id = ?", (str(scope.id),))


def test_missing_scope_or_target_is_rejected_before_insert(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    scope_id = ScopeId(new_id())
    target_id = TargetId(new_id())
    fake_scope = Scope.model_construct(id=scope_id)
    fake_target = Target.model_construct(id=target_id, scope_id=scope_id)
    task = task_for(fake_scope, fake_target)

    with SQLiteUnitOfWork(factory) as unit:
        with pytest.raises(CyberOSError) as captured:
            SQLiteTaskRepository(unit).add(TaskRecord(task))
    assert captured.value.code is ErrorCode.SCOPE_NOT_FOUND


def test_missing_target_is_rejected_before_insert(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    scope, _ = parents(factory)
    missing_target = Target.model_construct(id=TargetId(new_id()), scope_id=scope.id)
    task = task_for(scope, missing_target)

    with SQLiteUnitOfWork(factory) as unit:
        with pytest.raises(CyberOSError) as captured:
            SQLiteTaskRepository(unit).add(TaskRecord(task))
    assert captured.value.code is ErrorCode.TARGET_NOT_FOUND
