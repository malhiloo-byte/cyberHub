from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.time import ensure_utc
from cyberos.domain.task.result import ExecutionFailureReason, ExecutionResult

if TYPE_CHECKING:
    from cyberos.recon.pipeline import PipelineExecutionReport


class ReconTaskResultAdapter:
    """Maps a pipeline report to the existing Task execution projection.

    stdout is a bounded Pipeline Summary JSON document, never a subprocess
    stream. stderr contains only a redacted typed failure summary.
    """

    @staticmethod
    def from_pipeline_report(
        report: PipelineExecutionReport,
        *,
        started_at: datetime,
        finished_at: datetime,
    ) -> ExecutionResult:
        start = ensure_utc(started_at)
        finish = ensure_utc(finished_at)
        duration_seconds = (finish - start).total_seconds()
        if duration_seconds < 0:
            raise ValueError("Pipeline finish time cannot precede start time.")
        summary = {
            "pipeline_id": report.pipeline_id,
            "pipeline_version": report.pipeline_version,
            "status": report.status.value,
            "committed_assets_count": report.committed_asset_count,
            "committed_observations_count": report.committed_observation_count,
            "step_receipts_summary": [
                {
                    "step_id": receipt.step_id,
                    "plugin_id": receipt.plugin_id,
                    "status": receipt.status,
                    "committed_assets": receipt.committed_assets,
                    "committed_observations": receipt.committed_observations,
                }
                for receipt in report.step_receipts
            ],
        }
        stdout = json.dumps(
            summary, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        if len(stdout) > report.task.execution_spec.max_output_bytes:
            raise CyberOSError(
                ErrorCode.PLUGIN_LIMIT_EXCEEDED,
                "Pipeline summary exceeds the Task output limit.",
            )
        from cyberos.recon.pipeline import PipelineStatus

        if report.status is PipelineStatus.COMPLETED:
            return ExecutionResult(
                exit_code=0,
                stdout=stdout,
                stderr=b"",
                truncated=False,
                duration_seconds=duration_seconds,
                timeout_exceeded=report.timeout_exceeded,
                error_message=None,
            )
        if report.status is PipelineStatus.CANCELLED:
            error_message = "Pipeline cancelled safely."
            return ExecutionResult(
                exit_code=130,
                stdout=stdout,
                stderr=error_message.encode("utf-8"),
                truncated=False,
                duration_seconds=duration_seconds,
                timeout_exceeded=report.timeout_exceeded,
                failure_reason=(
                    ExecutionFailureReason.TIMEOUT_EXCEEDED if report.timeout_exceeded else None
                ),
                error_message=error_message,
            )
        failure = report.failure
        code = failure.code if failure is not None else "PIPELINE_FAILED"
        error_message = f"{code}: pipeline step failed safely."
        return ExecutionResult(
            exit_code=1,
            stdout=stdout,
            stderr=error_message.encode("utf-8"),
            truncated=False,
            duration_seconds=duration_seconds,
            timeout_exceeded=report.timeout_exceeded,
            failure_reason=(
                ExecutionFailureReason.TIMEOUT_EXCEEDED if report.timeout_exceeded else None
            ),
            error_message=error_message,
        )
