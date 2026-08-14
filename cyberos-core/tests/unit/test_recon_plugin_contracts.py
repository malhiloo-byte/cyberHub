from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cyberos.application.scope_validation import ExecutionAuthorization, TargetCandidate
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.scope.primitives import new_scope_id
from cyberos.domain.target.primitives import TargetKind, TargetRule, new_target_id
from cyberos.domain.task.model import Task
from cyberos.domain.task.spec import ExecutionSpec
from cyberos.recon.contracts import (
    PluginCapability,
    PluginDeclaredLimits,
    PluginInvocation,
    PluginManifest,
    PluginRequirements,
    ReconObservation,
    ReconResult,
    ReconStatus,
)
from cyberos.recon.fixture import OfflineFixturePlugin
from cyberos.recon.host import PluginHost

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def build_execution_context(
    *,
    raw_value: str = "fixture.success",
    kind: TargetKind = TargetKind.FQDN,
    expires_at: datetime | None = None,
) -> tuple[Task, ExecutionAuthorization, TargetCandidate]:
    scope_id = new_scope_id()
    target_id = new_target_id()
    candidate = TargetCandidate(raw_value=raw_value, kind=kind)
    authorization = ExecutionAuthorization(
        scope_id=scope_id,
        candidate=candidate,
        authorized_at=NOW,
        expires_at=expires_at,
        matched_target_id=target_id,
        matching_rule=TargetRule.INCLUDE,
        reason="test_authorization",
        scope_version=1,
    )
    task = Task.create(
        scope_id=scope_id,
        target_id=target_id,
        authorization=authorization,
        execution_spec=ExecutionSpec(
            command=("fixture",), timeout_seconds=5, max_output_bytes=4_096
        ),
        now=NOW,
    )
    return task, authorization, candidate


def manifest(
    *,
    plugin_id: str = "test.plugin",
    contract_version: str = "1.0",
    capabilities: tuple[PluginCapability, ...] = (PluginCapability.OFFLINE_DETERMINISTIC,),
    target_kinds: tuple[TargetKind, ...] = (TargetKind.FQDN,),
    requirements: PluginRequirements | None = None,
    limits: PluginDeclaredLimits | None = None,
) -> PluginManifest:
    return PluginManifest(
        plugin_id=plugin_id,
        display_name="Test Plugin",
        description="Contract test plugin",
        plugin_version="1.0.0",
        contract_version=contract_version,
        capabilities=capabilities,
        supported_target_kinds=target_kinds,
        requirements=requirements or PluginRequirements(),
        declared_limits=limits or PluginDeclaredLimits(),
    )


class StaticPlugin:
    def __init__(self, plugin_manifest: PluginManifest) -> None:
        self._manifest = plugin_manifest

    @property
    def manifest(self) -> PluginManifest:
        return self._manifest

    def execute(self, invocation: PluginInvocation) -> ReconResult:
        return ReconResult.success(
            task_id=invocation.task.id,
            scope_id=invocation.input.scope_id,
            target_id=invocation.input.target_id,
            plugin_id=self.manifest.plugin_id,
            plugin_version=self.manifest.plugin_version,
            contract_version=self.manifest.contract_version,
            observations=(ReconObservation("test.ok", "yes"),),
        )


class OversizedPlugin(StaticPlugin):
    def execute(self, invocation: PluginInvocation) -> ReconResult:
        return ReconResult.success(
            task_id=invocation.task.id,
            scope_id=invocation.input.scope_id,
            target_id=invocation.input.target_id,
            plugin_id=self.manifest.plugin_id,
            plugin_version=self.manifest.plugin_version,
            contract_version=self.manifest.contract_version,
            observations=tuple(ReconObservation("test.item", str(index)) for index in range(9)),
        )


def test_manifest_is_immutable_canonical_and_rejects_invalid_identity() -> None:
    value = manifest(capabilities=(PluginCapability.OFFLINE_DETERMINISTIC,))
    assert value.capabilities == (PluginCapability.OFFLINE_DETERMINISTIC,)
    with pytest.raises(CyberOSError) as captured:
        manifest(plugin_id="Invalid Plugin")
    assert captured.value.code is ErrorCode.PLUGIN_MANIFEST_INVALID
    with pytest.raises((TypeError, AttributeError)):
        value.plugin_id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        (
            {"plugin_id": "a", "capabilities": (PluginCapability.OFFLINE_DETERMINISTIC,) * 2},
            ErrorCode.PLUGIN_MANIFEST_INVALID,
        ),
        ({"plugin_id": "a", "contract_version": "1.0.0"}, ErrorCode.PLUGIN_MANIFEST_INVALID),
        ({"plugin_id": "a", "target_kinds": ()}, ErrorCode.PLUGIN_MANIFEST_INVALID),
        (
            {
                "plugin_id": "a",
                "capabilities": (PluginCapability.OFFLINE_DETERMINISTIC,),
                "requirements": PluginRequirements(network=True),
            },
            ErrorCode.PLUGIN_MANIFEST_INVALID,
        ),
    ],
)
def test_manifest_rejects_invalid_declarations(kwargs: dict[str, object], code: ErrorCode) -> None:
    with pytest.raises(CyberOSError) as captured:
        manifest(**kwargs)  # type: ignore[arg-type]
    assert captured.value.code is code


def test_host_is_deny_by_default_and_validates_contract_version() -> None:
    host = PluginHost()
    with pytest.raises(CyberOSError) as denied:
        host.register(StaticPlugin(manifest(capabilities=(PluginCapability.NETWORK_DNS,))))
    assert denied.value.code is ErrorCode.PLUGIN_CAPABILITY_DENIED
    with pytest.raises(CyberOSError) as incompatible:
        PluginHost(host_contract_version="1.0").register(
            StaticPlugin(manifest(contract_version="1.1"))
        )
    assert incompatible.value.code is ErrorCode.PLUGIN_CONTRACT_UNSUPPORTED


