"""Immutable, deterministic contracts for the Module 1.0 plugin boundary.

The host is the only component allowed to create a valid PluginInvocation. The
models in this module deliberately contain no network, process, filesystem, or
external-service behavior.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, TypeAlias, runtime_checkable
from uuid import UUID

from cyberos.application.scope_validation import ExecutionAuthorization, TargetCandidate
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.serialization import dumps
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.primitives import TargetId, TargetKind
from cyberos.domain.task.model import Task

PluginId: TypeAlias = str
SemVer: TypeAlias = str
ContractVersion: TypeAlias = str
ScalarValue: TypeAlias = str | int | float | bool | None

_PLUGIN_ID_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
_CONTRACT_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_OBSERVATION_TYPE_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_PARAMETER_KEY_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")


class PluginCapability(StrEnum):
    """Capabilities a plugin may declare; declaration is not permission."""

    OFFLINE_DETERMINISTIC = "offline.deterministic"
    NETWORK_DNS = "network.dns"
    NETWORK_HTTP = "network.http"
    PROCESS_EXEC = "process.exec"
    FILESYSTEM_READ = "filesystem.read"
    EXTERNAL_API = "external.api"
    AI_INFERENCE = "ai.inference"


class PluginErrorCode(StrEnum):
    """Public, stable error family for controlled plugin failures."""

    FIXTURE_INPUT_REJECTED = "FIXTURE_INPUT_REJECTED"


class ReconStatus(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


_PLUGIN_ERROR_CODES = frozenset(
    {
        ErrorCode.PLUGIN_MANIFEST_INVALID,
        ErrorCode.PLUGIN_CONTRACT_UNSUPPORTED,
        ErrorCode.PLUGIN_CAPABILITY_DENIED,
        ErrorCode.PLUGIN_INPUT_INVALID,
        ErrorCode.PLUGIN_AUTHORIZATION_INVALID,
        ErrorCode.PLUGIN_NOT_READY,
        ErrorCode.PLUGIN_EXECUTION_FAILED,
        ErrorCode.PLUGIN_RESULT_INVALID,
        ErrorCode.PLUGIN_LIMIT_EXCEEDED,
        ErrorCode.PLUGIN_DUPLICATE_ID,
    }
)


def _bounded_text(value: str, *, field: str, maximum: int, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise CyberOSError(ErrorCode.PLUGIN_MANIFEST_INVALID, f"{field} must be text.")
    normalized = value.strip()
    if not allow_empty and not normalized:
        raise CyberOSError(ErrorCode.PLUGIN_MANIFEST_INVALID, f"{field} cannot be empty.")
    if len(normalized) > maximum:
        raise CyberOSError(
            ErrorCode.PLUGIN_MANIFEST_INVALID,
            f"{field} cannot exceed {maximum} characters.",
            details={"field": field, "maximum": maximum},
        )
    return normalized


def _normalize_semver(value: str) -> str:
    normalized = _bounded_text(value, field="plugin_version", maximum=64)
    if _SEMVER_RE.fullmatch(normalized) is None:
        raise CyberOSError(
            ErrorCode.PLUGIN_MANIFEST_INVALID,
            "plugin_version must use semantic versioning MAJOR.MINOR.PATCH.",
        )
    return normalized


def _normalize_contract_version(value: str) -> str:
    normalized = _bounded_text(value, field="contract_version", maximum=16)
    if _CONTRACT_RE.fullmatch(normalized) is None:
        raise CyberOSError(
            ErrorCode.PLUGIN_MANIFEST_INVALID,
            "contract_version must use MAJOR.MINOR notation.",
        )
    return normalized


def _version_parts(value: str) -> tuple[int, int]:
    major, minor = value.split(".", maxsplit=1)
    return int(major), int(minor)


def validate_contract_compatibility(plugin_contract: str, host_contract: str) -> None:
    plugin = _version_parts(_normalize_contract_version(plugin_contract))
    host = _version_parts(_normalize_contract_version(host_contract))
    if plugin[0] != host[0] or plugin[1] > host[1]:
        raise CyberOSError(
            ErrorCode.PLUGIN_CONTRACT_UNSUPPORTED,
            "Plugin contract version is not supported by this host.",
            details={"plugin_contract": plugin_contract, "host_contract": host_contract},
        )


def _validate_uuid4(value: UUID, *, field: str) -> None:
    if not isinstance(value, UUID) or value.version != 4:
        raise CyberOSError(
            ErrorCode.PLUGIN_INPUT_INVALID,
            f"{field} must be a UUID4.",
            details={"field": field},
        )


@dataclass(frozen=True, slots=True)
class PluginRequirements:
    """Declared requirements; each still needs a host policy grant."""

    network: bool = False
    subprocess: bool = False
    filesystem: bool = False
    external_api: bool = False
    ai: bool = False

    def __post_init__(self) -> None:
        values = (self.network, self.subprocess, self.filesystem, self.external_api, self.ai)
        if not all(isinstance(value, bool) for value in values):
            raise CyberOSError(
                ErrorCode.PLUGIN_MANIFEST_INVALID, "Plugin requirements must be booleans."
            )


@dataclass(frozen=True, slots=True)
class PluginDeclaredLimits:
    """Plugin-owned ceilings; effective limits are always stricter host limits."""

    max_input_bytes: int = 65_536
    max_output_bytes: int = 1_048_576
    max_observations: int = 256
    timeout_seconds: int = 30

    def __post_init__(self) -> None:
        values = {
            "max_input_bytes": self.max_input_bytes,
            "max_output_bytes": self.max_output_bytes,
            "max_observations": self.max_observations,
            "timeout_seconds": self.timeout_seconds,
        }
        for field, value in values.items():
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise CyberOSError(
                    ErrorCode.PLUGIN_MANIFEST_INVALID,
                    f"{field} must be a positive integer.",
                )
        if self.max_output_bytes > 16_777_216:
            raise CyberOSError(
                ErrorCode.PLUGIN_MANIFEST_INVALID, "Plugin output ceiling is too large."
            )
        if self.timeout_seconds > 3_600:
            raise CyberOSError(
                ErrorCode.PLUGIN_MANIFEST_INVALID, "Plugin timeout ceiling is too large."
            )


@dataclass(frozen=True, slots=True)
class PluginManifest:
    """Validated immutable identity and capability declaration."""

    plugin_id: PluginId
    display_name: str
    description: str
    plugin_version: SemVer
    contract_version: ContractVersion
    capabilities: tuple[PluginCapability, ...]
    supported_target_kinds: tuple[TargetKind, ...]
    requirements: PluginRequirements = PluginRequirements()
    declared_limits: PluginDeclaredLimits = PluginDeclaredLimits()

    def __post_init__(self) -> None:
        plugin_id = _bounded_text(self.plugin_id, field="plugin_id", maximum=80)
        if _PLUGIN_ID_RE.fullmatch(plugin_id) is None:
            raise CyberOSError(
                ErrorCode.PLUGIN_MANIFEST_INVALID, "plugin_id has an invalid format."
            )
        object.__setattr__(self, "plugin_id", plugin_id)
        object.__setattr__(
            self,
            "display_name",
            _bounded_text(self.display_name, field="display_name", maximum=120),
        )
        object.__setattr__(
            self,
            "description",
            _bounded_text(self.description, field="description", maximum=1_000, allow_empty=True),
        )
        object.__setattr__(self, "plugin_version", _normalize_semver(self.plugin_version))
        object.__setattr__(
            self, "contract_version", _normalize_contract_version(self.contract_version)
        )
        if not isinstance(self.requirements, PluginRequirements):
            raise CyberOSError(
                ErrorCode.PLUGIN_MANIFEST_INVALID, "requirements must be PluginRequirements."
            )
        if not isinstance(self.declared_limits, PluginDeclaredLimits):
            raise CyberOSError(
                ErrorCode.PLUGIN_MANIFEST_INVALID, "declared_limits must be PluginDeclaredLimits."
            )
        capabilities = self._canonical_capabilities(self.capabilities)
        target_kinds = self._canonical_target_kinds(self.supported_target_kinds)
        if not capabilities:
            raise CyberOSError(
                ErrorCode.PLUGIN_MANIFEST_INVALID, "At least one plugin capability is required."
            )
        if not target_kinds:
            raise CyberOSError(
                ErrorCode.PLUGIN_MANIFEST_INVALID, "At least one target kind is required."
            )
        self._validate_requirements(capabilities, self.requirements)
        object.__setattr__(self, "capabilities", capabilities)
        object.__setattr__(self, "supported_target_kinds", target_kinds)

    @staticmethod
    def _canonical_capabilities(
        values: tuple[PluginCapability, ...],
    ) -> tuple[PluginCapability, ...]:
        if not isinstance(values, tuple) or any(
            not isinstance(value, PluginCapability) for value in values
        ):
            raise CyberOSError(
                ErrorCode.PLUGIN_MANIFEST_INVALID, "capabilities must be a tuple of known values."
            )
        if len(set(values)) != len(values):
            raise CyberOSError(ErrorCode.PLUGIN_MANIFEST_INVALID, "capabilities must be unique.")
        return tuple(sorted(values, key=lambda value: value.value))

    @staticmethod
    def _canonical_target_kinds(values: tuple[TargetKind, ...]) -> tuple[TargetKind, ...]:
        if not isinstance(values, tuple) or any(
            not isinstance(value, TargetKind) for value in values
        ):
            raise CyberOSError(
                ErrorCode.PLUGIN_MANIFEST_INVALID,
                "supported_target_kinds contains an unknown kind.",
            )
        if len(set(values)) != len(values):
            raise CyberOSError(
                ErrorCode.PLUGIN_MANIFEST_INVALID, "supported_target_kinds must be unique."
            )
        return tuple(sorted(values, key=lambda value: value.value))

    @staticmethod
    def _validate_requirements(
        capabilities: tuple[PluginCapability, ...], requirements: PluginRequirements
    ) -> None:
        capability_values = set(capabilities)
        required = (
            (
                requirements.network,
                {PluginCapability.NETWORK_DNS, PluginCapability.NETWORK_HTTP},
                "network",
            ),
            (requirements.subprocess, {PluginCapability.PROCESS_EXEC}, "subprocess"),
            (requirements.filesystem, {PluginCapability.FILESYSTEM_READ}, "filesystem"),
            (requirements.external_api, {PluginCapability.EXTERNAL_API}, "external_api"),
            (requirements.ai, {PluginCapability.AI_INFERENCE}, "ai"),
        )
        for enabled, acceptable, field in required:
            if enabled and not capability_values.intersection(acceptable):
                raise CyberOSError(
                    ErrorCode.PLUGIN_MANIFEST_INVALID,
                    f"Requirement {field} is not represented by a declared capability.",
                )

    def to_payload(self) -> dict[str, object]:
        return {
            "plugin_id": self.plugin_id,
            "display_name": self.display_name,
            "description": self.description,
            "plugin_version": self.plugin_version,
            "contract_version": self.contract_version,
            "capabilities": [value.value for value in self.capabilities],
            "supported_target_kinds": [value.value for value in self.supported_target_kinds],
            "requirements": {
                "network": self.requirements.network,
                "subprocess": self.requirements.subprocess,
                "filesystem": self.requirements.filesystem,
                "external_api": self.requirements.external_api,
                "ai": self.requirements.ai,
            },
            "declared_limits": {
                "max_input_bytes": self.declared_limits.max_input_bytes,
                "max_output_bytes": self.declared_limits.max_output_bytes,
                "max_observations": self.declared_limits.max_observations,
                "timeout_seconds": self.declared_limits.timeout_seconds,
            },
        }


@dataclass(frozen=True, slots=True)
class ReconInput:
    """Explicit, bounded plugin input with no secondary target selector."""

    scope_id: ScopeId
    target_id: TargetId
    candidate: TargetCandidate
    parameters: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _validate_uuid4(self.scope_id, field="scope_id")
        _validate_uuid4(self.target_id, field="target_id")
        if not isinstance(self.candidate, TargetCandidate):
            raise CyberOSError(ErrorCode.PLUGIN_INPUT_INVALID, "candidate must be TargetCandidate.")
        if not isinstance(self.parameters, tuple):
            raise CyberOSError(ErrorCode.PLUGIN_INPUT_INVALID, "parameters must be a tuple.")
        reserved = {"target", "target_id", "scope_id", "candidate", "raw_target", "url", "host"}
        seen: set[str] = set()
        normalized: list[tuple[str, str]] = []
        for key, value in self.parameters:
            if (
                not isinstance(key, str)
                or _PARAMETER_KEY_RE.fullmatch(key) is None
                or key in reserved
            ):
                raise CyberOSError(
                    ErrorCode.PLUGIN_INPUT_INVALID, "parameters contain a reserved or invalid key."
                )
            if not isinstance(value, str) or len(value) > 1_024:
                raise CyberOSError(
                    ErrorCode.PLUGIN_INPUT_INVALID, "parameter values must be bounded text."
                )
            if key in seen:
                raise CyberOSError(ErrorCode.PLUGIN_INPUT_INVALID, "parameter keys must be unique.")
            seen.add(key)
            normalized.append((key, value))
        object.__setattr__(self, "parameters", tuple(sorted(normalized)))

    def to_payload(self) -> dict[str, object]:
        return {
            "scope_id": str(self.scope_id),
            "target_id": str(self.target_id),
            "candidate": {"raw_value": self.candidate.raw_value, "kind": self.candidate.kind.value},
            "parameters": {key: value for key, value in self.parameters},
        }


@dataclass(frozen=True, slots=True)
class ExecutionLimits:
    """Effective host limits derived from Task and policy intersections."""

    timeout_seconds: int
    max_input_bytes: int
    max_output_bytes: int
    max_observations: int

    def __post_init__(self) -> None:
        for field in ("timeout_seconds", "max_input_bytes", "max_output_bytes", "max_observations"):
            value = getattr(self, field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise CyberOSError(ErrorCode.PLUGIN_LIMIT_EXCEEDED, f"{field} must be positive.")


_INVOCATION_SEAL = object()


@dataclass(frozen=True, slots=True, init=False)
class PluginInvocation:
    """Immutable host-created envelope supplied to a registered plugin."""

    plugin_id: PluginId
    plugin_version: SemVer
    contract_version: ContractVersion
    task: Task
    authorization: ExecutionAuthorization
    input: ReconInput
    effective_limits: ExecutionLimits

    def __init__(
        self,
        *,
        _seal: object | None = None,
        plugin_id: PluginId,
        plugin_version: SemVer,
        contract_version: ContractVersion,
        task: Task,
        authorization: ExecutionAuthorization,
        input: ReconInput,
        effective_limits: ExecutionLimits,
    ) -> None:
        if _seal is not _INVOCATION_SEAL:
            raise CyberOSError(
                ErrorCode.PLUGIN_AUTHORIZATION_INVALID,
                "Only PluginHost may create PluginInvocation.",
            )
        object.__setattr__(self, "plugin_id", plugin_id)
        object.__setattr__(self, "plugin_version", plugin_version)
        object.__setattr__(self, "contract_version", contract_version)
        object.__setattr__(self, "task", task)
        object.__setattr__(self, "authorization", authorization)
        object.__setattr__(self, "input", input)
        object.__setattr__(self, "effective_limits", effective_limits)

    @classmethod
    def _from_host(
        cls,
        *,
        seal: object,
        plugin_id: PluginId,
        plugin_version: SemVer,
        contract_version: ContractVersion,
        task: Task,
        authorization: ExecutionAuthorization,
        input: ReconInput,
        effective_limits: ExecutionLimits,
    ) -> PluginInvocation:
        return cls(
            _seal=seal,
            plugin_id=plugin_id,
            plugin_version=plugin_version,
            contract_version=contract_version,
            task=task,
            authorization=authorization,
            input=input,
            effective_limits=effective_limits,
        )


@dataclass(frozen=True, slots=True)
class ReconObservation:
    """Bounded scalar observation with canonical metadata ordering."""

    observation_type: str
    value: ScalarValue
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.observation_type, str)
            or _OBSERVATION_TYPE_RE.fullmatch(self.observation_type) is None
        ):
            raise CyberOSError(
                ErrorCode.PLUGIN_RESULT_INVALID, "observation_type has an invalid format."
            )
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise CyberOSError(ErrorCode.PLUGIN_RESULT_INVALID, "Observation float must be finite.")
        if isinstance(self.value, str) and len(self.value) > 4_096:
            raise CyberOSError(ErrorCode.PLUGIN_RESULT_INVALID, "Observation text is too large.")
        if not isinstance(self.metadata, tuple):
            raise CyberOSError(
                ErrorCode.PLUGIN_RESULT_INVALID, "Observation metadata must be a tuple."
            )
        seen: set[str] = set()
        normalized: list[tuple[str, str]] = []
        for key, value in self.metadata:
            if not isinstance(key, str) or _PARAMETER_KEY_RE.fullmatch(key) is None:
                raise CyberOSError(
                    ErrorCode.PLUGIN_RESULT_INVALID, "Observation metadata key is invalid."
                )
            if not isinstance(value, str) or len(value) > 1_024 or key in seen:
                raise CyberOSError(
                    ErrorCode.PLUGIN_RESULT_INVALID,
                    "Observation metadata is invalid or duplicated.",
                )
            seen.add(key)
            normalized.append((key, value))
        object.__setattr__(self, "metadata", tuple(sorted(normalized)))

    def to_payload(self) -> dict[str, object]:
        return {
            "observation_type": self.observation_type,
            "value": self.value,
            "metadata": {key: value for key, value in self.metadata},
        }


@dataclass(frozen=True, slots=True)
class ReconError:
    """Safe typed error included in a controlled ReconResult failure."""

    code: ErrorCode
    message: str
    field: str | None = None

    def __post_init__(self) -> None:
        if self.code not in _PLUGIN_ERROR_CODES:
            raise CyberOSError(
                ErrorCode.PLUGIN_RESULT_INVALID, "ReconError code is not a plugin error."
            )
        object.__setattr__(
            self, "message", _bounded_text(self.message, field="error_message", maximum=512)
        )
        if self.field is not None:
            object.__setattr__(
                self, "field", _bounded_text(self.field, field="error_field", maximum=80)
            )

    def to_payload(self) -> dict[str, object]:
        return {"code": self.code.value, "message": self.message, "field": self.field}


@dataclass(frozen=True, slots=True)
class ReconResult:
    """Deterministic immutable result accepted from a plugin."""

    task_id: UUID
    scope_id: ScopeId
    target_id: TargetId
    plugin_id: PluginId
    plugin_version: SemVer
    contract_version: ContractVersion
    status: ReconStatus
    observations: tuple[ReconObservation, ...] = ()
    errors: tuple[ReconError, ...] = ()

    def __post_init__(self) -> None:
        _validate_uuid4(self.task_id, field="task_id")
        _validate_uuid4(self.scope_id, field="scope_id")
        _validate_uuid4(self.target_id, field="target_id")
        if not isinstance(self.status, ReconStatus):
            raise CyberOSError(ErrorCode.PLUGIN_RESULT_INVALID, "status must be ReconStatus.")
        object.__setattr__(
            self, "plugin_id", _bounded_text(self.plugin_id, field="plugin_id", maximum=80)
        )
        object.__setattr__(self, "plugin_version", _normalize_semver(self.plugin_version))
        object.__setattr__(
            self, "contract_version", _normalize_contract_version(self.contract_version)
        )
        if not isinstance(self.observations, tuple) or any(
            not isinstance(value, ReconObservation) for value in self.observations
        ):
            raise CyberOSError(
                ErrorCode.PLUGIN_RESULT_INVALID,
                "observations must contain ReconObservation values.",
            )
        if not isinstance(self.errors, tuple) or any(
            not isinstance(value, ReconError) for value in self.errors
        ):
            raise CyberOSError(
                ErrorCode.PLUGIN_RESULT_INVALID, "errors must contain ReconError values."
            )
        observations = tuple(
            sorted(self.observations, key=lambda item: (item.observation_type, repr(item.value)))
        )
        errors = tuple(
            sorted(self.errors, key=lambda item: (item.code.value, item.message, item.field or ""))
        )
        object.__setattr__(self, "observations", observations)
        object.__setattr__(self, "errors", errors)
        if self.status is ReconStatus.SUCCESS and self.errors:
            raise CyberOSError(
                ErrorCode.PLUGIN_RESULT_INVALID, "Successful ReconResult cannot contain errors."
            )
        if self.status is ReconStatus.FAILURE and not self.errors:
            raise CyberOSError(
                ErrorCode.PLUGIN_RESULT_INVALID, "Failed ReconResult requires a typed error."
            )

    @classmethod
    def success(
        cls,
        *,
        task_id: UUID,
        scope_id: ScopeId,
        target_id: TargetId,
        plugin_id: PluginId,
        plugin_version: SemVer,
        contract_version: ContractVersion,
        observations: tuple[ReconObservation, ...],
    ) -> ReconResult:
        return cls(
            task_id=task_id,
            scope_id=scope_id,
            target_id=target_id,
            plugin_id=plugin_id,
            plugin_version=plugin_version,
            contract_version=contract_version,
            status=ReconStatus.SUCCESS,
            observations=observations,
        )

    @classmethod
    def failure(
        cls,
        *,
        task_id: UUID,
        scope_id: ScopeId,
        target_id: TargetId,
        plugin_id: PluginId,
        plugin_version: SemVer,
        contract_version: ContractVersion,
        errors: tuple[ReconError, ...],
    ) -> ReconResult:
        return cls(
            task_id=task_id,
            scope_id=scope_id,
            target_id=target_id,
            plugin_id=plugin_id,
            plugin_version=plugin_version,
            contract_version=contract_version,
            status=ReconStatus.FAILURE,
            errors=errors,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "task_id": str(self.task_id),
            "scope_id": str(self.scope_id),
            "target_id": str(self.target_id),
            "plugin_id": self.plugin_id,
            "plugin_version": self.plugin_version,
            "contract_version": self.contract_version,
            "status": self.status.value,
            "observations": [value.to_payload() for value in self.observations],
            "errors": [value.to_payload() for value in self.errors],
        }

    def to_json(self) -> str:
        return dumps(self.to_payload())

    def validate_within(self, limits: ExecutionLimits) -> None:
        if len(self.observations) > limits.max_observations:
            raise CyberOSError(
                ErrorCode.PLUGIN_LIMIT_EXCEEDED, "Plugin result exceeds observation limit."
            )
        if len(self.to_json().encode("utf-8")) > limits.max_output_bytes:
            raise CyberOSError(
                ErrorCode.PLUGIN_LIMIT_EXCEEDED,
                "Plugin result exceeds the effective output limit.",
            )


@runtime_checkable
class ReconPlugin(Protocol):
    @property
    def manifest(self) -> PluginManifest: ...

    def execute(self, invocation: PluginInvocation) -> ReconResult: ...


def create_host_invocation(
    *,
    plugin_id: PluginId,
    plugin_version: SemVer,
    contract_version: ContractVersion,
    task: Task,
    authorization: ExecutionAuthorization,
    input: ReconInput,
    effective_limits: ExecutionLimits,
) -> PluginInvocation:
    """Internal host-only constructor kept separate from the plugin protocol."""

    return PluginInvocation._from_host(
        seal=_INVOCATION_SEAL,
        plugin_id=plugin_id,
        plugin_version=plugin_version,
        contract_version=contract_version,
        task=task,
        authorization=authorization,
        input=input,
        effective_limits=effective_limits,
    )
