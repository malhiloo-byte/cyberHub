from datetime import UTC, datetime, timedelta

import pytest

from cyberos.core.ids import new_id
from cyberos.domain.scope.matcher import MatchDecision, ScopeMatcher
from cyberos.domain.scope.model import Scope
from cyberos.domain.target.model import Target
from cyberos.domain.target.primitives import TargetKind, TargetRule

NOW = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)


def authorized_scope(*targets: Target, expires_at=None) -> Scope:
    scope_id = targets[0].scope_id if targets else None
    scope = Scope.create(new_id(), "Matcher Scope", scope_id=scope_id, now=NOW)
    for target in targets:
        scope = scope.add_target(target)
    validated = scope.mark_validated(at=NOW)
    return validated.authorize("approval-0.4f", at=NOW, expires_at=expires_at)


def target(scope: Scope, rule: TargetRule, kind: TargetKind, value: str) -> Target:
    return Target.create(scope.id, rule, kind, value, now=NOW)


def test_exclude_always_wins_over_include() -> None:
    scope = Scope.create(new_id(), "Matcher Scope", now=NOW)
    include = target(scope, TargetRule.INCLUDE, TargetKind.FQDN, "admin.example.com")
    exclude = target(scope, TargetRule.EXCLUDE, TargetKind.WILDCARD, "*.example.com")
    result = ScopeMatcher.match(
        authorized_scope(include, exclude),
        "admin.example.com",
        TargetKind.FQDN,
        evaluated_at=NOW,
    )
    assert result.decision is MatchDecision.EXCLUDED
    assert result.matched_target_id == exclude.id
    assert result.matching_rule is TargetRule.EXCLUDE
    assert result.reason == "excluded_by_explicit_rule"


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        ("EXAMPLE.COM.", MatchDecision.INCLUDED),
        ("sub.example.com", MatchDecision.DENIED_OUT_OF_SCOPE),
        ("not-example.com", MatchDecision.DENIED_OUT_OF_SCOPE),
    ],
)
def test_fqdn_is_case_insensitive_exact_match(candidate: str, expected: MatchDecision) -> None:
    scope = Scope.create(new_id(), "Matcher Scope", now=NOW)
    rule = target(scope, TargetRule.INCLUDE, TargetKind.FQDN, "example.com")
    result = ScopeMatcher.match(
        authorized_scope(rule), candidate, TargetKind.FQDN, evaluated_at=NOW
    )
    assert result.decision is expected


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        ("example.com", MatchDecision.INCLUDED),
        ("a.example.com", MatchDecision.INCLUDED),
        ("a.b.example.com", MatchDecision.INCLUDED),
        ("badexample.com", MatchDecision.DENIED_OUT_OF_SCOPE),
        ("example.com.evil.com", MatchDecision.DENIED_OUT_OF_SCOPE),
    ],
)
def test_wildcard_matches_root_and_subdomains_only(candidate: str, expected: MatchDecision) -> None:
    scope = Scope.create(new_id(), "Matcher Scope", now=NOW)
    rule = target(scope, TargetRule.INCLUDE, TargetKind.WILDCARD, "*.example.com")
    result = ScopeMatcher.match(
        authorized_scope(rule), candidate, TargetKind.FQDN, evaluated_at=NOW
    )
    assert result.decision is expected


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        ("10.10.0.1", MatchDecision.INCLUDED),
        ("10.10.0.255", MatchDecision.INCLUDED),
        ("10.10.1.1", MatchDecision.DENIED_OUT_OF_SCOPE),
        ("10.9.255.255", MatchDecision.DENIED_OUT_OF_SCOPE),
    ],
)
def test_ipv4_cidr_boundaries(candidate: str, expected: MatchDecision) -> None:
    scope = Scope.create(new_id(), "Matcher Scope", now=NOW)
    rule = target(scope, TargetRule.INCLUDE, TargetKind.CIDR, "10.10.0.0/24")
    result = ScopeMatcher.match(
        authorized_scope(rule), candidate, TargetKind.IPV4, evaluated_at=NOW
    )
    assert result.decision is expected


def test_ipv6_compression_and_cidr_membership() -> None:
    scope = Scope.create(new_id(), "Matcher Scope", now=NOW)
    rule = target(scope, TargetRule.INCLUDE, TargetKind.CIDR, "2001:db8:abcd::/48")
    result = ScopeMatcher.match(
        authorized_scope(rule), "2001:0DB8:ABCD:0:0:0:0:42", TargetKind.IPV6, evaluated_at=NOW
    )
    assert result.decision is MatchDecision.INCLUDED


