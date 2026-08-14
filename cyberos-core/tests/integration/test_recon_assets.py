from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cyberos.application.recon_ingestion import ReconIngestionService
from cyberos.application.scope_validation import ExecutionAuthorization, TargetCandidate
from cyberos.config.models import DatabaseSettings
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.engagement.model import Engagement, EngagementKind
from cyberos.domain.scope.model import Scope
from cyberos.domain.target.model import Target
from cyberos.domain.target.primitives import TargetKind, TargetRule
from cyberos.domain.task.model import Task
from cyberos.domain.task.record import TaskRecord
from cyberos.domain.task.spec import ExecutionSpec
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.engagement_repository import SQLiteEngagementRepository
from cyberos.persistence.migrations.loader import checksum_sql
from cyberos.persistence.migrations.runner import MigrationRunner
from cyberos.persistence.recon_repository import SQLiteReconRepository
from cyberos.persistence.scope_repository import SQLiteScopeRepository
from cyberos.persistence.target_repository import SQLiteTargetRepository
from cyberos.persistence.task_repository import SQLiteTaskRepository
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork
from cyberos.persistence.workspace_repository import SQLiteWorkspaceRepository
from cyberos.recon.contracts import (
    ExecutionLimits,
    ReconObservation,
    ReconResult,
)

MIGRATIONS_DIR = Path(__file__).parents[2] / "src/cyberos/persistence/migrations/versions"
NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


def factory_for(tmp_path: Path) -> SQLiteConnectionFactory:
    factory = SQLiteConnectionFactory(DatabaseSettings(path=tmp_path / "cyberos.sqlite3"))
    MigrationRunner(factory, MIGRATIONS_DIR).run()
    return factory


