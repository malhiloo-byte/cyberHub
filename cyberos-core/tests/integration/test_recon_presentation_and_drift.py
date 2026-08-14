"""Module 1.7 presentation and schema-drift integration/security tests."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from cyberos.application.offline_web_api import (
    MultiWebApiOfflineHarness,
    MultiWebApiOfflineScenario,
)
from cyberos.application.offline_web_api_drift import MultiWebApiSchemaDriftHarness
from cyberos.application.recon_export_presentation import ReconExportPresentationService
from cyberos.config.models import DatabaseSettings
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.recon.presentation import (
    PresentationMetricClassification,
    PresentationMetricView,
    PresentationSectionId,
    PresentationSectionView,
    PresentationViewKind,
    ReconPresentationRequest,
    ReconPresentationView,
)
from cyberos.domain.recon.report_export import ExportContext, ExportKind, ReconReportExportRequest
from cyberos.domain.recon.schema_drift import (
    ContractShiftKind,
    EnvelopeKind,
    MultiWebApiSchemaDriftScenario,
    SchemaDriftCaseKind,
)
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


def workflow_export(
    tmp_path: Path,
) -> tuple[SQLiteConnectionFactory, ExportContext, object, object]:
    factory = factory_for(tmp_path)
    workflow = MultiWebApiOfflineHarness(factory).run(MultiWebApiOfflineScenario(now=NOW))
    context = ExportContext(workflow.task.scope_id, workflow.task.target_id, workflow.task.id)
    from cyberos.application.recon_reporting_export import ReconReportingExportService

    exporter = ReconReportingExportService(factory, clock=lambda: NOW)
    snapshot = exporter.snapshot(context)
    json_export = exporter.export_json(ReconReportExportRequest(context, ExportKind.JSON), snapshot)
    structured = exporter.structured_summary(
        ReconReportExportRequest(context, ExportKind.STRUCTURED_SUMMARY), snapshot
    )
    return factory, context, json_export, structured


def test_presentation_adapters_propagate_integrity_and_remain_renderer_neutral(
    tmp_path: Path,
) -> None:
    _, context, json_export, structured = workflow_export(tmp_path)
    service = ReconExportPresentationService()
    json_view = service.present(
        ReconPresentationRequest(context, PresentationViewKind.SUMMARY), json_export
    )
    structured_view = service.present(
        ReconPresentationRequest(context, PresentationViewKind.AUDIT_SUMMARY), structured
    )

    assert json_view.source_fingerprint == json_export.source_fingerprint
    assert json_view.export_digest == json_export.export_digest
    assert structured_view.source_fingerprint == structured.source_fingerprint
    assert len(structured_view.export_digest) == 64
    assert structured_view.redaction_applied is True
    assert tuple(section.section_id for section in json_view.sections) == (
        PresentationSectionId.TARGET_RECON,
        PresentationSectionId.ASSET_DISTRIBUTION,
        PresentationSectionId.PROVENANCE_AUDIT,
    )
    assert not hasattr(json_view, "html")
    assert not hasattr(json_view, "path")
    assert not hasattr(json_view, "renderer")


def test_presentation_context_alignment_fails_closed(tmp_path: Path) -> None:
    _, context, json_export, _ = workflow_export(tmp_path)
    service = ReconExportPresentationService()
    mismatched = ReconPresentationRequest(
        ExportContext(context.scope_id), PresentationViewKind.SUMMARY
    )
    with pytest.raises(CyberOSError) as error:
        service.present(mismatched, json_export)
    assert error.value.code is ErrorCode.PRESENTATION_CONTEXT_INVALID


def test_presentation_budget_overflow_rejects_sections_and_metrics(tmp_path: Path) -> None:
    _, context, json_export, _ = workflow_export(tmp_path)
    service = ReconExportPresentationService()
    with pytest.raises(CyberOSError) as section_error:
        service.present(
            ReconPresentationRequest(context, PresentationViewKind.SUMMARY, max_sections=2),
            json_export,
        )
    assert section_error.value.code is ErrorCode.PRESENTATION_BUDGET_EXCEEDED
    with pytest.raises(CyberOSError) as metric_error:
        service.present(
            ReconPresentationRequest(
                context, PresentationViewKind.SUMMARY, max_metrics_per_section=2
            ),
            json_export,
        )
    assert metric_error.value.code is ErrorCode.PRESENTATION_BUDGET_EXCEEDED


def test_presentation_scalar_budget_is_fail_closed() -> None:
    metric = PresentationMetricView(
        "large",
        "Large metric",
        "x" * 65_537,
        PresentationMetricClassification.STATUS,
    )
    section = PresentationSectionView(
        PresentationSectionId.TARGET_RECON,
        "Target Recon",
        "Safe description",
        (metric,),
    )
    with pytest.raises(CyberOSError) as error:
        ReconPresentationView(
            "1.0",
            PresentationViewKind.SUMMARY,
            ExportContext(__import__("uuid").uuid4()),
            NOW,
            "Large view",
            (section,),
            "a" * 64,
            "b" * 64,
            "complete",
            True,
        )
    assert error.value.code is ErrorCode.PRESENTATION_BUDGET_EXCEEDED


@pytest.mark.parametrize(
    "case_kind",
    (
        SchemaDriftCaseKind.DEPRECATED_FIELD_REMOVED,
        SchemaDriftCaseKind.UNEXPECTED_CONTRACT_SHIFT,
        SchemaDriftCaseKind.SYNTHETIC_API_VERSION_MISMATCH,
        SchemaDriftCaseKind.STRUCTURAL_ENVELOPE_CHANGED,
    ),
)
def test_schema_drift_is_typed_offline_and_preserves_prior_state(
    tmp_path: Path, case_kind: SchemaDriftCaseKind
) -> None:
    scenario = MultiWebApiSchemaDriftScenario(
        scenario_id=f"offline.web.api.drift.{case_kind.value}",
        fixture_version="1.0.0",
        case_kind=case_kind,
        expected_schema_version="1.0",
        presented_schema_version="2.0"
        if case_kind is SchemaDriftCaseKind.SYNTHETIC_API_VERSION_MISMATCH
        else "1.0",
        expected_envelope=EnvelopeKind.DATA,
        presented_envelope=EnvelopeKind.RESULT
        if case_kind is SchemaDriftCaseKind.STRUCTURAL_ENVELOPE_CHANGED
        else EnvelopeKind.DATA,
        drift_marker=case_kind.value,
        contract_shift=ContractShiftKind.TYPE_CHANGED
        if case_kind is SchemaDriftCaseKind.UNEXPECTED_CONTRACT_SHIFT
        else None,
        now=NOW,
    )
    result = MultiWebApiSchemaDriftHarness(factory_for(tmp_path)).run(scenario)

    assert result.report.status.value == "failed"
    assert result.report.step_receipts[0].step_id == "prior"
    assert result.receipt.synthetic is True
    assert result.receipt.offline_fixture is True
    assert result.receipt.committed_assets_before == result.receipt.committed_assets_after == 1
    assert (
        result.receipt.committed_observations_before
        == result.receipt.committed_observations_after
        == 1
    )
    with SQLiteUnitOfWork(factory_for(tmp_path)) as unit:
        unit.rollback()


def test_drift_scenario_rejects_invalid_version_and_envelope_shapes() -> None:
    with pytest.raises(CyberOSError) as version_error:
        MultiWebApiSchemaDriftScenario(
            "invalid-version",
            "1.0.0",
            SchemaDriftCaseKind.SYNTHETIC_API_VERSION_MISMATCH,
            "1.0",
            "1.0",
            EnvelopeKind.DATA,
            EnvelopeKind.DATA,
            "version",
        )
    assert version_error.value.code is ErrorCode.SCHEMA_DRIFT_FIXTURE_INVALID
    with pytest.raises(CyberOSError) as envelope_error:
        MultiWebApiSchemaDriftScenario(
            "invalid-envelope",
            "1.0.0",
            SchemaDriftCaseKind.STRUCTURAL_ENVELOPE_CHANGED,
            "1.0",
            "1.0",
            EnvelopeKind.DATA,
            EnvelopeKind.DATA,
            "envelope",
        )
    assert envelope_error.value.code is ErrorCode.SCHEMA_DRIFT_FIXTURE_INVALID


def test_drift_harness_creates_no_evidence_for_rejected_step(tmp_path: Path) -> None:
    scenario = MultiWebApiSchemaDriftScenario(
        "offline.web.api.drift.evidence",
        "1.0.0",
        SchemaDriftCaseKind.DEPRECATED_FIELD_REMOVED,
        "1.0",
        "1.0",
        EnvelopeKind.DATA,
        EnvelopeKind.DATA,
        "required_field_removed",
        now=NOW,
    )
    factory = factory_for(tmp_path)
    result = MultiWebApiSchemaDriftHarness(factory).run(scenario)
    with SQLiteUnitOfWork(factory) as unit:
        evidence = SQLiteReconEvidenceRepository(unit).list_by_task(result.task.id)
        unit.rollback()
    assert evidence == ()
