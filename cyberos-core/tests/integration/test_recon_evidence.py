from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from cyberos.application.recon_evidence import ReconEvidenceService
from cyberos.application.recon_ingestion import ReconIngestionService
from cyberos.application.scope_validation import ExecutionAuthorization, TargetCandidate
from cyberos.config.models import DatabaseSettings
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.engagement.model import Engagement, EngagementKind
from cyberos.domain.recon.evidence import (
    EvidenceFactory,
    EvidenceKind,
    EvidenceRecord,
    EvidenceStatus,
)
from cyberos.domain.recon.model import AssetAggregate, AssetObservation
from cyberos.domain.scope.model import Scope
from cyberos.domain.target.model import Target
from cyberos.domain.target.primitives import TargetKind, TargetRule
from cyberos.domain.task.model import Task
from cyberos.domain.task.record import TaskRecord
from cyberos.domain.task.spec import ExecutionSpec
from cyberos.domain.workspace.model import Workspace
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.engagement_repository import SQLiteEngagementRepository
from cyberos.persistence.mappers.evidence import evidence_from_row
from cyberos.persistence.migrations.loader import checksum_sql
from cyberos.persistence.migrations.runner import MigrationRunner
from cyberos.persistence.recon_evidence_repository import SQLiteReconEvidenceRepository
from cyberos.persistence.recon_repository import SQLiteReconRepository
from cyberos.persistence.scope_repository import SQLiteScopeRepository
from cyberos.persistence.target_repository import SQLiteTargetRepository
from cyberos.persistence.task_repository import SQLiteTaskRepository
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork
from cyberos.persistence.workspace_repository import SQLiteWorkspaceRepository
from cyberos.recon.contracts import ExecutionLimits, ReconObservation, ReconResult

MIGRATIONS_DIR = Path(__file__).parents[2] / "src/cyberos/persistence/migrations/versions"
NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


def factory_for(tmp_path: Path) -> SQLiteConnectionFactory:
    factory = SQLiteConnectionFactory(DatabaseSettings(path=tmp_path / "cyberos.sqlite3"))
    MigrationRunner(factory, MIGRATIONS_DIR).run()
    return factory