def parents(factory: SQLiteConnectionFactory) -> tuple[Scope, Target, Task, ExecutionAuthorization]:
    workspace = __import__(
        "cyberos.domain.workspace.model", fromlist=["Workspace"]
    ).Workspace.create("Recon Workspace", now=NOW)
    engagement = Engagement.create(
        workspace.id, "Recon Engagement", EngagementKind.LEARNING, now=NOW
    )
    scope = Scope.create(engagement.id, "Recon Scope", now=NOW)
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
        reason="test_authorized",
        scope_version=1,
    )
    task = Task.create(
        scope.id,
        target.id,
        authorization,
        ExecutionSpec(command=("fixture", "offline"), max_output_bytes=1024),
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


def result_for(task: Task, *, observation_type: str = "subdomain") -> ReconResult:
    observation = ReconObservation(
        observation_type=observation_type,
        value="dev.example.com"
        if observation_type == "subdomain"
        else "https://api.example.com/health",
        metadata=(("parent_domain", "example.com"),)
        if observation_type == "subdomain"
        else (("status_code", "200"), ("technologies_json", '["fixture"]')),
    )
    return ReconResult.success(
        task_id=task.id,
        scope_id=task.scope_id,
        target_id=task.target_id,
        plugin_id="offline.fixture",
        plugin_version="1.0.0",
        contract_version="1.0",
        observations=(observation,),
    )


def limits() -> ExecutionLimits:
    return ExecutionLimits(
        timeout_seconds=30,
        max_input_bytes=4096,
        max_output_bytes=1024,
        max_observations=10,
    )


def ingest(
    factory: SQLiteConnectionFactory, task: Task, authorization: ExecutionAuthorization
) -> None:
    ReconIngestionService(factory).ingest(
        task=task,
        authorization=authorization,
        result=result_for(task),
        effective_limits=limits(),
        observed_at=NOW,
    )


def test_migration_0005_checksum_tables_indexes_and_health(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    source = (MIGRATIONS_DIR / "0005_recon_assets.sql").read_text(encoding="utf-8")
    with factory.connect() as managed:
        row = managed.raw.execute(
            "SELECT version, name, checksum FROM schema_migrations WHERE version = 5"
        ).fetchone()
        tables = {
            item[0]
            for item in managed.raw.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        indexes = {
            table: {item[1] for item in managed.raw.execute(f"PRAGMA index_list({table})")}
            for table in (
                "assets",
                "asset_observations",
                "subdomain_records",
                "port_service_records",
                "http_endpoint_records",
            )
        }
        assert managed.raw.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert managed.raw.execute("PRAGMA foreign_key_check").fetchall() == []
    assert tuple(row) == (5, "recon_assets", checksum_sql(source))
    assert {
        "assets",
        "asset_observations",
        "subdomain_records",
        "port_service_records",
        "http_endpoint_records",
    } <= tables
    assert "uq_assets_scope_target_kind_value" in indexes["assets"]
    assert "uq_asset_observations_idempotency" in indexes["asset_observations"]


def test_migration_0005_is_forward_only_and_idempotent(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    second = MigrationRunner(factory, MIGRATIONS_DIR).run()
    source = (MIGRATIONS_DIR / "0005_recon_assets.sql").read_text(encoding="utf-8")
    assert second.applied == ()
    assert second.current_version == 6
    assert "IF NOT EXISTS" not in source.upper()
    assert "BEGIN" not in source.upper()
    assert "COMMIT" not in source.upper()


def test_recon_ingestion_round_trip_and_typed_projection(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    scope, target, task, authorization = parents(factory)
    ingest(factory, task, authorization)
    with SQLiteUnitOfWork(factory) as unit:
        repository = SQLiteReconRepository(unit)
        assets = repository.list_assets(scope.id, target.id)
        observations = repository.list_observations(assets[0].id)
        typed_count = unit.raw.execute("SELECT count(*) FROM subdomain_records").fetchone()[0]
        unit.rollback()
    assert len(assets) == 1
    assert assets[0].canonical_value == "dev.example.com"
    assert len(observations) == 1
    assert typed_count == 1


def test_recon_correlation_is_idempotent_for_same_result(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    scope, target, task, authorization = parents(factory)
    ingest(factory, task, authorization)
    ingest(factory, task, authorization)
    with SQLiteUnitOfWork(factory) as unit:
        assert unit.raw.execute("SELECT count(*) FROM assets").fetchone()[0] == 1
        assert unit.raw.execute("SELECT count(*) FROM asset_observations").fetchone()[0] == 1
        unit.rollback()


def test_recon_target_and_task_foreign_keys_are_restrict(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    scope, target, task, authorization = parents(factory)
    ingest(factory, task, authorization)
    with factory.connect() as managed:
        with pytest.raises(sqlite3.IntegrityError):
            managed.raw.execute("DELETE FROM targets WHERE id = ?", (str(target.id),))
        with pytest.raises(sqlite3.IntegrityError):
            managed.raw.execute("DELETE FROM tasks WHERE id = ?", (str(task.id),))
        with pytest.raises(sqlite3.IntegrityError):
            managed.raw.execute("DELETE FROM scopes WHERE id = ?", (str(scope.id),))


def test_recon_atomic_rollback_leaves_no_partial_typed_row(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    scope, target, task, authorization = parents(factory)
    with SQLiteUnitOfWork(factory) as unit:
        unit.raw.execute(
            "INSERT INTO assets (id, scope_id, target_id, asset_kind, canonical_value, "
            "display_value, status, first_seen_at, last_seen_at, first_seen_task_id, "
            "last_seen_task_id, created_at, updated_at, archived_at, version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(__import__("uuid").uuid4()),
                str(scope.id),
                str(target.id),
                "host",
                "fixture",
                "fixture",
                "active",
                NOW.isoformat(),
                NOW.isoformat(),
                str(task.id),
                str(task.id),
                NOW.isoformat(),
                NOW.isoformat(),
                None,
                1,
            ),
        )
        with pytest.raises(sqlite3.IntegrityError):
            unit.raw.execute(
                "INSERT INTO port_service_records "
                "(id, asset_id, scope_id, target_id, task_id, transport, port, status, "
                "first_seen_at, last_seen_at, created_at, updated_at, version) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(__import__("uuid").uuid4()),
                    str(__import__("uuid").uuid4()),
                    str(scope.id),
                    str(target.id),
                    str(task.id),
                    "tcp",
                    0,
                    "active",
                    NOW.isoformat(),
                    NOW.isoformat(),
                    NOW.isoformat(),
                    NOW.isoformat(),
                    1,
                ),
            )
        unit.rollback()
    with factory.connect() as managed:
        assert managed.raw.execute("SELECT count(*) FROM assets").fetchone()[0] == 0


def test_recon_rejects_cross_target_authorization_before_write(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    scope, target, task, authorization = parents(factory)
    wrong_authorization = ExecutionAuthorization(
        scope_id=scope.id,
        candidate=TargetCandidate("other.example.com", TargetKind.FQDN),
        authorized_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        matched_target_id=Target.create(
            scope.id, TargetRule.INCLUDE, TargetKind.FQDN, "other.example.com", now=NOW
        ).id,
        matching_rule=TargetRule.INCLUDE,
        reason="wrong_target",
        scope_version=1,
    )
    with pytest.raises(CyberOSError) as captured:
        ReconIngestionService(factory).ingest(
            task=task,
            authorization=wrong_authorization,
            result=result_for(task),
            effective_limits=limits(),
        )
    assert captured.value.code is ErrorCode.RECON_AUTHORIZATION_INVALID
    with factory.connect() as managed:
        assert managed.raw.execute("SELECT count(*) FROM assets").fetchone()[0] == 0


def test_recon_rejects_result_identity_mismatch_and_oversized_result(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    scope, target, task, authorization = parents(factory)
    result = result_for(task)
    mismatched = result.__class__(
        task_id=__import__("uuid").uuid4(),
        scope_id=result.scope_id,
        target_id=result.target_id,
        plugin_id=result.plugin_id,
        plugin_version=result.plugin_version,
        contract_version=result.contract_version,
        status=result.status,
        observations=result.observations,
    )
    with pytest.raises(CyberOSError) as captured:
        ReconIngestionService(factory).ingest(
            task=task, authorization=authorization, result=mismatched, effective_limits=limits()
        )
    assert captured.value.code is ErrorCode.RECON_RESULT_INVALID
    with pytest.raises(CyberOSError) as captured_limit:
        ReconIngestionService(factory).ingest(
            task=task,
            authorization=authorization,
            result=result,
            effective_limits=ExecutionLimits(30, 4096, 1, 10),
            observed_at=NOW,
        )
    assert captured_limit.value.code is ErrorCode.PLUGIN_LIMIT_EXCEEDED


def test_recon_boundary_source_has_no_forbidden_side_effect_apis() -> None:
    root = Path(__file__).parents[2] / "src/cyberos"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            root / "application/recon_ingestion.py",
            root / "domain/recon/model.py",
            root / "persistence/recon_repository.py",
        )
    )
    for forbidden in (
        "socket",
        "requests",
        "urllib.request",
        "subprocess",
        "create_subprocess",
        "urlopen",
    ):
        assert forbidden not in source
