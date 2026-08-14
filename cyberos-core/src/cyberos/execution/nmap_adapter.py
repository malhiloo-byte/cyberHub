"""Nmap identity and localhost preflight contracts for Slice 2.1.f.a–b.

Style note: this module verifies an explicitly supplied binary and builds a
dry-run request only. It never resolves PATH, installs packages, opens a
socket, invokes Nmap, writes scan output, or authorizes a non-loopback target.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from cyberos.application.scope_validation import ExecutionAuthorization
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.time import ensure_utc, utc_now
from cyberos.domain.recon.network_scan import (
    MachineOutputFormat,
    NetworkScanInvocation,
    ScanMode,
    TimingProfile,
)
from cyberos.domain.target.primitives import TargetKind, TargetRule
from cyberos.execution.live_adapter import ApprovedExecutable, LiveSubprocessRequest

__all__ = [
    "NmapLocalhostLabPolicy",
    "NmapLocalhostManifest",
    "NmapPreflightPlan",
    "VerifiedBinaryIdentity",
]

_HEX = re.compile(r"[0-9a-f]{64}\Z")
_LOCALHOST = "127.0.0.1"
_ALLOWED_PORTS = frozenset({22, 80, 443})
_FIXED_PREFIX = ("-sS", "-T3", "-n", "-Pn")


@dataclass(frozen=True, slots=True)
class VerifiedBinaryIdentity:
    """Host-verified Nmap identity; never created from PATH lookup."""

    logical_id: str
    absolute_path: str
    binary_name: str
    sha256: str
    version: str

    def __post_init__(self) -> None:
        if not self.logical_id or any(character in self.logical_id for character in "\x00\r\n"):
            raise CyberOSError(
                ErrorCode.NMAP_MANIFEST_INVALID, "Binary logical identity is invalid."
            )
        path = Path(self.absolute_path)
        if not path.is_absolute() or path.name != self.binary_name or self.binary_name != "nmap":
            raise CyberOSError(
                ErrorCode.LIVE_TOOL_BINARY_INVALID, "Nmap binary path identity is invalid."
            )
        if not _HEX.fullmatch(self.sha256):
            raise CyberOSError(ErrorCode.LIVE_TOOL_BINARY_INVALID, "Nmap binary digest is invalid.")
        if not self.version or any(character in self.version for character in "\x00\r\n"):
            raise CyberOSError(
                ErrorCode.LIVE_TOOL_BINARY_INVALID, "Nmap binary version is invalid."
            )

    @classmethod
    def verify(
        cls,
        *,
        logical_id: str,
        absolute_path: str,
        expected_sha256: str,
        expected_version: str,
    ) -> VerifiedBinaryIdentity:
        path = Path(absolute_path)
        if not path.is_absolute() or path.name != "nmap":
            raise CyberOSError(
                ErrorCode.LIVE_TOOL_BINARY_INVALID, "Nmap path must be absolute and named nmap."
            )
        if path.is_symlink() or not path.is_file():
            raise CyberOSError(
                ErrorCode.LIVE_TOOL_BINARY_UNAVAILABLE, "Approved Nmap binary is unavailable."
            )
        if not os.access(path, os.X_OK):
            raise CyberOSError(
                ErrorCode.LIVE_TOOL_BINARY_INVALID, "Approved Nmap binary is not executable."
            )
        if not _HEX.fullmatch(expected_sha256):
            raise CyberOSError(
                ErrorCode.LIVE_TOOL_BINARY_INVALID, "Expected Nmap digest is invalid."
            )
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected_sha256:
            raise CyberOSError(
                ErrorCode.LIVE_TOOL_BINARY_INVALID, "Nmap binary digest does not match."
            )
        return cls(logical_id, str(path), "nmap", actual, expected_version)


@dataclass(frozen=True, slots=True)
class NmapLocalhostManifest:
    adapter_id: str = "nmap.tcp-syn.xml.localhost"
    executable_id: str = "nmap.binary.approved"
    adapter_version: str = "2.1.0"
    command_contract_version: str = "1.0"
    output_contract_version: str = "1.0"
    output_format: MachineOutputFormat = MachineOutputFormat.XML
    max_ports: int = 3
    max_timeout_seconds: int = 30
    max_output_bytes: int = 262_144
    scan_mode: ScanMode = ScanMode.SYN

    def __post_init__(self) -> None:
        if self.output_format is not MachineOutputFormat.XML:
            raise CyberOSError(
                ErrorCode.NMAP_MANIFEST_INVALID, "Localhost Nmap output must be XML."
            )
        if self.scan_mode not in {ScanMode.SYN, ScanMode.CONNECT}:
            raise CyberOSError(ErrorCode.NMAP_MANIFEST_INVALID, "Localhost scan mode is invalid.")
        if self.max_ports != 3 or self.max_timeout_seconds != 30:
            raise CyberOSError(ErrorCode.NMAP_MANIFEST_INVALID, "Localhost lab limits are fixed.")
        if self.max_output_bytes != 262_144:
            raise CyberOSError(ErrorCode.NMAP_MANIFEST_INVALID, "Localhost output limit is fixed.")

    def approved_executable(self, identity: VerifiedBinaryIdentity) -> ApprovedExecutable:
        if identity.logical_id != self.executable_id:
            raise CyberOSError(
                ErrorCode.NMAP_MANIFEST_INVALID, "Binary identity does not match Nmap manifest."
            )
        scan_flag = "-sS" if self.scan_mode is ScanMode.SYN else "-sT"
        return ApprovedExecutable(
            logical_id=self.executable_id,
            executable=identity.absolute_path,
            command_prefix=(identity.absolute_path, scan_flag, *_FIXED_PREFIX[1:]),
            supported_target_kinds=(TargetKind.IPV4,),
            require_target_argument=True,
            max_timeout_seconds=self.max_timeout_seconds,
            max_output_bytes=self.max_output_bytes,
        )


@dataclass(frozen=True, slots=True)
class NmapPreflightPlan:
    profile_id: str
    request: LiveSubprocessRequest
    argv_digest: str
    dry_run: bool = True


class NmapLocalhostLabPolicy:
    """Build a dry-run request for one authorized IPv4 loopback target."""

    profile_id = "lab.localhost.tcp-syn.v1"

    def build_plan(
        self,
        *,
        invocation: NetworkScanInvocation,
        identity: VerifiedBinaryIdentity,
        manifest: NmapLocalhostManifest,
        authorization: ExecutionAuthorization,
        now: datetime | None = None,
    ) -> NmapPreflightPlan:
        timestamp = ensure_utc(now) if now is not None else utc_now()
        if invocation.manifest_id != manifest.adapter_id:
            raise CyberOSError(
                ErrorCode.NMAP_MANIFEST_INVALID, "Invocation is not bound to Nmap manifest."
            )
        if (
            invocation.target_kind is not TargetKind.IPV4
            or invocation.canonical_target != _LOCALHOST
        ):
            raise CyberOSError(
                ErrorCode.LAB_TARGET_REJECTED, "Only 127.0.0.1 is allowed in this lab profile."
            )
        if invocation.output_format is not MachineOutputFormat.XML:
            raise CyberOSError(
                ErrorCode.NMAP_MANIFEST_INVALID, "Nmap localhost output must be XML."
            )
        if not invocation.ports or len(invocation.ports) > manifest.max_ports:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_LIMIT_EXCEEDED, "Localhost port budget exceeded."
            )
        if any(port not in _ALLOWED_PORTS for port in invocation.ports):
            raise CyberOSError(
                ErrorCode.LAB_TARGET_REJECTED, "Port is not in the localhost lab allowlist."
            )
        if (
            authorization.scope_id != invocation.scope_id
            or authorization.matched_target_id != invocation.target_id
        ):
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_UNAUTHORIZED, "Authorization is not invocation-bound."
            )
        if authorization.matching_rule is not TargetRule.INCLUDE:
            raise CyberOSError(
                ErrorCode.LIVE_ADAPTER_UNAUTHORIZED,
                "Localhost trial requires Include authorization.",
            )
        if authorization.expires_at is not None and authorization.expires_at <= timestamp:
            raise CyberOSError(ErrorCode.LIVE_ADAPTER_UNAUTHORIZED, "Authorization has expired.")
        if (
            invocation.scan_mode is not manifest.scan_mode
            or invocation.timing_profile is not TimingProfile.T4
        ):
            raise CyberOSError(
                ErrorCode.PORT_SCAN_FLAG_NOT_ALLOWED, "Nmap fixed scan policy is not satisfied."
            )
        if (
            invocation.timeout_seconds > manifest.max_timeout_seconds
            or invocation.max_output_bytes > manifest.max_output_bytes
        ):
            raise CyberOSError(
                ErrorCode.PORT_SCAN_LIMIT_EXCEEDED, "Nmap localhost limits are exceeded."
            )
        scan_flag = "-sS" if manifest.scan_mode is ScanMode.SYN else "-sT"
        argv = (
            identity.absolute_path,
            scan_flag,
            *_FIXED_PREFIX[1:],
            "-p",
            ",".join(str(port) for port in sorted(invocation.ports)),
            "-oX",
            "-",
            _LOCALHOST,
        )
        if invocation.task.execution_spec.command != argv:
            raise CyberOSError(
                ErrorCode.TASK_EXECUTION_SPEC_MISMATCH, "Task command is not the Nmap plan."
            )
        request = LiveSubprocessRequest(
            task=invocation.task,
            authorization=authorization,
            scope_id=invocation.scope_id,
            target_id=invocation.target_id,
            target_kind=invocation.target_kind,
            canonical_target=_LOCALHOST,
            command=argv,
            allowed_executable_id=manifest.executable_id,
            timeout_seconds=invocation.timeout_seconds,
            max_stdout_bytes=invocation.max_output_bytes,
            max_stderr_bytes=invocation.max_output_bytes,
        )
        profile_id = (
            "lab.localhost.tcp-syn.v1"
            if manifest.scan_mode is ScanMode.SYN
            else "lab.localhost.tcp-connect.v1"
        )
        return NmapPreflightPlan(
            profile_id,
            request,
            hashlib.sha256("\x00".join(argv).encode()).hexdigest(),
        )
