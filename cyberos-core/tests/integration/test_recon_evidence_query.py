from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from cyberos.application.offline_web_pentest import (
    OfflineWebPentestHarness,
    OfflineWebPentestScenario,
)
from cyberos.application.recon_evidence_query import EvidenceQueryService
from cyberos.application.scope_validation import ScopeValidationService, TargetCandidate
from cyberos.config.models import DatabaseSettings
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.recon.evidence import EvidenceFactory, EvidenceKind, EvidenceStatus
from cyberos.domain.recon.evidence_query import (
    EvidenceCursor,
    EvidenceQuery,
    EvidenceSort,
    MetadataMode,
)
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.primitives import TargetId, TargetKind
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.migrations.runner import MigrationRunner
from cyberos.persistence.recon_evidence_repository import SQLiteReconEvidenceRepository
from cyberos.persistence.recon_repository import SQLiteReconRepository
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork

MIGRATIONS_DIR = Path(__file__).parents[2] / "src/cyberos/persistence/migrations/versions"
NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


def factory_for(tmp_path: Path) -> SQLiteConnectionFactory:
    factory = SQLiteConnectionFactory(DatabaseSettings(path=tmp_path / "cyberos.sqlite3"))
    MigrationRunner(factory, MIGRATIONS_DIR).run()
    return factory


def test_offline_web_pentest_happy_path_is_end_to_end_and_deterministic(
    tmp_path: Path,
) -> None:
    factory = factory_for(tmp_path)
    result = OfflineWebPentestHarness(factory).run(OfflineWebPentestScenario(now=NOW))
    assert result.report.status.value == "completed"
    assert result.evidence.status is EvidenceStatus.ACTIVE
    assert result.query_page.returned == 1
    item = result.query_page.items[0]
    assert item.id == result.evidence.id
    assert item.metadata == {"offline_fixture": True, "scenario_id": "offline.web.pentest"}
    assert item.pipeline_id == "offline.web.pentest"
    assert item.scope_id == result.task.scope_id
    assert item.target_id == result.task.target_id


def test_query_rejects_unbounded_and_oversized_requests() -> None:
    with pytest.raises(CyberOSError) as unbounded:
        EvidenceQuery()
    assert unbounded.value.code is ErrorCode.EVIDENCE_QUERY_UNBOUNDED

    with pytest.raises(CyberOSError) as oversized:
        EvidenceQuery(scope_id=ScopeId(uuid4()), limit=201)
    assert oversized.value.code is ErrorCode.EVIDENCE_QUERY_LIMIT_EXCEEDED


def test_summary_projection_omits_metadata_and_archive_requires_explicit_filter(
    tmp_path: Path,
) -> None:
    factory = factory_for(tmp_path)
    result = OfflineWebPentestHarness(factory).run(OfflineWebPentestScenario(now=NOW))
    summary = EvidenceQueryService(factory).query(
        EvidenceQuery(scope_id=result.task.scope_id, metadata_mode=MetadataMode.SUMMARY)
    )
    assert summary.items[0].metadata is None

    with SQLiteUnitOfWork(factory) as unit:
        archived = SQLiteReconEvidenceRepository(unit).archive(
            result.evidence.id, expected_version=result.evidence.version
        )
        unit.commit()
    assert archived.status is EvidenceStatus.ARCHIVED
    assert (
        EvidenceQueryService(factory).query(EvidenceQuery(scope_id=result.task.scope_id)).items
        == ()
    )
    archived_page = EvidenceQueryService(factory).query(
        EvidenceQuery(
            scope_id=result.task.scope_id,
            status=EvidenceStatus.ARCHIVED,
            metadata_mode=MetadataMode.SAFE_METADATA,
        )
    )
    assert archived_page.items[0].id == result.evidence.id


def test_keyset_pagination_is_stable_and_cursor_is_query_bound(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    scenario = OfflineWebPentestScenario(now=NOW)
    result = OfflineWebPentestHarness(factory).run(scenario)
    authorization = ScopeValidationService(factory).authorize_execution(
        result.task.scope_id,
        TargetCandidate(scenario.target_value, TargetKind.FQDN),
    )
    with SQLiteUnitOfWork(factory) as unit:
        recon = SQLiteReconRepository(unit)
        asset = recon.list_assets(result.task.scope_id, result.task.target_id)[0]
        observation = recon.list_observations(asset.id)[0]
        repository = SQLiteReconEvidenceRepository(unit)
        for index in range(55):
            record = EvidenceFactory.from_observation(
                result.task,
                authorization,
                asset,
                observation,
                kind=EvidenceKind.SERVICE_METADATA,
                title=f"Offline service {index}",
                metadata={"index": index},
                collected_at=NOW + timedelta(seconds=index),
            )
            repository.add(record)
        unit.commit()

    first_query = EvidenceQuery(
        scope_id=result.task.scope_id,
        kind=EvidenceKind.SERVICE_METADATA,
        sort=EvidenceSort.COLLECTED_AT_DESC,
        limit=25,
    )
    first = EvidenceQueryService(factory).query(first_query)
    assert first.returned == 25
    assert first.has_more is True
    assert first.next_cursor is not None

    second = EvidenceQueryService(factory).query(replace(first_query, cursor=first.next_cursor))
    assert second.returned == 25
    assert second.has_more is True
    assert set(item.id for item in first.items).isdisjoint(item.id for item in second.items)

    mismatched = replace(
        first_query,
        sort=EvidenceSort.KIND_ASC,
        cursor=first.next_cursor,
    )
    with pytest.raises(CyberOSError) as cursor_error:
        EvidenceQueryService(factory).query(mismatched)
    assert cursor_error.value.code is ErrorCode.EVIDENCE_QUERY_CURSOR_INVALID

    invalid_cursor = EvidenceCursor(
        1,
        first_query.fingerprint(),
        first_query.sort,
        (NOW.isoformat(), str(first.items[-1].id), ""),
    )
    assert EvidenceCursor.decode(invalid_cursor.encode()) == invalid_cursor


def test_all_allowlisted_sorts_return_stable_projections(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    result = OfflineWebPentestHarness(factory).run(OfflineWebPentestScenario(now=NOW))
    for sort in EvidenceSort:
        page = EvidenceQueryService(factory).query(
            EvidenceQuery(scope_id=result.task.scope_id, sort=sort)
        )
        assert page.returned == 1
        assert page.items[0].id == result.evidence.id


def test_query_rejects_inconsistent_context_without_leaking_rows(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    result = OfflineWebPentestHarness(factory).run(OfflineWebPentestScenario(now=NOW))
    with pytest.raises(CyberOSError) as context_error:
        EvidenceQueryService(factory).query(
            EvidenceQuery(scope_id=result.task.scope_id, target_id=TargetId(uuid4()))
        )
    assert context_error.value.code is ErrorCode.EVIDENCE_QUERY_CONTEXT_INVALID


def test_offline_workflow_failure_is_typed_and_does_not_create_evidence(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    with pytest.raises(CyberOSError) as failure:
        OfflineWebPentestHarness(factory).run(
            OfflineWebPentestScenario(target_value="offline.failure", now=NOW)
        )
    assert failure.value.code is ErrorCode.PLUGIN_EXECUTION_FAILED
    with SQLiteUnitOfWork(factory) as unit:
        evidence_count = unit.raw.execute("SELECT count(*) FROM evidence_records").fetchone()[0]
        asset_count = unit.raw.execute("SELECT count(*) FROM assets").fetchone()[0]
        unit.rollback()
    assert evidence_count == 0
    assert asset_count == 0
