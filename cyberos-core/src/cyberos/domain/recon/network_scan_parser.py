"""Pure, deterministic offline parsers for Module 2.1 scan fixtures.

Style note: parsing is a read-only trust boundary. It accepts bounded bytes,
rejects external entities and unsupported schemas, redacts secrets before
normalization, and returns immutable scalar observations. It performs no
network, process, filesystem, or persistence operation.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Final
from xml.parsers import expat

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.recon.network_scan import MachineOutputFormat, validate_target_value
from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.primitives import TargetId, TargetKind
from cyberos.recon.contracts import ReconObservation

__all__ = [
    "NetworkScanParseResult",
    "NetworkScanParser",
    "ParsedPortService",
    "ParserLimits",
]


_SECRET_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b(authorization|cookie|password|passwd|token|api[_-]?key)\s*[:=]\s*([^\s,;]+)"
)
_PATH_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<![A-Za-z0-9_])/(?:home|root|tmp|var|etc|Users)/[^\s,;\"'}]+"
)
_CONTROL_RE: Final[re.Pattern[str]] = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SCHEMA_VERSION = "1.0"
_ALLOWED_STATES = frozenset({"open", "closed", "filtered"})
_ALLOWED_PROTOCOLS = frozenset({"tcp", "udp"})


@dataclass(frozen=True, slots=True)
class ParserLimits:
    max_payload_bytes: int = 1_048_576
    max_hosts: int = 256
    max_services: int = 256
    max_field_bytes: int = 1_024
    max_depth: int = 8

    def __post_init__(self) -> None:
        values = (
            self.max_payload_bytes,
            self.max_hosts,
            self.max_services,
            self.max_field_bytes,
            self.max_depth,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in values
        ):
            raise CyberOSError(ErrorCode.PORT_SCAN_LIMIT_EXCEEDED, "Parser limits are invalid.")


_DEFAULT_PARSER_LIMITS = ParserLimits()


@dataclass(frozen=True, slots=True)
class ParsedPortService:
    host: str
    port: int
    protocol: str
    state: str
    service_name: str | None
    product: str | None
    version: str | None


@dataclass(frozen=True, slots=True)
class NetworkScanParseResult:
    schema_version: str
    output_format: MachineOutputFormat
    scope_id: ScopeId
    target_id: TargetId
    canonical_target: str
    services: tuple[ParsedPortService, ...]
    observations: tuple[ReconObservation, ...]
    source_digest: str
    redaction_applied: bool
    synthetic: bool
    offline_fixture: bool
    complete: bool

    def __post_init__(self) -> None:
        if self.schema_version != _SCHEMA_VERSION:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_SCHEMA_UNSUPPORTED, "Parser schema version is unsupported."
            )
        if not isinstance(self.output_format, MachineOutputFormat):
            raise CyberOSError(
                ErrorCode.PORT_SCAN_OUTPUT_CONTRACT_INVALID, "Output format is invalid."
            )
        if not self.redaction_applied:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_REDACTION_FAILED, "Parser result must be redaction-marked."
            )
        if not self.synthetic or not self.offline_fixture:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_OUTPUT_CONTRACT_INVALID,
                "Offline parser results require synthetic markers.",
            )
        if not self.complete:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_TRUNCATED_OUTPUT, "Incomplete parser result cannot be accepted."
            )
        if len(self.source_digest) != 64 or any(
            character not in "0123456789abcdef" for character in self.source_digest
        ):
            raise CyberOSError(ErrorCode.PORT_SCAN_PARSE_FAILED, "Source digest is invalid.")


class NetworkScanParser:
    """Parse one bounded fixture payload without external resolution."""

    def parse(
        self,
        payload: bytes,
        *,
        output_format: MachineOutputFormat,
        scope_id: ScopeId,
        target_id: TargetId,
        target_kind: TargetKind,
        canonical_target: str,
        limits: ParserLimits = _DEFAULT_PARSER_LIMITS,
        truncated: bool = False,
    ) -> NetworkScanParseResult:
        if not isinstance(payload, bytes) or len(payload) > limits.max_payload_bytes:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_LIMIT_EXCEEDED, "Parser payload exceeds byte budget."
            )
        if truncated:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_TRUNCATED_OUTPUT, "Truncated output is rejected."
            )
        normalized_target = validate_target_value(target_kind, canonical_target)
        redacted = _redact(payload, limits.max_payload_bytes)
        if output_format is MachineOutputFormat.XML:
            services = self._parse_xml(redacted, normalized_target, limits)
        elif output_format is MachineOutputFormat.JSON:
            services = self._parse_json(redacted, normalized_target, limits)
        else:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_OUTPUT_CONTRACT_INVALID, "Output format is unsupported."
            )
        observations = tuple(
            ReconObservation(
                observation_type="service",
                value=f"{service.service_name or 'unknown'}@{service.host}:{service.port}",
                metadata=tuple(
                    sorted(
                        {
                            "port": str(service.port),
                            "product": service.product or "",
                            "protocol": service.protocol,
                            "service_name": service.service_name or "",
                            "service_version": service.version or "",
                            "state": service.state,
                            "transport": service.protocol,
                        }.items()
                    )
                ),
            )
            for service in services
            if service.state == "open"
        )
        return NetworkScanParseResult(
            schema_version=_SCHEMA_VERSION,
            output_format=output_format,
            scope_id=scope_id,
            target_id=target_id,
            canonical_target=normalized_target,
            services=services,
            observations=observations,
            source_digest=hashlib.sha256(redacted).hexdigest(),
            redaction_applied=True,
            synthetic=True,
            offline_fixture=True,
            complete=True,
        )

    def _parse_xml(
        self, payload: bytes, expected_target: str, limits: ParserLimits
    ) -> tuple[ParsedPortService, ...]:
        upper = payload.upper()
        if any(
            marker in upper for marker in (b"<!DOCTYPE", b"<!ENTITY", b"SYSTEM", b"PUBLIC", b"<![")
        ):
            raise CyberOSError(
                ErrorCode.PORT_SCAN_PARSE_FAILED, "XML external entities are not permitted."
            )
        services: list[ParsedPortService] = []
        depth = 0
        root_seen = False
        current_target: str | None = None

        def reject_doctype(
            _name: str, _system_id: str | None, _public_id: str | None, _has_internal_subset: int
        ) -> None:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_PARSE_FAILED,
                "XML external declarations are not permitted.",
            )

        def reject_entity(
            _entity_name: str,
            _is_parameter_entity: int,
            _value: str | None,
            _base: str | None,
            _system_id: str | None,
            _public_id: str | None,
            _notation_name: str | None,
        ) -> None:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_PARSE_FAILED,
                "XML entity declarations are not permitted.",
            )

        def reject_external(
            _context: str | None,
            _base: str | None,
            _system_id: str | None,
            _public_id: str | None,
        ) -> int:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_PARSE_FAILED,
                "XML external entities are not permitted.",
            )

        def start(name: str, attributes: dict[str, str]) -> None:
            nonlocal depth, root_seen, current_target
            depth += 1
            if depth > limits.max_depth:
                raise CyberOSError(ErrorCode.PORT_SCAN_LIMIT_EXCEEDED, "XML depth budget exceeded.")
            if not root_seen:
                root_seen = True
                if name != "scan" or set(attributes) != {"schema_version", "target"}:
                    raise CyberOSError(
                        ErrorCode.PORT_SCAN_SCHEMA_UNSUPPORTED,
                        "XML schema envelope is unsupported.",
                    )
                if (
                    attributes["schema_version"] != _SCHEMA_VERSION
                    or attributes["target"] != expected_target
                ):
                    raise CyberOSError(
                        ErrorCode.PORT_SCAN_CONTEXT_MISMATCH,
                        "XML target context does not match.",
                    )
                return
            if name == "host":
                if set(attributes) != {"target"} or attributes["target"] != expected_target:
                    raise CyberOSError(
                        ErrorCode.PORT_SCAN_CONTEXT_MISMATCH,
                        "XML host target does not match.",
                    )
                if current_target is not None:
                    raise CyberOSError(
                        ErrorCode.PORT_SCAN_PARSE_FAILED,
                        "Nested XML hosts are invalid.",
                    )
                current_target = expected_target
                return
            if name == "port":
                if current_target != expected_target or set(attributes) - {
                    "number",
                    "protocol",
                    "state",
                    "service",
                    "product",
                    "version",
                }:
                    raise CyberOSError(
                        ErrorCode.PORT_SCAN_PARSE_FAILED,
                        "XML port fields are invalid.",
                    )
                services.append(self._service_from_mapping(attributes, expected_target, limits))
                if len(services) > limits.max_services:
                    raise CyberOSError(
                        ErrorCode.PORT_SCAN_LIMIT_EXCEEDED,
                        "XML service budget exceeded.",
                    )
                return
            raise CyberOSError(ErrorCode.PORT_SCAN_PARSE_FAILED, "XML element is not allowlisted.")

        def end(name: str) -> None:
            nonlocal depth, current_target
            if name == "host":
                current_target = None
            depth -= 1

        parser = expat.ParserCreate()
        parser.StartElementHandler = start
        parser.EndElementHandler = end
        parser.StartDoctypeDeclHandler = reject_doctype
        parser.EntityDeclHandler = reject_entity
        parser.ExternalEntityRefHandler = reject_external
        try:
            parser.Parse(payload, True)
        except CyberOSError:
            raise
        except expat.ExpatError as exc:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_PARSE_FAILED, "XML fixture is malformed."
            ) from exc
        if not root_seen or depth != 0:
            raise CyberOSError(ErrorCode.PORT_SCAN_PARSE_FAILED, "XML fixture is incomplete.")
        return tuple(sorted(services, key=lambda item: (item.host, item.port, item.protocol)))

    def _parse_json(
        self, payload: bytes, expected_target: str, limits: ParserLimits
    ) -> tuple[ParsedPortService, ...]:
        try:
            value = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_PARSE_FAILED, "JSON fixture is malformed."
            ) from exc
        if not isinstance(value, dict) or set(value) != {"schema_version", "target", "services"}:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_SCHEMA_UNSUPPORTED, "JSON schema envelope is unsupported."
            )
        if value.get("schema_version") != _SCHEMA_VERSION or value.get("target") != expected_target:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_CONTEXT_MISMATCH, "JSON target context does not match."
            )
        raw_services = value.get("services")
        if not isinstance(raw_services, list) or len(raw_services) > limits.max_services:
            raise CyberOSError(ErrorCode.PORT_SCAN_LIMIT_EXCEEDED, "JSON service budget exceeded.")
        services = tuple(
            self._service_from_json(item, expected_target, limits) for item in raw_services
        )
        return tuple(sorted(services, key=lambda item: (item.host, item.port, item.protocol)))

    @staticmethod
    def _service_from_mapping(
        item: dict[str, str], expected_target: str, limits: ParserLimits
    ) -> ParsedPortService:
        try:
            port = int(item["number"])
            protocol = item["protocol"]
            state = item["state"]
        except (KeyError, ValueError) as exc:
            raise CyberOSError(
                ErrorCode.PORT_SCAN_PARSE_FAILED, "Port service fields are invalid."
            ) from exc
        if (
            not 1 <= port <= 65535
            or protocol not in _ALLOWED_PROTOCOLS
            or state not in _ALLOWED_STATES
        ):
            raise CyberOSError(ErrorCode.PORT_SCAN_PARSE_FAILED, "Port service value is invalid.")
        service_name = item.get("service")
        product = item.get("product")
        version = item.get("version")
        for value in (service_name, product, version):
            if value is not None and len(value.encode()) > limits.max_field_bytes:
                raise CyberOSError(
                    ErrorCode.PORT_SCAN_LIMIT_EXCEEDED, "Service field budget exceeded."
                )
        return ParsedPortService(
            host=expected_target,
            port=port,
            protocol=protocol,
            state=state,
            service_name=service_name,
            product=product,
            version=version,
        )

    @classmethod
    def _service_from_json(
        cls, item: object, expected_target: str, limits: ParserLimits
    ) -> ParsedPortService:
        if not isinstance(item, dict) or set(item) - {
            "port",
            "protocol",
            "state",
            "service",
            "product",
            "version",
        }:
            raise CyberOSError(ErrorCode.PORT_SCAN_PARSE_FAILED, "JSON service fields are invalid.")
        if not all(isinstance(item.get(key), (str, int)) for key in ("port", "protocol", "state")):
            raise CyberOSError(ErrorCode.PORT_SCAN_PARSE_FAILED, "JSON service types are invalid.")
        return cls._service_from_mapping(
            {
                "number": str(item["port"]),
                "protocol": str(item["protocol"]),
                "state": str(item["state"]),
                **{
                    key: str(item[key])
                    for key in ("service", "product", "version")
                    if key in item and item[key] is not None
                },
            },
            expected_target,
            limits,
        )


def _redact(payload: bytes, maximum: int) -> bytes:
    text = payload.decode("utf-8", errors="replace")
    redacted = _SECRET_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    redacted = _PATH_RE.sub("[PATH_REDACTED]", redacted)
    redacted = _CONTROL_RE.sub("", redacted)
    encoded = redacted.encode("utf-8")
    if len(encoded) > maximum:
        raise CyberOSError(
            ErrorCode.PORT_SCAN_LIMIT_EXCEEDED, "Redacted parser payload exceeds byte budget."
        )
    return encoded
