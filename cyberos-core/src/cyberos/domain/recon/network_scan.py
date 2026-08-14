"""Offline-first contracts and policy for the Module 2.1 port-scan adapter.

Style note: this module contains immutable, renderer-neutral domain contracts
and pure validation only. It never opens sockets, starts processes, reads or
writes files, parses arbitrary shell strings, or persists reconnaissance data.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from cyberos.application.scope_validation import ExecutionAuthorization
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.primitives import TargetId, TargetKind, TargetRule
from cyberos.domain.task.model import Task

__all__ = [
    "FlagRule",
    "MachineOutputFormat",
    "NetworkPortScanAdapterManifest",
    "NetworkScanInvocation",
    "NetworkScanLimits",
    "ScanMode",
    "TimingProfile",
    "validate_target_value",
]


class MachineOutputFormat(StrEnum):
    XML = "xml"
    JSON = "json"


class ScanMode(StrEnum):
    SYN = "syn"


class TimingProfile(StrEnum):
    T4 = "T4"


class FlagRule(StrEnum):
    SCAN_MODE = "scan_mode"
    PORT_SELECTION = "port_selection"
    TIMING = "timing"
    MACHINE_OUTPUT = "machine_output"


_FQDN_RE: Final[re.Pattern[str]] = re.compile(
    r"(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\Z"
)
_MAX_CIDR_HOSTS: Final[int] = 256
_MAX_PORTS: Final[int] = 256


def _text(value: str, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.encode()) > maximum:
        raise CyberOSError(ErrorCode.PORT_SCAN_MANIFEST_INVALID, f"{field} is invalid.")
    if any(character in value for character in "\x00\r\n;|&><$`"):
        raise CyberOSError(
            ErrorCode.PORT_SCAN_MANIFEST_INVALID, f"{field} contains forbidden syntax."
        )
    return value.strip()


def validate_target_value(kind: TargetKind, value: str) -> str:
    """Validate one canonical target without network resolution."""

    if kind is TargetKind.WILDCARD or kind is TargetKind.URL:
        raise CyberOSError(
            ErrorCode.PORT_SCAN_TARGET_INVALID, "Target kind is not allowed for port scanning."
        )
    normalized = _text(value, "target", 253).rstrip(".").lower()
    if kind is TargetKind.IPV4:
        try:
            parsed_v4 = ipaddress.IPv4Address(normalized)
        except ipaddress.AddressValueError as exc:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_TARGET_INVALID, "IPv4 target is invalid."
            ) from exc
        return str(parsed_v4)
    if kind is TargetKind.IPV6:
        try:
            parsed_v6 = ipaddress.IPv6Address(normalized)
        except ipaddress.AddressValueError as exc:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_TARGET_INVALID, "IPv6 target is invalid."
            ) from exc
        return parsed_v6.compressed
    if kind is TargetKind.CIDR:
        try:
            network = ipaddress.ip_network(normalized, strict=True)
        except ValueError as exc:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_TARGET_INVALID, "CIDR target is invalid."
            ) from exc
        hosts = network.num_addresses
        if hosts > _MAX_CIDR_HOSTS:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_LIMIT_EXCEEDED, "CIDR target exceeds host budget."
            )
        return str(network)
    if kind is TargetKind.FQDN and _FQDN_RE.fullmatch(normalized) is not None:
        return normalized
    raise CyberOSError(ErrorCode.PORT_SCAN_TARGET_INVALID, "FQDN target is invalid.")


@dataclass(frozen=True, slots=True)
class NetworkScanLimits:
    max_ports: int = _MAX_PORTS
    max_timeout_seconds: int = 300
    max_output_bytes: int = 1_048_576
    max_observations: int = 256

    def __post_init__(self) -> None:
        values = (
            self.max_ports,
            self.max_timeout_seconds,
            self.max_output_bytes,
            self.max_observations,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in values
        ):
            raise CyberOSError(
                ErrorCode.PORT_SCAN_MANIFEST_INVALID, "Network scan limits are invalid."
            )


@dataclass(frozen=True, slots=True)
class NetworkPortScanAdapterManifest:
    adapter_id: str
    display_name: str
    adapter_version: str
    contract_version: str
    executable_id: str
    executable_absolute_path: str
    supported_target_kinds: tuple[TargetKind, ...]
    output_format: MachineOutputFormat
    output_contract_version: str
    allowed_flags: tuple[FlagRule, ...]
    required_flags: tuple[FlagRule, ...]
    fixed_scan_mode: ScanMode = ScanMode.SYN
    fixed_timing: TimingProfile = TimingProfile.T4
    limits: NetworkScanLimits = NetworkScanLimits()
    supports_child_processes: bool = False
    supports_background_mode: bool = False

    def __post_init__(self) -> None:
        if not self.adapter_id or not re.fullmatch(
            r"[a-z0-9]+(?:[._-][a-z0-9]+)*", self.adapter_id
        ):
            raise CyberOSError(ErrorCode.PORT_SCAN_MANIFEST_INVALID, "Adapter ID is invalid.")
        _text(self.display_name, "display_name", 120)
        for value, field, pattern in (
            (self.adapter_version, "adapter_version", r"\d+\.\d+\.\d+"),
            (self.contract_version, "contract_version", r"\d+\.\d+"),
            (self.output_contract_version, "output_contract_version", r"\d+\.\d+"),
        ):
            if re.fullmatch(pattern, value) is None:
                raise CyberOSError(ErrorCode.PORT_SCAN_MANIFEST_INVALID, f"{field} is invalid.")
        if not self.executable_id or not self.executable_absolute_path.startswith("/"):
            raise CyberOSError(
                ErrorCode.PORT_SCAN_MANIFEST_INVALID, "Executable identity is invalid."
            )
        if not isinstance(self.output_format, MachineOutputFormat):
            raise CyberOSError(ErrorCode.PORT_SCAN_MANIFEST_INVALID, "Output format is invalid.")
        if not isinstance(self.supported_target_kinds, tuple) or not self.supported_target_kinds:
            raise CyberOSError(ErrorCode.PORT_SCAN_MANIFEST_INVALID, "Target kinds are required.")
        allowed_kinds = {TargetKind.FQDN, TargetKind.IPV4, TargetKind.IPV6, TargetKind.CIDR}
        if any(kind not in allowed_kinds for kind in self.supported_target_kinds):
            raise CyberOSError(
                ErrorCode.PORT_SCAN_MANIFEST_INVALID, "Target kind is not supported."
            )
        if len(set(self.supported_target_kinds)) != len(self.supported_target_kinds):
            raise CyberOSError(ErrorCode.PORT_SCAN_MANIFEST_INVALID, "Target kinds must be unique.")
        if not isinstance(self.allowed_flags, tuple) or len(set(self.allowed_flags)) != len(
            self.allowed_flags
        ):
            raise CyberOSError(ErrorCode.PORT_SCAN_MANIFEST_INVALID, "Allowed flags are invalid.")
        if not isinstance(self.required_flags, tuple) or any(
            flag not in self.allowed_flags for flag in self.required_flags
        ):
            raise CyberOSError(ErrorCode.PORT_SCAN_MANIFEST_INVALID, "Required flags are invalid.")
        if not isinstance(self.limits, NetworkScanLimits):
            raise CyberOSError(ErrorCode.PORT_SCAN_MANIFEST_INVALID, "Limits are invalid.")
        if self.supports_child_processes or self.supports_background_mode:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_MANIFEST_INVALID, "Child/background execution is forbidden."
            )


@dataclass(frozen=True, slots=True)
class NetworkScanInvocation:
    task: Task
    authorization: ExecutionAuthorization
    scope_id: ScopeId
    target_id: TargetId
    target_kind: TargetKind
    canonical_target: str
    manifest_id: str
    ports: tuple[int, ...]
    scan_mode: ScanMode
    timing_profile: TimingProfile
    output_format: MachineOutputFormat
    timeout_seconds: int
    max_output_bytes: int

    def __post_init__(self) -> None:
        if self.scope_id != self.task.scope_id or self.target_id != self.task.target_id:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_TARGET_UNAUTHORIZED, "Invocation is not Task-bound."
            )
        if (
            self.authorization.scope_id != self.scope_id
            or self.authorization.matched_target_id != self.target_id
            or self.authorization.matching_rule is not TargetRule.INCLUDE
        ):
            raise CyberOSError(
                ErrorCode.PORT_SCAN_TARGET_UNAUTHORIZED, "Invocation authorization is invalid."
            )
        if self.target_kind not in {
            TargetKind.FQDN,
            TargetKind.IPV4,
            TargetKind.IPV6,
            TargetKind.CIDR,
        }:
            raise CyberOSError(ErrorCode.PORT_SCAN_TARGET_INVALID, "Target kind is invalid.")
        canonical = validate_target_value(self.target_kind, self.canonical_target)
        if canonical != self.authorization.candidate.raw_value.rstrip(".").lower():
            raise CyberOSError(
                ErrorCode.PORT_SCAN_CONTEXT_MISMATCH,
                "Canonical target does not match authorization.",
            )
        if (
            not isinstance(self.ports, tuple)
            or not self.ports
            or len(set(self.ports)) != len(self.ports)
        ):
            raise CyberOSError(
                ErrorCode.PORT_SCAN_TARGET_INVALID, "Ports must be unique and non-empty."
            )
        if any(
            not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535
            for port in self.ports
        ):
            raise CyberOSError(ErrorCode.PORT_SCAN_TARGET_INVALID, "Port value is invalid.")
        if len(self.ports) > _MAX_PORTS:
            raise CyberOSError(ErrorCode.PORT_SCAN_LIMIT_EXCEEDED, "Port budget exceeded.")
        if not isinstance(self.scan_mode, ScanMode) or not isinstance(
            self.timing_profile, TimingProfile
        ):
            raise CyberOSError(
                ErrorCode.PORT_SCAN_FLAG_NOT_ALLOWED, "Scan mode or timing profile is invalid."
            )
        if not isinstance(self.output_format, MachineOutputFormat):
            raise CyberOSError(
                ErrorCode.PORT_SCAN_OUTPUT_CONTRACT_INVALID, "Output format is invalid."
            )
        if not isinstance(self.timeout_seconds, int) or self.timeout_seconds < 1:
            raise CyberOSError(ErrorCode.PORT_SCAN_LIMIT_EXCEEDED, "Timeout is invalid.")
        if not isinstance(self.max_output_bytes, int) or self.max_output_bytes < 1:
            raise CyberOSError(ErrorCode.PORT_SCAN_LIMIT_EXCEEDED, "Output budget is invalid.")

    def to_typed_flags(self, manifest: NetworkPortScanAdapterManifest) -> tuple[str, ...]:
        if manifest.adapter_id != self.manifest_id:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_FLAG_NOT_ALLOWED, "Manifest identity does not match invocation."
            )
        if (
            self.scan_mode is not manifest.fixed_scan_mode
            or self.timing_profile is not manifest.fixed_timing
        ):
            raise CyberOSError(
                ErrorCode.PORT_SCAN_FLAG_NOT_ALLOWED, "Requested scan policy is not allowlisted."
            )
        if self.output_format is not manifest.output_format:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_OUTPUT_CONTRACT_INVALID,
                "Output format does not match manifest.",
            )
        if (
            self.timeout_seconds > manifest.limits.max_timeout_seconds
            or self.max_output_bytes > manifest.limits.max_output_bytes
        ):
            raise CyberOSError(
                ErrorCode.PORT_SCAN_LIMIT_EXCEEDED, "Invocation exceeds manifest limits."
            )
        if (
            FlagRule.SCAN_MODE not in manifest.required_flags
            or FlagRule.PORT_SELECTION not in manifest.required_flags
        ):
            raise CyberOSError(
                ErrorCode.PORT_SCAN_MANIFEST_INVALID, "Required scan flags are incomplete."
            )
        ports = ",".join(str(port) for port in sorted(self.ports))
        output_flag = (
            "--output-xml" if self.output_format is MachineOutputFormat.XML else "--output-json"
        )
        return ("-sS", "-p", ports, "-T4", output_flag, self.canonical_target)
