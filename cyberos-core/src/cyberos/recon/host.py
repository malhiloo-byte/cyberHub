"""Registry and host boundary for Module 1.0 recon plugins."""

from __future__ import annotations

from datetime import datetime

from cyberos.application.scope_validation import ExecutionAuthorization
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.time import ensure_utc, utc_now
from cyberos.domain.target.primitives import TargetRule
from cyberos.domain.task.model import Task
from cyberos.domain.task.primitives import TaskStatus
from cyberos.recon.contracts import (
    ExecutionLimits,
    PluginCapability,
    PluginManifest,
    ReconInput,
    ReconPlugin,
    ReconResult,
    create_host_invocation,
    validate_contract_compatibility,
)


class PluginHost:
    """Deny-by-default registry and invocation boundary."""

    def __init__(
        self,
        *,
        host_contract_version: str = "1.0",
        allowed_capabilities: frozenset[PluginCapability] | None = None,
    ) -> None:
        self.host_contract_version = host_contract_version
        self.allowed_capabilities = (
            allowed_capabilities
            if allowed_capabilities is not None
            else frozenset({PluginCapability.OFFLINE_DETERMINISTIC})
        )
        self._plugins: dict[str, ReconPlugin] = {}

    def register(self, plugin: ReconPlugin) -> PluginManifest:
        if not isinstance(plugin, ReconPlugin):
            raise CyberOSError(
                ErrorCode.PLUGIN_MANIFEST_INVALID, "Plugin does not implement ReconPlugin."
            )
        try:
            manifest = plugin.manifest
        except Exception as exc:
            raise CyberOSError(
                ErrorCode.PLUGIN_MANIFEST_INVALID, "Plugin manifest could not be read."
            ) from exc
        if not isinstance(manifest, PluginManifest):
            raise CyberOSError(
                ErrorCode.PLUGIN_MANIFEST_INVALID, "Plugin manifest has an invalid type."
            )
        validate_contract_compatibility(manifest.contract_version, self.host_contract_version)
        denied = set(manifest.capabilities).difference(self.allowed_capabilities)
        if denied:
            raise CyberOSError(
                ErrorCode.PLUGIN_CAPABILITY_DENIED,
                "Plugin declares capabilities denied by the active host policy.",
                details={"capabilities": sorted(value.value for value in denied)},
            )
        if manifest.plugin_id in self._plugins:
            raise CyberOSError(
                ErrorCode.PLUGIN_DUPLICATE_ID, "Plugin identity is already registered."
            )
        self._plugins[manifest.plugin_id] = plugin
        return manifest

    def get_manifest(self, plugin_id: str) -> PluginManifest:
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            raise CyberOSError(ErrorCode.PLUGIN_NOT_READY, "Plugin is not registered.")
        return plugin.manifest

    def invoke(
        self,
        plugin_id: str,
        *,
        task: Task,
        authorization: ExecutionAuthorization,
        input: ReconInput,
        now: datetime | None = None,
    ) -> ReconResult:
        return self._invoke(
            plugin_id,
            task=task,
            authorization=authorization,
            input=input,
            now=now,
            allow_running=False,
        )

    def invoke_running(
        self,
        plugin_id: str,
        *,
        task: Task,
        authorization: ExecutionAuthorization,
        input: ReconInput,
        now: datetime | None = None,
    ) -> ReconResult:
        """Internal orchestration route for an already-running Task.

        This is additive: the public legacy `invoke` route remains pending-only.
        All other host validation, capability, identity, expiry, and limit checks
        are shared with the legacy route.
        """

        return self._invoke(
            plugin_id,
            task=task,
            authorization=authorization,
            input=input,
            now=now,
            allow_running=True,
        )

    def _invoke(
        self,
        plugin_id: str,
        *,
        task: Task,
        authorization: ExecutionAuthorization,
        input: ReconInput,
        now: datetime | None,
        allow_running: bool,
    ) -> ReconResult:
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            raise CyberOSError(ErrorCode.PLUGIN_NOT_READY, "Plugin is not registered.")
        manifest = plugin.manifest
        timestamp = ensure_utc(now) if now is not None else utc_now()
        self._validate_binding(manifest, task, authorization, input, timestamp, allow_running)
        limits = self._effective_limits(task, manifest, input)
        invocation = create_host_invocation(
            plugin_id=manifest.plugin_id,
            plugin_version=manifest.plugin_version,
            contract_version=manifest.contract_version,
            task=task,
            authorization=authorization,
            input=input,
            effective_limits=limits,
        )
        try:
            result = plugin.execute(invocation)
        except CyberOSError:
            raise
        except Exception as exc:
            raise CyberOSError(
                ErrorCode.PLUGIN_EXECUTION_FAILED,
                "Plugin execution failed safely at the host boundary.",
            ) from exc
        self._validate_result(result, manifest, task, input, limits)
        return result

    @staticmethod
    def _validate_binding(
        manifest: PluginManifest,
        task: Task,
        authorization: ExecutionAuthorization,
        input: ReconInput,
        now: datetime,
        allow_running: bool = False,
    ) -> None:
        if input.candidate.kind not in manifest.supported_target_kinds:
            raise CyberOSError(
                ErrorCode.PLUGIN_INPUT_INVALID, "Plugin does not support this TargetKind."
            )
        if task.status is not TaskStatus.PENDING and not (
            allow_running and task.status is TaskStatus.RUNNING
        ):
            raise CyberOSError(
                ErrorCode.PLUGIN_AUTHORIZATION_INVALID, "Plugin invocation requires a pending Task."
            )
        if task.scope_id != authorization.scope_id or task.scope_id != input.scope_id:
            raise CyberOSError(
                ErrorCode.PLUGIN_AUTHORIZATION_INVALID, "Plugin Scope binding is inconsistent."
            )
        if task.target_id != authorization.matched_target_id or task.target_id != input.target_id:
            raise CyberOSError(
                ErrorCode.PLUGIN_AUTHORIZATION_INVALID, "Plugin Target binding is inconsistent."
            )
        if authorization.candidate != input.candidate:
            raise CyberOSError(
                ErrorCode.PLUGIN_AUTHORIZATION_INVALID,
                "Plugin candidate is not authorization-bound.",
            )
        if authorization.matching_rule is not TargetRule.INCLUDE:
            raise CyberOSError(
                ErrorCode.PLUGIN_AUTHORIZATION_INVALID,
                "Plugin invocation requires Include authorization.",
            )
        if authorization.expires_at is not None and authorization.expires_at <= now:
            raise CyberOSError(
                ErrorCode.PLUGIN_AUTHORIZATION_INVALID, "ExecutionAuthorization has expired."
            )
        if task.authorization_expires_at != authorization.expires_at:
            raise CyberOSError(
                ErrorCode.PLUGIN_AUTHORIZATION_INVALID, "Task authorization expiry does not match."
            )

    @staticmethod
    def _effective_limits(
        task: Task, manifest: PluginManifest, input: ReconInput
    ) -> ExecutionLimits:
        task_spec = task.execution_spec
        declared = manifest.declared_limits
        candidate_size = len(input.candidate.raw_value.encode("utf-8"))
        parameter_size = sum(
            len(key.encode("utf-8")) + len(value.encode("utf-8")) for key, value in input.parameters
        )
        input_size = candidate_size + parameter_size
        limits = ExecutionLimits(
            timeout_seconds=min(task_spec.timeout_seconds, declared.timeout_seconds),
            max_input_bytes=declared.max_input_bytes,
            max_output_bytes=min(task_spec.max_output_bytes, declared.max_output_bytes),
            max_observations=declared.max_observations,
        )
        if input_size > limits.max_input_bytes:
            raise CyberOSError(
                ErrorCode.PLUGIN_LIMIT_EXCEEDED, "Plugin input exceeds the effective input limit."
            )
        return limits

    @staticmethod
    def _validate_result(
        result: ReconResult,
        manifest: PluginManifest,
        task: Task,
        input: ReconInput,
        limits: ExecutionLimits,
    ) -> None:
        if not isinstance(result, ReconResult):
            raise CyberOSError(
                ErrorCode.PLUGIN_RESULT_INVALID, "Plugin returned an invalid result type."
            )
        if (
            result.task_id != task.id
            or result.scope_id != input.scope_id
            or result.target_id != input.target_id
        ):
            raise CyberOSError(
                ErrorCode.PLUGIN_RESULT_INVALID, "Plugin result identity does not match invocation."
            )
        if (
            result.plugin_id != manifest.plugin_id
            or result.plugin_version != manifest.plugin_version
        ):
            raise CyberOSError(
                ErrorCode.PLUGIN_RESULT_INVALID,
                "Plugin result version identity does not match manifest.",
            )
        if result.contract_version != manifest.contract_version:
            raise CyberOSError(
                ErrorCode.PLUGIN_RESULT_INVALID,
                "Plugin result contract version does not match manifest.",
            )
        result.validate_within(limits)