def parents(
    factory: SQLiteConnectionFactory, *, suffix: str = ""
) -> tuple[Scope, Target, Task, ExecutionAuthorization]:
    workspace = Workspace.create("Evidence Workspace" + suffix, now=NOW)
    engagement = Engagement.create(
        workspace.id, "Evidence Engagement" + suffix, EngagementKind.LEARNING, now=NOW
    )
    scope = Scope.create(engagement.id, "Evidence Scope" + suffix, now=NOW)
    target = Target.create(
        scope.id,
        TargetRule.INCLUDE,
        TargetKind.FQDN,
        "api" + suffix + ".example.com",
        now=NOW,
    )
    authorization = ExecutionAuthorization(
        scope_id=scope.id,
        candidate=TargetCandidate(target.value, TargetKind.FQDN),
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


def ingest(
    factory: SQLiteConnectionFactory, task: Task, authorization: ExecutionAuthorization
) -> tuple[AssetAggregate, AssetObservation]:
    result = ReconResult.success(
        task_id=task.id,
        scope_id=task.scope_id,
        target_id=task.target_id,
        plugin_id="offline.fixture",
        plugin_version="1.0.0",
        contract_version="1.0",
        observations=(
            ReconObservation(
                observation_type="subdomain",
                value="dev.example.com",
                metadata=(("parent_domain", "example.com"),),
            ),
        ),
    )
    ReconIngestionService(factory).ingest(
        task=task,
        authorization=authorization,
        result=result,
        effective_limits=ExecutionLimits(
            timeout_seconds=30,
            max_input_bytes=4096,
            max_output_bytes=1024,
            max_observations=10,
        ),
        observed_at=NOW,
    )
    with SQLiteUnitOfWork(factory) as unit:
        repository = SQLiteReconRepository(unit)
        asset = repository.list_assets(task.scope_id, task.target_id)[0]
        observation = repository.list_observations(asset.id)[0]
        unit.rollback()
    return asset, observation


def record_for(
    task: Task,
    authorization: ExecutionAuthorization,
    asset: AssetAggregate,
    observation: AssetObservation,
) -> EvidenceRecord:
    return EvidenceFactory.from_observation(
        task,
        authorization,
        asset,
        observation,
        kind=EvidenceKind.OBSERVATION_SUMMARY,
        title="Offline subdomain observation",
        metadata={"asset_kind": asset.asset_kind.value, "observed": True},
        pipeline_id="recon.fixture",
        pipeline_version="1.0.0",
        collected_at=NOW,
    )


def test_migration_0006_checksum_health_and_indexes(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    source = (MIGRATIONS_DIR / "0006_recon_evidence.sql").read_text(encoding="utf-8")
    with factory.connect() as managed:
        migration = managed.raw.execute(
            "SELECT version, name, checksum FROM schema_migrations WHERE version = 6"
        ).fetchone()
        tables = {
            item[0]
            for item in managed.raw.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        indexes = {item[1] for item in managed.raw.execute("PRAGMA index_list(evidence_records)")}
        assert managed.raw.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert managed.raw.execute("PRAGMA foreign_key_check").fetchall() == []
    assert tuple(migration) == (6, "recon_evidence", checksum_sql(source))
    assert "evidence_records" in tables
    assert {"uq_evidence_idempotency", "idx_evidence_task_collected"} <= indexes
    assert "IF NOT EXISTS" not in source.upper()
    assert "BEGIN" not in source.upper()
    assert "COMMIT" not in source.upper()


def test_migration_0006_is_idempotent_and_forward_only(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    result = MigrationRunner(factory, MIGRATIONS_DIR).run()
    assert result.applied == ()
    assert result.current_version == 6


def test_evidence_factory_binds_authorization_and_metadata(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    _, _, task, authorization = parents(factory)
    asset, observation = ingest(factory, task, authorization)
    record = record_for(task, authorization, asset, observation)
    assert record.status is EvidenceStatus.ACTIVE
    assert record.observation_id == observation.id
    assert record.content_size_bytes == len(b'{"asset_kind":"subdomain","observed":true}')
    assert record.metadata["asset_kind"] == "subdomain"


def test_evidence_factory_rejects_expired_or_cross_context_authorization(
    tmp_path: Path,
) -> None:
    factory = factory_for(tmp_path)
    _, _, task, authorization = parents(factory)
    asset, observation = ingest(factory, task, authorization)
    with pytest.raises(CyberOSError) as expired:
        record_for(task, authorization, asset, observation)
        EvidenceFactory.from_observation(
            task,
            authorization,
            asset,
            observation,
            kind=EvidenceKind.OBSERVATION_SUMMARY,
            title="Expired",
            metadata={"safe": True},
            collected_at=NOW + timedelta(hours=2),
        )
    assert expired.value.code is ErrorCode.RECON_EVIDENCE_PROVENANCE_INVALID

    other_scope, _, other_task, other_authorization = parents(factory, suffix="-other")
    del other_scope
    with pytest.raises(CyberOSError) as mismatch:
        EvidenceFactory.from_observation(
            other_task,
            other_authorization,
            asset,
            observation,
            kind=EvidenceKind.OBSERVATION_SUMMARY,
            title="Mismatch",
            metadata={"safe": True},
            collected_at=NOW,
        )
    assert mismatch.value.code is ErrorCode.RECON_EVIDENCE_PROVENANCE_INVALID


def test_repository_round_trip_idempotency_and_service_provenance(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    _, _, task, authorization = parents(factory)
    asset, observation = ingest(factory, task, authorization)
    created = ReconEvidenceService(factory).create_from_observation(
        task,
        authorization,
        asset,
        observation,
        kind=EvidenceKind.OBSERVATION_SUMMARY,
        title="Offline subdomain observation",
        metadata={"asset_kind": asset.asset_kind.value, "observed": True},
        pipeline_id="recon.fixture",
        pipeline_version="1.0.0",
        collected_at=NOW,
    )
    with SQLiteUnitOfWork(factory) as unit:
        repository = SQLiteReconEvidenceRepository(unit)
        loaded = repository.get(created.id)
        replay = repository.add(created)
        listed = repository.list_by_task(task.id)
        unit.rollback()
    assert loaded == created
    assert replay == created
    assert listed == (created,)


def test_repository_rejects_cross_context_record_and_no_partial_commit(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    _, _, task, authorization = parents(factory)
    asset, observation = ingest(factory, task, authorization)
    record = record_for(task, authorization, asset, observation)
    _, other_target, _, _ = parents(factory, suffix="-other")
    invalid = replace(record, target_id=other_target.id)
    with SQLiteUnitOfWork(factory) as unit:
        with pytest.raises(CyberOSError) as error:
            SQLiteReconEvidenceRepository(unit).add(invalid)
        unit.rollback()
    assert error.value.code is ErrorCode.RECON_EVIDENCE_PROVENANCE_INVALID
    with SQLiteUnitOfWork(factory) as unit:
        count = unit.raw.execute("SELECT count(*) FROM evidence_records").fetchone()[0]
        unit.rollback()
    assert count == 0


def test_archive_only_lifecycle_and_optimistic_concurrency(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    _, _, task, authorization = parents(factory)
    asset, observation = ingest(factory, task, authorization)
    record = ReconEvidenceService(factory).create_from_observation(
        task,
        authorization,
        asset,
        observation,
        kind=EvidenceKind.OBSERVATION_SUMMARY,
        title="Archive test",
        metadata={"safe": True},
        collected_at=NOW,
    )
    with SQLiteUnitOfWork(factory) as unit:
        repository = SQLiteReconEvidenceRepository(unit)
        archived = repository.archive(record.id, expected_version=1)
        unit.commit()
    assert archived.status is EvidenceStatus.ARCHIVED
    assert archived.version == 2
    with SQLiteUnitOfWork(factory) as unit:
        repository = SQLiteReconEvidenceRepository(unit)
        assert repository.list_by_task(task.id) == ()
        assert repository.list_by_task(task.id, include_archived=True) == (archived,)
        with pytest.raises(CyberOSError) as stale:
            repository.archive(record.id, expected_version=1)
        unit.rollback()
    assert stale.value.code is ErrorCode.RECON_EVIDENCE_ARCHIVED


def test_metadata_and_sql_constraints_reject_unsafe_values(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    _, _, task, authorization = parents(factory)
    asset, observation = ingest(factory, task, authorization)
    with pytest.raises(CyberOSError) as restricted:
        EvidenceFactory.from_observation(
            task,
            authorization,
            asset,
            observation,
            kind=EvidenceKind.OBSERVATION_SUMMARY,
            title="Unsafe",
            metadata={"token": "secret"},
            collected_at=NOW,
        )
    assert restricted.value.code is ErrorCode.RECON_EVIDENCE_INVALID

    valid = record_for(task, authorization, asset, observation)
    with SQLiteUnitOfWork(factory) as unit:
        with pytest.raises(sqlite3.IntegrityError):
            unit.raw.execute(
                "INSERT INTO evidence_records (id, scope_id, target_id, task_id, asset_id, "
                "observation_id, kind, title, content_digest, content_size_bytes, metadata_json, "
                "source_plugin_id, source_plugin_version, collected_at, status, version, "
                "created_at, updated_at) VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(valid.id),
                    str(valid.scope_id),
                    str(valid.target_id),
                    str(valid.task_id),
                    str(valid.asset_id),
                    str(valid.observation_id),
                    "unknown",
                    valid.title,
                    valid.content_digest,
                    valid.content_size_bytes,
                    '{"safe":true}',
                    valid.source_plugin_id,
                    valid.source_plugin_version,
                    valid.collected_at.isoformat(),
                    "active",
                    1,
                    valid.created_at.isoformat(),
                    valid.updated_at.isoformat(),
                ),
            )
        unit.rollback()


def test_evidence_mapper_rejects_corrupt_metadata_row(tmp_path: Path) -> None:
    del tmp_path
    with pytest.raises(CyberOSError) as error:
        evidence_from_row(cast(sqlite3.Row, {}))
    assert error.value.code is ErrorCode.PERSISTENCE_MAPPING_FAILED
