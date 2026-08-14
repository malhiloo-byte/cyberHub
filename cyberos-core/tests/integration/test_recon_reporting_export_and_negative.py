from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cyberos.application.offline_web_api import (
    MultiWebApiOfflineHarness,
    MultiWebApiOfflineScenario,
)
from cyberos.application.offline_web_api_negative import (
    MultiWebApiNegativeHarness,
    MultiWebApiNegativeScenario,
    OfflineNegativeCaseKind,
)
from cyberos.application.recon_reporting_export import ReconReportingExportService
from cyberos.config.models import DatabaseSettings
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.recon.report_export import ExportContext, ExportKind, ReconReportExportRequest
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.migrations.runner import MigrationRunner
from cyberos.persistence.recon_evidence_repository import SQLiteReconEvidenceRepository
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork

MIGRATIONS_DIR = Path(__file__).parents[2] / "src/cyberos/persistence/migrations/versions"
NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


def factory_for(tmp_path: Path) -> SQLiteConnectionFactory:
    factory = SQLiteConnectionFactory(DatabaseSettings(path=tmp_path / "cyberos.sqlite3"))
    MigrationRunner(factory, MIGRATIONS_DIR).run()
    return factory


def test_json_export_is_canonical_deterministic_and_in_memory(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    workflow = MultiWebApiOfflineHarness(factory).run(MultiWebApiOfflineScenario(now=NOW))
    service = ReconReportingExportService(factory, clock=lambda: NOW)
    context = ExportContext(workflow.task.scope_id, workflow.task.target_id, workflow.task.id)
    snapshot = service.snapshot(context)
    export = service.export_json(ReconReportExportRequest(context, ExportKind.JSON), snapshot)
    encoded = service.serialize_json(export)

    parsed = json.loads(encoded)
    assert parsed["completeness"] == "complete"
    assert parsed["source_fingerprint"] == snapshot.source_fingerprint
    assert len(parsed["export_digest"]) == 64
    assert encoded == json.dumps(parsed, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    assert len(encoded.encode("utf-8")) <= 262_144


def test_structured_summary_is_renderer_neutral_and_has_closed_sections(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    workflow = MultiWebApiOfflineHarness(factory).run(MultiWebApiOfflineScenario(now=NOW))
    service = ReconReportingExportService(factory, clock=lambda: NOW)
    context = ExportContext(workflow.task.scope_id, workflow.task.target_id, workflow.task.id)
    snapshot = service.snapshot(context)
    presentation = service.structured_summary(
        ReconReportExportRequest(context, ExportKind.STRUCTURED_SUMMARY), snapshot
    )
    assert tuple(section.section_id.value for section in presentation.sections) == (
        "target_recon",
        "asset_distribution",
        "provenance_audit",
    )
    assert presentation.redaction_applied is True
    assert not hasattr(presentation, "path")


def test_export_context_mismatch_and_byte_overflow_fail_closed(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    workflow = MultiWebApiOfflineHarness(factory).run(MultiWebApiOfflineScenario(now=NOW))
    service = ReconReportingExportService(factory, clock=lambda: NOW)
    context = ExportContext(workflow.task.scope_id, workflow.task.target_id, workflow.task.id)
    snapshot = service.snapshot(context)
    with pytest.raises(CyberOSError) as context_error:
        service.export_json(
            ReconReportExportRequest(ExportContext(workflow.task.scope_id), ExportKind.JSON),
            snapshot,
        )
    assert context_error.value.code is ErrorCode.REPORT_EXPORT_CONTEXT_INVALID
    with pytest.raises(CyberOSError) as size_error:
        service.export_json(
            ReconReportExportRequest(context, ExportKind.JSON, max_export_bytes=1), snapshot
        )
    assert size_error.value.code is ErrorCode.REPORT_EXPORT_SIZE_EXCEEDED


def test_export_does_not_mutate_task_or_write_files(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    workflow = MultiWebApiOfflineHarness(factory).run(MultiWebApiOfflineScenario(now=NOW))
    service = ReconReportingExportService(factory, clock=lambda: NOW)
    context = ExportContext(workflow.task.scope_id, workflow.task.target_id, workflow.task.id)
    snapshot = service.snapshot(context)
    export = service.export_json(ReconReportExportRequest(context, ExportKind.JSON), snapshot)
    with pytest.raises(TypeError):
        export.payload["new_field"] = "forbidden"  # type: ignore[index]
    assert workflow.task.status.value == "completed"
    assert not list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("case_kind", "expected_status"),
    (
        (OfflineNegativeCaseKind.SYNTHETIC_RATE_LIMIT_429, 429),
        (OfflineNegativeCaseKind.SYNTHETIC_AUTHENTICATION_REJECTION_401, 401),
        (OfflineNegativeCaseKind.SYNTHETIC_AUTHORIZATION_REJECTION_403, 403),
        (OfflineNegativeCaseKind.UNEXPECTED_PAYLOAD_SHAPE, None),
    ),
)
def test_negative_fixture_receipts_preserve_prior_step_and_create_no_evidence(
    tmp_path: Path, case_kind: OfflineNegativeCaseKind, expected_status: int | None
) -> None:
    factory = factory_for(tmp_path)
    result = MultiWebApiNegativeHarness(factory).run(
        MultiWebApiNegativeScenario(case_kind=case_kind, now=NOW)
    )
    assert result.report.status.value == "failed"
    assert result.receipt.synthetic is True
    assert result.receipt.offline_fixture is True
    assert result.receipt.expected_status_code == expected_status
    assert result.receipt.committed_assets_before == 1
    assert result.receipt.committed_assets_after == 1
    assert result.receipt.committed_observations_before == 1
    assert result.receipt.committed_observations_after == 1
    with SQLiteUnitOfWork(factory) as unit:
        evidence = SQLiteReconEvidenceRepository(unit).list_by_task(result.task.id)
        unit.rollback()
    assert evidence == ()


def test_negative_parameter_boundary_fails_before_workflow_and_never_echoes_value(
    tmp_path: Path,
) -> None:
    with pytest.raises(CyberOSError) as error:
        MultiWebApiNegativeScenario(
            case_kind=OfflineNegativeCaseKind.PARAMETER_BOUNDARY_FAILURE,
            parameter_name="",
            now=NOW,
        )
    assert error.value.code is ErrorCode.OFFLINE_NEGATIVE_PARAMETER_INVALID
    assert error.value.message == "Synthetic parameter name boundary is invalid."
    assert list(tmp_path.iterdir()) == []
