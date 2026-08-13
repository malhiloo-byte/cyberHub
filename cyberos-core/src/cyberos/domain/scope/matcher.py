"""Pure, deterministic scope matching with fail-closed safety semantics."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_address, ip_network
from urllib.parse import urlsplit

from cyberos.core.errors import ErrorCode
from cyberos.core.time import ensure_utc
from cyberos.domain.scope.model import Scope
from cyberos.domain.scope.primitives import ScopeStatus
from cyberos.domain.target.canonicalization import TargetCanonicalizationError, TargetCanonicalizer
from cyberos.domain.target.model import Target
from cyberos.domain.target.primitives import TargetId, TargetKind, TargetRule, TargetStatus


class MatchDecision(StrEnum):
    INCLUDED = "included"
    EXCLUDED = "excluded"
    DENIED_OUT_OF_SCOPE = "denied_out_of_scope"


@dataclass(frozen=True, slots=True)
class MatchResult:
    decision: MatchDecision
    matched_target_id: TargetId | None
    matching_rule: TargetRule | None
    reason: str


@dataclass(frozen=True, slots=True)
class _Candidate:
    kind: TargetKind
    value: str
    host: str | None
    ip: IPv4Address | IPv6Address | None
    network: IPv4Network | IPv6Network | None


class ScopeMatcher:
    """Evaluate one candidate against an authorized Scope without side effects."""

    @classmethod
    def match(
        cls,
        scope: Scope,
        candidate: str,
        candidate_kind: TargetKind,
        *,
        evaluated_at: datetime,
    ) -> MatchResult:
        evaluation_time = ensure_utc(evaluated_at)
        if scope.status is not ScopeStatus.AUTHORIZED:
            return cls._denied("scope_not_authorized")
        if scope.expires_at is not None and scope.expires_at <= evaluation_time:
            return cls._denied("scope_expired")
        try:
            parsed = cls._parse_candidate(candidate, candidate_kind)
        except TargetCanonicalizationError:
            return cls._denied("candidate_invalid")

        active_targets = sorted(
            (target for target in scope.targets if target.status is TargetStatus.ACTIVE),
            key=lambda target: str(target.id),
        )
        for target in active_targets:
            if target.rule is TargetRule.EXCLUDE and cls._matches(target, parsed):
                return MatchResult(
                    MatchDecision.EXCLUDED,
                    target.id,
                    TargetRule.EXCLUDE,
                    "excluded_by_explicit_rule",
                )
        for target in active_targets:
            if target.rule is TargetRule.INCLUDE and cls._matches(target, parsed):
                return MatchResult(
                    MatchDecision.INCLUDED,
                    target.id,
                    TargetRule.INCLUDE,
                    "included_by_authorized_rule",
                )
        return cls._denied("no_matching_rule")

    @staticmethod
    def _denied(reason: str) -> MatchResult:
        return MatchResult(MatchDecision.DENIED_OUT_OF_SCOPE, None, None, reason)

    @classmethod
    def _parse_candidate(cls, value: str, kind: TargetKind) -> _Candidate:
        canonical = TargetCanonicalizer.canonicalize(kind, value)
        if canonical.kind is TargetKind.FQDN:
            return _Candidate(canonical.kind, canonical.value, canonical.value, None, None)
        if canonical.kind is TargetKind.WILDCARD:
            return _Candidate(canonical.kind, canonical.value, None, None, None)
        if canonical.kind in {TargetKind.IPV4, TargetKind.IPV6}:
            address = ip_address(canonical.value)
            return _Candidate(canonical.kind, canonical.value, None, address, None)
        if canonical.kind is TargetKind.CIDR:
            network = ip_network(canonical.value, strict=True)
            return _Candidate(canonical.kind, canonical.value, None, None, network)

        parsed = urlsplit(canonical.value)
        host = parsed.hostname
        if host is None:
            raise TargetCanonicalizationError(
                code=ErrorCode.TARGET_URL_INVALID,
                message="URL host is unavailable.",
                kind=TargetKind.URL,
            )
        host_address: IPv4Address | IPv6Address | None
        try:
            host_address = ip_address(host)
        except ValueError:
            host_address = None
        return _Candidate(canonical.kind, canonical.value, host, host_address, None)

    @classmethod
    def _matches(cls, target: Target, candidate: _Candidate) -> bool:
        if target.kind is TargetKind.URL:
            return candidate.kind is TargetKind.URL and target.value == candidate.value
        if target.kind is TargetKind.FQDN:
            return candidate.host == target.value
        if target.kind is TargetKind.WILDCARD:
            if candidate.host is None:
                return False
            suffix = target.value[2:]
            return candidate.host == suffix or candidate.host.endswith(f".{suffix}")
        if target.kind in {TargetKind.IPV4, TargetKind.IPV6}:
            return candidate.ip is not None and target.value == str(candidate.ip)
        if target.kind is TargetKind.CIDR:
            rule_network = ip_network(target.value, strict=True)
            if candidate.ip is not None:
                return candidate.ip in rule_network
            if isinstance(candidate.network, IPv4Network) and isinstance(rule_network, IPv4Network):
                return candidate.network.subnet_of(rule_network)
            if isinstance(candidate.network, IPv6Network) and isinstance(rule_network, IPv6Network):
                return candidate.network.subnet_of(rule_network)
            return False
        return False
