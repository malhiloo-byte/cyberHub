"""Pure Nmap XML stdout bridge for Slice 2.1.f.c.

Style note: the bridge accepts bytes only, uses Expat with external
declarations disabled, extracts a closed subset of Nmap XML, and delegates
final normalization to the Module 2.1 parser. It never runs Nmap, opens a
socket, writes a file, or stores raw XML.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from xml.parsers import expat

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.recon.network_scan import MachineOutputFormat
from cyberos.domain.recon.network_scan_parser import (
    NetworkScanParser,
    NetworkScanParseResult,
    ParserLimits,
)
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.primitives import TargetId, TargetKind

__all__ = ["NmapXmlParserBridge"]
_DEFAULT_PARSER_LIMITS = ParserLimits()


@dataclass(frozen=True, slots=True)
class _Port:
    port: str
    protocol: str
    state: str
    service: str
    product: str
    version: str


class NmapXmlParserBridge:
    """Parse the allowlisted Nmap XML subset into the existing parser DTO."""

    def __init__(self, parser: NetworkScanParser | None = None) -> None:
        self.parser = parser or NetworkScanParser()

    def parse(
        self,
        payload: bytes,
        *,
        scope_id: ScopeId,
        target_id: TargetId,
        canonical_target: str,
        limits: ParserLimits = _DEFAULT_PARSER_LIMITS,
        truncated: bool = False,
    ) -> NetworkScanParseResult:
        if truncated:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_TRUNCATED_OUTPUT, "Nmap XML output was truncated."
            )
        if len(payload) > limits.max_payload_bytes:
            raise CyberOSError(ErrorCode.PORT_SCAN_LIMIT_EXCEEDED, "Nmap XML exceeds byte budget.")
        expected_target = canonical_target
        ports: list[_Port] = []
        depth = 0
        root_seen = False
        root_closed = False
        current_host: str | None = None
        current_port: dict[str, str] | None = None
        current_state: str | None = None
        current_service: dict[str, str] | None = None

        def accept_benign_doctype(
            _name: str, _system_id: str | None, _public_id: str | None, _has_internal_subset: int
        ) -> None:
            if _name != "nmaprun" or _public_id is not None or _has_internal_subset:
                raise CyberOSError(ErrorCode.NMAP_XML_INVALID, "Nmap XML DTD is not permitted.")
            # A SYSTEM identifier may appear in standard Nmap output. It is
            # deliberately ignored; no DTD is loaded and no URI is fetched.

        def reject_entity(
            _entity_name: str,
            _is_parameter_entity: int,
            _value: str | None,
            _base: str | None,
            _system_id: str | None,
            _public_id: str | None,
            _notation_name: str | None,
        ) -> None:
            raise CyberOSError(ErrorCode.NMAP_XML_INVALID, "Nmap XML entities are not permitted.")

        def reject_external(
            _context: str | None,
            _base: str | None,
            _system_id: str | None,
            _public_id: str | None,
        ) -> int:
            raise CyberOSError(
                ErrorCode.NMAP_XML_INVALID, "Nmap XML external entities are not permitted."
            )

        def start(name: str, attributes: dict[str, str]) -> None:
            nonlocal depth, root_seen, current_host, current_port, current_state, current_service
            depth += 1
            if depth > limits.max_depth:
                raise CyberOSError(
                    ErrorCode.PORT_SCAN_LIMIT_EXCEEDED, "Nmap XML depth budget exceeded."
                )
            if not root_seen:
                root_seen = True
                if name != "nmaprun" or attributes.get("scanner") != "nmap":
                    raise CyberOSError(ErrorCode.NMAP_XML_INVALID, "Nmap XML root is invalid.")
                return
            if name == "host":
                if current_host is not None:
                    raise CyberOSError(ErrorCode.NMAP_XML_INVALID, "Nested Nmap hosts are invalid.")
                current_host = expected_target
                return
            if name == "address":
                if current_host is None or attributes.get("addr") != expected_target:
                    raise CyberOSError(
                        ErrorCode.PORT_SCAN_CONTEXT_MISMATCH, "Nmap address does not match target."
                    )
                if attributes.get("addrtype") != "ipv4":
                    raise CyberOSError(
                        ErrorCode.PORT_SCAN_TARGET_INVALID, "Nmap address type is not IPv4."
                    )
                return
            if name == "port":
                if current_host != expected_target or current_port is not None:
                    raise CyberOSError(ErrorCode.NMAP_XML_INVALID, "Nmap port envelope is invalid.")
                if set(attributes) != {"protocol", "portid"}:
                    raise CyberOSError(
                        ErrorCode.NMAP_XML_INVALID, "Nmap port attributes are invalid."
                    )
                current_port = attributes
                return
            if name == "state":
                state = attributes.get("state")
                reason = attributes.get("reason")
                reason_ttl = attributes.get("reason_ttl")
                if (
                    current_port is None
                    or not state
                    or set(attributes) - {"state", "reason", "reason_ttl"}
                    or (
                        reason is not None
                        and (not reason or len(reason.encode()) > limits.max_field_bytes)
                    )
                    or (
                        reason_ttl is not None
                        and (not reason_ttl.isdecimal() or not 0 <= int(reason_ttl) <= 255)
                    )
                ):
                    raise CyberOSError(ErrorCode.NMAP_XML_INVALID, "Nmap state element is invalid.")
                current_state = state
                return
            if name == "service":
                if current_port is None or set(attributes) - {"name", "product", "version"}:
                    raise CyberOSError(
                        ErrorCode.NMAP_XML_INVALID, "Nmap service element is invalid."
                    )
                current_service = attributes
                return
            if name in {
                "scaninfo",
                "status",
                "ports",
                "runstats",
                "finished",
                "hosts",
                "times",
                "verbose",
                "debugging",
                "hostnames",
                "hostname",
                "extraports",
                "extrareasons",
            }:
                return
            raise CyberOSError(ErrorCode.NMAP_XML_INVALID, "Nmap XML element is not allowlisted.")

        def end(name: str) -> None:
            nonlocal depth, current_host, current_port, current_state, current_service, root_closed
            if name == "service" and current_port is not None:
                current_service = current_service or {}
            if name == "port":
                if current_port is None or current_state is None:
                    raise CyberOSError(ErrorCode.NMAP_XML_INVALID, "Nmap port lacks state.")
                service = current_service or {}
                ports.append(
                    _Port(
                        port=current_port["portid"],
                        protocol=current_port["protocol"],
                        state=current_state,
                        service=service.get("name", ""),
                        product=service.get("product", ""),
                        version=service.get("version", ""),
                    )
                )
                if len(ports) > limits.max_services:
                    raise CyberOSError(
                        ErrorCode.PORT_SCAN_LIMIT_EXCEEDED, "Nmap service budget exceeded."
                    )
                current_port = None
                current_state = None
                current_service = None
            if name == "host":
                current_host = None
            if name == "nmaprun":
                root_closed = True
            depth -= 1

        parser = expat.ParserCreate()
        parser.StartElementHandler = start
        parser.EndElementHandler = end
        parser.StartDoctypeDeclHandler = accept_benign_doctype
        parser.EntityDeclHandler = reject_entity
        parser.ExternalEntityRefHandler = reject_external
        parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
        try:
            parser.Parse(payload, True)
        except CyberOSError:
            raise
        except expat.ExpatError as exc:
            raise CyberOSError(ErrorCode.NMAP_XML_INVALID, "Nmap XML is malformed.") from exc
        if not root_seen or not root_closed or depth != 0:
            raise CyberOSError(ErrorCode.NMAP_XML_INVALID, "Nmap XML is incomplete.")
        normalized = self._normalized_xml(expected_target, ports)
        try:
            return self.parser.parse(
                normalized,
                output_format=MachineOutputFormat.XML,
                scope_id=scope_id,
                target_id=target_id,
                target_kind=TargetKind.IPV4,
                canonical_target=expected_target,
                limits=limits,
            )
        except CyberOSError:
            raise
        except Exception as exc:
            raise CyberOSError(
                ErrorCode.NMAP_XML_INVALID, "Nmap XML normalization failed."
            ) from exc

    @staticmethod
    def _normalized_xml(target: str, ports: list[_Port]) -> bytes:
        escaped_target = html.escape(target, quote=True)
        nodes = []
        for item in sorted(ports, key=lambda value: (value.port, value.protocol)):
            nodes.append(
                f'<port number="{html.escape(item.port, quote=True)}" '
                f'protocol="{html.escape(item.protocol, quote=True)}" '
                f'state="{html.escape(item.state, quote=True)}" '
                f'service="{html.escape(item.service, quote=True)}" '
                f'product="{html.escape(item.product, quote=True)}" '
                f'version="{html.escape(item.version, quote=True)}"/>'
            )
        return (
            f'<scan schema_version="1.0" target="{escaped_target}">'
            f'<host target="{escaped_target}">{"".join(nodes)}</host></scan>'
        ).encode()
