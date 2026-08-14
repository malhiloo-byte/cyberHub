from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from cyberos.application.offline_web_api import (
    MultiWebApiOfflineHarness,
    MultiWebApiOfflineScenario,
    OfflineWebApiStep,
    OfflineWebApiStepKind,
)
from cyberos.application.recon_reporting import ReconReportingService
from cyberos.config.models import DatabaseSettings
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.recon.reporting import ReconReportBudget, ReconReportContext
from cyberos.domain.scope.primitives import ScopeId
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.migrations.runner import MigrationRunner
from cyberos.persistence.recon_repository import SQLiteReconRepository
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork

MIGRATIONS_DIR = Path(__file__).parents[2] / "src/cyberos/persistence/migrations/versions"
NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


def factory_for(tmp_path: Path) -> SQLiteConnectionFactory:
    factory = SQLiteConnectionFactory(DatabaseSettings(path=tmp_path / "cyberos.sqlite3"))
    MigrationRunner(factory, MIGRATIONS_DIR).run()
    return factory


def test_multi_web_api_workflow_chains_and_reports_synthetic_outputs(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    result = MultiWebApiOfflineHarness(factory).run(MultiWebApiOfflineScenario(now=NOW))

    assert result.report.status.value == "completed"
    assert len(result.evidence) == 3
    assert result.summary is not None
    assert result.summary.asset_count == 1
    assert result.summary.observation_count == 3
    assert result.summary.provenance.synthetic_record_count == 3
    assert result.summary.synthetic_fixture_only is True
    assert result.summary.source_plugins[0].evidence_count == 1
    service = ReconReportingService(factory, clock=lambda: NOW)
    context = ReconReportContext(result.task.scope_id, result.task.target_id, result.task.id)
    distribution = service.asset_distribution_breakdown(context)
    audit = service.provenance_audit_summary(context)
    assert distribution.total_assets == 1
    assert distribution.observed_asset_count == 1
    assert distribution.evidence_linked_asset_count == 1
    assert distribution.unlinked_asset_count == 0
    assert audit.total_evidence == 3
    assert audit.cross_context_violation_count == 0
    assert audit.missing_parent_count == 0


def test_reporting_budget_overflow_fails_closed_without_partial_projection(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    result = MultiWebApiOfflineHarness(factory).run(MultiWebApiOfflineScenario(now=NOW))
    assert result.summary is not None
    with pytest.raises(CyberOSError) as error:
        ReconReportingService(factory, clock=lambda: NOW).target_recon_summary(
            ReconReportContext(result.task.scope_id, result.task.target_id, result.task.id),
            budget=ReconReportBudget(max_evidence_records=2),
        )
    assert error.value.code is ErrorCode.REPORT_BUDGET_EXCEEDED


def test_reporting_rejects_unknown_scope_context(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    with pytest.raises(CyberOSError) as error:
        ReconReportingService(factory).target_recon_summary(ReconReportContext(ScopeId(uuid4())))
    assert error.value.code is ErrorCode.REPORT_QUERY_INVALID


def test_header_allowlist_rejects_credentials_and_parameter_values(tmp_path: Path) -> None:
    with pytest.raises(CyberOSError) as header_error:
        OfflineWebApiStep(
            "headers",
            OfflineWebApiStepKind.SYNTHETIC_RESPONSE_HEADERS,
            safe_headers=(("Authorization", "Bearer forbidden"),),
        )
    assert header_error.value.code is ErrorCode.OFFLINE_FIXTURE_INVALID

    with pytest.raises(CyberOSError) as parameter_error:
        OfflineWebApiStep(
            "parameters",
            OfflineWebApiStepKind.PARAMETER_NAME_DISCOVERY,
            parameters=(("page", "value"),),
        )
    assert parameter_error.value.code is ErrorCode.OFFLINE_FIXTURE_INVALID


def test_partial_failure_preserves_endpoint_but_discards_later_evidence(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    base = MultiWebApiOfflineScenario(now=NOW)
    steps = (
        base.steps[0],
        OfflineWebApiStep(
            "headers",
            OfflineWebApiStepKind.SYNTHETIC_RESPONSE_HEADERS,
            safe_headers=(("content-type", "application/json"),),
            fail=True,
        ),
        base.steps[2],
    )
    result = MultiWebApiOfflineHarness(factory).run(
        MultiWebApiOfflineScenario(steps=steps, now=NOW)
    )
    assert result.report.status.value == "failed"
    assert result.evidence == ()
    with SQLiteUnitOfWork(factory) as unit:
        assets = SQLiteReconRepository(unit).list_assets(
            result.task.scope_id, result.task.target_id
        )
        observations = tuple(
            observation
            for asset in assets
            for observation in SQLiteReconRepository(unit).list_observations(asset.id)
        )
        unit.rollback()
    assert len(assets) == 1
    assert len(observations) == 1


def test_cancel_before_ingest_preserves_prior_step_only(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    result = MultiWebApiOfflineHarness(factory).run(
        MultiWebApiOfflineScenario(now=NOW), cancel_after_step_id="headers"
    )
    assert result.report.status.value == "cancelled"
    assert result.evidence == ()
    with SQLiteUnitOfWork(factory) as unit:
        assets = SQLiteReconRepository(unit).list_assets(
            result.task.scope_id, result.task.target_id
        )
        observations = tuple(
            observation
            for asset in assets
            for observation in SQLiteReconRepository(unit).list_observations(asset.id)
        )
        unit.rollback()
    assert len(assets) == 1
    assert len(observations) == 1
