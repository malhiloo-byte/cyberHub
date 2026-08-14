"""Offline deterministic fixture plugin for Module 1.0 contract tests."""

from __future__ import annotations

from cyberos.core.errors import ErrorCode
from cyberos.domain.target.primitives import TargetKind
from cyberos.recon.contracts import (
    PluginCapability,
    PluginDeclaredLimits,
    PluginInvocation,
    PluginManifest,
    PluginRequirements,
    ReconError,
    ReconObservation,
    ReconPlugin,
    ReconResult,
)


class OfflineFixturePlugin(ReconPlugin):
    """Pure in-process fixture with fixed output and no side effects."""

    @property
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            plugin_id="fixture.offline",
            display_name="Offline Deterministic Fixture",
            description="A pure fixture used to prove the Module 1.0 plugin contract.",
            plugin_version="1.0.0",
            contract_version="1.0",
            capabilities=(PluginCapability.OFFLINE_DETERMINISTIC,),
            supported_target_kinds=(TargetKind.FQDN,),
            requirements=PluginRequirements(),
            declared_limits=PluginDeclaredLimits(
                max_input_bytes=4_096,
                max_output_bytes=16_384,
                max_observations=8,
                timeout_seconds=5,
            ),
        )

    def execute(self, invocation: PluginInvocation) -> ReconResult:
        candidate = invocation.input.candidate
        if candidate.raw_value == "fixture.failure":
            return ReconResult.failure(
                task_id=invocation.task.id,
                scope_id=invocation.input.scope_id,
                target_id=invocation.input.target_id,
                plugin_id=self.manifest.plugin_id,
                plugin_version=self.manifest.plugin_version,
                contract_version=self.manifest.contract_version,
                errors=(
                    ReconError(
                        code=ErrorCode.PLUGIN_EXECUTION_FAILED,
                        message="Offline fixture rejected the deterministic failure case.",
                        field="candidate",
                    ),
                ),
            )
        return ReconResult.success(
            task_id=invocation.task.id,
            scope_id=invocation.input.scope_id,
            target_id=invocation.input.target_id,
            plugin_id=self.manifest.plugin_id,
            plugin_version=self.manifest.plugin_version,
            contract_version=self.manifest.contract_version,
            observations=(
                ReconObservation("fixture.candidate", candidate.raw_value),
                ReconObservation("fixture.kind", candidate.kind.value),
            ),
        )