def test_exact_ip_rules_do_not_cross_address_families() -> None:
    scope = Scope.create(new_id(), "Matcher Scope", now=NOW)
    rule = target(scope, TargetRule.INCLUDE, TargetKind.IPV4, "192.0.2.10")
    ipv6_result = ScopeMatcher.match(
        authorized_scope(rule), "2001:db8::10", TargetKind.IPV6, evaluated_at=NOW
    )
    ipv4_result = ScopeMatcher.match(
        authorized_scope(rule), "192.0.2.10", TargetKind.IPV4, evaluated_at=NOW
    )
    assert ipv6_result.decision is MatchDecision.DENIED_OUT_OF_SCOPE
    assert ipv4_result.decision is MatchDecision.INCLUDED


def test_url_host_is_evaluated_against_fqdn_and_cidr_rules() -> None:
    scope = Scope.create(new_id(), "Matcher Scope", now=NOW)
    fqdn = target(scope, TargetRule.INCLUDE, TargetKind.FQDN, "api.example.com")
    result = ScopeMatcher.match(
        authorized_scope(fqdn),
        "https://API.EXAMPLE.COM:443/v1?query=1",
        TargetKind.URL,
        evaluated_at=NOW,
    )
    assert result.decision is MatchDecision.INCLUDED


def test_url_rule_requires_exact_canonical_url() -> None:
    scope = Scope.create(new_id(), "Matcher Scope", now=NOW)
    rule = target(
        scope,
        TargetRule.INCLUDE,
        TargetKind.URL,
        "https://example.com:443/api?x=1",
    )
    exact = ScopeMatcher.match(
        authorized_scope(rule), "https://example.com/api?x=1", TargetKind.URL, evaluated_at=NOW
    )
    different_query = ScopeMatcher.match(
        authorized_scope(rule), "https://example.com/api?x=2", TargetKind.URL, evaluated_at=NOW
    )
    assert exact.decision is MatchDecision.INCLUDED
    assert different_query.decision is MatchDecision.DENIED_OUT_OF_SCOPE


@pytest.mark.parametrize(
    "candidate",
    [
        "https://user:pass@example.com/",
        "https://example.com/#fragment",
        "not a target",
    ],
)
def test_invalid_or_unsafe_candidates_fail_closed(candidate: str) -> None:
    scope = Scope.create(new_id(), "Matcher Scope", now=NOW)
    rule = target(scope, TargetRule.INCLUDE, TargetKind.FQDN, "example.com")
    result = ScopeMatcher.match(authorized_scope(rule), candidate, TargetKind.URL, evaluated_at=NOW)
    assert result.decision is MatchDecision.DENIED_OUT_OF_SCOPE
    assert result.matched_target_id is None
    assert result.reason == "candidate_invalid"


def test_non_authorized_scope_fails_closed_even_when_rule_matches() -> None:
    scope = Scope.create(new_id(), "Matcher Scope", now=NOW)
    rule = target(scope, TargetRule.INCLUDE, TargetKind.FQDN, "example.com")
    result = ScopeMatcher.match(
        scope.add_target(rule), "example.com", TargetKind.FQDN, evaluated_at=NOW
    )
    assert result.decision is MatchDecision.DENIED_OUT_OF_SCOPE
    assert result.reason == "scope_not_authorized"


def test_expired_authorized_scope_fails_closed() -> None:
    scope = Scope.create(new_id(), "Matcher Scope", now=NOW)
    rule = target(scope, TargetRule.INCLUDE, TargetKind.FQDN, "example.com")
    authorized = authorized_scope(rule, expires_at=NOW + timedelta(minutes=1))
    result = ScopeMatcher.match(
        authorized, "example.com", TargetKind.FQDN, evaluated_at=NOW + timedelta(minutes=1)
    )
    assert result.decision is MatchDecision.DENIED_OUT_OF_SCOPE
    assert result.reason == "scope_expired"


def test_archived_target_is_not_an_active_match() -> None:
    scope = Scope.create(new_id(), "Matcher Scope", now=NOW)
    rule = target(scope, TargetRule.INCLUDE, TargetKind.FQDN, "example.com")
    archived = rule.archive(at=NOW + timedelta(minutes=1))
    result = ScopeMatcher.match(
        authorized_scope(archived), "example.com", TargetKind.FQDN, evaluated_at=NOW
    )
    assert result.decision is MatchDecision.DENIED_OUT_OF_SCOPE
    assert result.reason == "no_matching_rule"
