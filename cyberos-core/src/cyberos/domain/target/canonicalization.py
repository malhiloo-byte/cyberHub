"""Pure, local-only Target parsing and canonicalization.

This module deliberately performs no DNS, HTTP, subprocess, or filesystem work.
"""

from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network
from urllib.parse import SplitResult, urlsplit, urlunsplit

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.target.primitives import TargetKind


class TargetCanonicalizationError(CyberOSError):
    """Safe typed error raised when a Target value cannot be canonicalized."""

    def __init__(self, code: ErrorCode, message: str, *, kind: TargetKind) -> None:
        super().__init__(code, message, details={"kind": kind.value})


@dataclass(frozen=True, slots=True)
class CanonicalTarget:
    """Canonical value object returned by the pure parser."""

    kind: TargetKind
    value: str


class TargetCanonicalizer:
    """Canonicalize one explicitly typed target without side effects."""

    @classmethod
    def canonicalize(cls, kind: TargetKind, value: str) -> CanonicalTarget:
        kind = cls._coerce_kind(kind)
        raw = cls._prepare(value, kind)
        handlers = {
            TargetKind.FQDN: cls._fqdn,
            TargetKind.WILDCARD: cls._wildcard,
            TargetKind.IPV4: cls._ipv4,
            TargetKind.IPV6: cls._ipv6,
            TargetKind.CIDR: cls._cidr,
            TargetKind.URL: cls._url,
        }
        return CanonicalTarget(kind=kind, value=handlers[kind](raw, kind))

    @staticmethod
    def _coerce_kind(kind: TargetKind) -> TargetKind:
        if isinstance(kind, TargetKind):
            return kind
        try:
            return TargetKind(kind)
        except (TypeError, ValueError) as exc:
            raise CyberOSError(
                ErrorCode.TARGET_KIND_INVALID,
                "Target kind is not supported.",
            ) from exc

    @staticmethod
    def _prepare(value: str, kind: TargetKind) -> str:
        if not isinstance(value, str):
            raise TargetCanonicalizationError(
                ErrorCode.TARGET_VALUE_INVALID,
                "Target value must be text.",
                kind=kind,
            )
        raw = value.strip()
        if not raw:
            raise TargetCanonicalizationError(
                ErrorCode.TARGET_VALUE_INVALID,
                "Target value cannot be empty.",
                kind=kind,
            )
        if any(ord(char) < 32 or ord(char) == 127 for char in raw):
            raise TargetCanonicalizationError(
                ErrorCode.TARGET_CONTROL_CHARACTER,
                "Target value contains a control character.",
                kind=kind,
            )
        if any(char.isspace() for char in raw):
            raise TargetCanonicalizationError(
                ErrorCode.TARGET_VALUE_INVALID,
                "Target value cannot contain whitespace.",
                kind=kind,
            )
        return raw

    @classmethod
    def _fqdn(cls, raw: str, kind: TargetKind) -> str:
        if "*" in raw or "/" in raw or ":" in raw:
            raise TargetCanonicalizationError(
                ErrorCode.TARGET_VALUE_INVALID,
                "FQDN must be a hostname without wildcard, port, or path.",
                kind=kind,
            )
        candidate = raw[:-1] if raw.endswith(".") else raw
        labels = candidate.split(".")
        if not candidate or any(not label for label in labels) or len(candidate) > 253:
            raise TargetCanonicalizationError(
                ErrorCode.TARGET_VALUE_INVALID,
                "FQDN has an invalid label structure.",
                kind=kind,
            )
        ascii_labels: list[str] = []
        for label in labels:
            try:
                encoded = label.encode("idna").decode("ascii").lower()
            except UnicodeError as exc:
                raise TargetCanonicalizationError(
                    ErrorCode.TARGET_VALUE_INVALID,
                    "FQDN label cannot be encoded with the fixed IDNA policy.",
                    kind=kind,
                ) from exc
            if not 1 <= len(encoded) <= 63 or encoded[0] == "-" or encoded[-1] == "-":
                raise TargetCanonicalizationError(
                    ErrorCode.TARGET_VALUE_INVALID,
                    "FQDN label length or hyphen placement is invalid.",
                    kind=kind,
                )
            if not all(char.isalnum() or char == "-" for char in encoded):
                raise TargetCanonicalizationError(
                    ErrorCode.TARGET_VALUE_INVALID,
                    "FQDN label contains an unsupported character.",
                    kind=kind,
                )
            ascii_labels.append(encoded)
        try:
            parsed = ip_address(".".join(ascii_labels))
        except ValueError:
            parsed = None
        if parsed is not None:
            raise TargetCanonicalizationError(
                ErrorCode.TARGET_VALUE_INVALID,
                "An IP address must use an IP Target kind, not FQDN.",
                kind=kind,
            )
        return ".".join(ascii_labels)

    @classmethod
    def _wildcard(cls, raw: str, kind: TargetKind) -> str:
        if not raw.startswith("*.") or raw.count("*") != 1:
            raise TargetCanonicalizationError(
                ErrorCode.TARGET_WILDCARD_INVALID,
                "Wildcard must contain exactly one leftmost '*.' label.",
                kind=kind,
            )
        suffix = cls._fqdn(raw[2:], kind)
        if suffix.count(".") < 1:
            raise TargetCanonicalizationError(
                ErrorCode.TARGET_WILDCARD_INVALID,
                "Wildcard suffix must contain at least two hostname labels.",
                kind=kind,
            )
        return f"*.{suffix}"

    @classmethod
    def _ipv4(cls, raw: str, kind: TargetKind) -> str:
        try:
            address = IPv4Address(raw)
        except ValueError as exc:
            raise TargetCanonicalizationError(
                ErrorCode.TARGET_IP_INVALID,
                "Value is not a valid IPv4 address.",
                kind=kind,
            ) from exc
        if address.is_unspecified:
            raise TargetCanonicalizationError(
                ErrorCode.TARGET_NETWORK_UNSAFE,
                "Unspecified IPv4 address is not an authorized target.",
                kind=kind,
            )
        return str(address)

    @classmethod
    def _ipv6(cls, raw: str, kind: TargetKind) -> str:
        try:
            address = IPv6Address(raw)
        except ValueError as exc:
            raise TargetCanonicalizationError(
                ErrorCode.TARGET_IP_INVALID,
                "Value is not a valid IPv6 address.",
                kind=kind,
            ) from exc
        if address.is_unspecified:
            raise TargetCanonicalizationError(
                ErrorCode.TARGET_NETWORK_UNSAFE,
                "Unspecified IPv6 address is not an authorized target.",
                kind=kind,
            )
        return address.compressed.lower()

    @classmethod
    def _cidr(cls, raw: str, kind: TargetKind) -> str:
        if "/" not in raw:
            raise TargetCanonicalizationError(
                ErrorCode.TARGET_VALUE_INVALID,
                "CIDR must include an explicit prefix length.",
                kind=kind,
            )
        try:
            network = ip_network(raw, strict=False)
        except ValueError as exc:
            raise TargetCanonicalizationError(
                ErrorCode.TARGET_IP_INVALID,
                "Value is not a valid CIDR network.",
                kind=kind,
            ) from exc
        if network.prefixlen == 0:
            raise TargetCanonicalizationError(
                ErrorCode.TARGET_NETWORK_UNSAFE,
                "Default-route CIDR networks are not authorized targets.",
                kind=kind,
            )
        return network.with_prefixlen

    @classmethod
    def _url(cls, raw: str, kind: TargetKind) -> str:
        try:
            parsed = urlsplit(raw)
            port = parsed.port
        except ValueError as exc:
            raise TargetCanonicalizationError(
                ErrorCode.TARGET_URL_INVALID,
                "URL contains an invalid port or authority.",
                kind=kind,
            ) from exc
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise TargetCanonicalizationError(
                ErrorCode.TARGET_URL_INVALID,
                "URL must use http or https and include a host.",
                kind=kind,
            )
        if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
            raise TargetCanonicalizationError(
                ErrorCode.TARGET_URL_INVALID,
                "URL credentials are not permitted.",
                kind=kind,
            )
        if parsed.fragment:
            raise TargetCanonicalizationError(
                ErrorCode.TARGET_URL_INVALID,
                "URL fragments are not permitted for targets.",
                kind=kind,
            )
        if "*" in parsed.hostname:
            raise TargetCanonicalizationError(
                ErrorCode.TARGET_URL_INVALID,
                "URL wildcards are not permitted; use the wildcard Target kind.",
                kind=kind,
            )
        hostname = cls._canonical_url_host(parsed.hostname, kind)
        scheme = parsed.scheme.lower()
        effective_port = ""
        if port is not None and port not in {80 if scheme == "http" else 443}:
            effective_port = f":{port}"
        authority = hostname
        if ":" in hostname and not hostname.startswith("["):
            authority = f"[{hostname}]"
        authority += effective_port
        path = parsed.path or "/"
        if not path.startswith("/"):
            raise TargetCanonicalizationError(
                ErrorCode.TARGET_URL_INVALID,
                "URL path must be absolute.",
                kind=kind,
            )
        result = urlunsplit(SplitResult(scheme, authority, path, parsed.query, ""))
        return result

    @classmethod
    def _canonical_url_host(cls, hostname: str, kind: TargetKind) -> str:
        try:
            address = ip_address(hostname)
        except ValueError:
            return cls._fqdn(hostname, kind)
        if address.is_unspecified:
            raise TargetCanonicalizationError(
                ErrorCode.TARGET_NETWORK_UNSAFE,
                "Unspecified IP address is not an authorized URL host.",
                kind=kind,
            )
        return address.compressed.lower() if isinstance(address, IPv6Address) else str(address)


class CandidateParser:
    """Parse a candidate using an explicit TargetKind; inference is intentionally absent."""

    @staticmethod
    def parse(value: str, kind: TargetKind) -> CanonicalTarget:
        return TargetCanonicalizer.canonicalize(kind, value)