def test_fixture_success_is_structured_and_deterministic() -> None:
    task, authorization, candidate = build_execution_context()
    from cyberos.recon.contracts import ReconInput

    input_value = ReconInput(scope_id=task.scope_id, target_id=task.target_id, candidate=candidate)
    host = PluginHost()
    host.register(OfflineFixturePlugin())
    first = host.invoke(
        "fixture.offline", task=task, authorization=authorization, input=input_value, now=NOW
    )
    second = host.invoke(
        "fixture.offline", task=task, authorization=authorization, input=input_value, now=NOW
    )
    assert first.status is ReconStatus.SUCCESS
    assert first.errors == ()
    assert first.to_json() == second.to_json()
    assert [item.observation_type for item in first.observations] == [
        "fixture.candidate",
        "fixture.kind",
    ]


def test_fixture_controlled_failure_is_typed() -> None:
    task, authorization, candidate = build_execution_context(raw_value="fixture.failure")
    from cyberos.recon.contracts import ReconInput

    host = PluginHost()
    host.register(OfflineFixturePlugin())
    result = host.invoke(
        "fixture.offline",
        task=task,
        authorization=authorization,
        input=ReconInput(scope_id=task.scope_id, target_id=task.target_id, candidate=candidate),
        now=NOW,
    )
    assert result.status is ReconStatus.FAILURE
    assert result.errors[0].code is ErrorCode.PLUGIN_EXECUTION_FAILED


def test_invocation_is_host_created_and_frozen() -> None:
    task, authorization, candidate = build_execution_context()
    from cyberos.recon.contracts import ReconInput

    input_value = ReconInput(scope_id=task.scope_id, target_id=task.target_id, candidate=candidate)
    with pytest.raises(CyberOSError) as captured:
        PluginInvocation(
            plugin_id="bad",
            plugin_version="1.0.0",
            contract_version="1.0",
            task=task,
            authorization=authorization,
            input=input_value,
            effective_limits=PluginHost._effective_limits(
                task, OfflineFixturePlugin().manifest, input_value
            ),
        )
    assert captured.value.code is ErrorCode.PLUGIN_AUTHORIZATION_INVALID


@pytest.mark.parametrize("field", ["scope", "target", "candidate", "expiry"])
def test_authorization_binding_is_fail_closed(field: str) -> None:
    task, authorization, candidate = build_execution_context(expires_at=NOW + timedelta(minutes=5))
    from cyberos.recon.contracts import ReconInput

    if field == "scope":
        input_value = ReconInput(
            scope_id=new_scope_id(), target_id=task.target_id, candidate=candidate
        )
    elif field == "target":
        input_value = ReconInput(
            scope_id=task.scope_id, target_id=new_target_id(), candidate=candidate
        )
    elif field == "candidate":
        input_value = ReconInput(
            scope_id=task.scope_id,
            target_id=task.target_id,
            candidate=TargetCandidate("different.example", TargetKind.FQDN),
        )
    else:
        input_value = ReconInput(
            scope_id=task.scope_id, target_id=task.target_id, candidate=candidate
        )
    host = PluginHost()
    host.register(OfflineFixturePlugin())
    with pytest.raises(CyberOSError) as captured:
        host.invoke(
            "fixture.offline",
            task=task,
            authorization=authorization,
            input=input_value,
            now=NOW + timedelta(minutes=6) if field == "expiry" else NOW,
        )
    assert captured.value.code is ErrorCode.PLUGIN_AUTHORIZATION_INVALID


def test_unsupported_target_kind_and_oversized_result_are_rejected() -> None:
    task, authorization, candidate = build_execution_context(
        kind=TargetKind.IPV4, raw_value="127.0.0.1"
    )
    from cyberos.recon.contracts import ReconInput

    host = PluginHost()
    host.register(OfflineFixturePlugin())
    with pytest.raises(CyberOSError) as kind_error:
        host.invoke(
            "fixture.offline",
            task=task,
            authorization=authorization,
            input=ReconInput(scope_id=task.scope_id, target_id=task.target_id, candidate=candidate),
            now=NOW,
        )
    assert kind_error.value.code is ErrorCode.PLUGIN_INPUT_INVALID

    oversized_host = PluginHost()
    oversized_host.register(
        OversizedPlugin(
            manifest(
                plugin_id="test.oversized",
                limits=PluginDeclaredLimits(max_observations=8, max_output_bytes=16_384),
            )
        )
    )
    task, authorization, candidate = build_execution_context()
    with pytest.raises(CyberOSError) as result_error:
        oversized_host.invoke(
            "test.oversized",
            task=task,
            authorization=authorization,
            input=ReconInput(scope_id=task.scope_id, target_id=task.target_id, candidate=candidate),
            now=NOW,
        )
    assert result_error.value.code is ErrorCode.PLUGIN_LIMIT_EXCEEDED


def test_recon_package_has_no_forbidden_side_effect_imports_or_calls() -> None:
    import ast

    package_dir = Path(__file__).parents[2] / "src" / "cyberos" / "recon"
    forbidden_modules = {"socket", "subprocess", "requests", "httpx", "urllib", "dns", "random"}
    forbidden_calls = {
        "system",
        "popen",
        "run",
        "Popen",
        "create_subprocess_exec",
        "create_subprocess_shell",
    }
    for path in package_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(
                    alias.name.split(".")[0] not in forbidden_modules for alias in node.names
                )
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                assert node.module.split(".")[0] not in forbidden_modules
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_calls
