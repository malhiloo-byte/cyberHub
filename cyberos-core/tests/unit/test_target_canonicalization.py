import pytest

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.target.canonicalization import (
    CandidateParser,
    TargetCanonicalizationError,
    TargetCanonicalizer,
)
from cyberos.domain.target.primitives import TargetKind


def canonical(kind: TargetKind, value: str) -> str:
    return TargetCanonicalizer.canonicalize(kind, value).value


@pytest.mark.parametrize(
    ("kind", "raw", "expected"),
    [
        (TargetKind.FQDN, "  EXAMPLE.Com. ", "example.com"),
        (TargetKind.FQDN, "BÜCHER.Example", "xn--bcher-kva.example"),
        (TargetKind.WILDCARD, "*.Example.COM.", "*.example.com"),
        (TargetKind.IPV4, "192.168.1.1", "192.168.1.1"),
        (TargetKind.IPV6, "2001:0DB8:0:0:0:0:0:1", "2001:db8::1"),
        (TargetKind.CIDR, "192.168.10.20/24", "192.168.10.0/24"),
        (TargetKind.CIDR, "2001:0DB8::1234/64", "2001:db8::/64"),
        (TargetKind.URL, "HTTPS://Example.COM:443/api?b=2&a=1", "https://example.com/api?b=2&a=1"),
        (TargetKind.URL, "http://Example.COM:8080", "http://example.com:8080/"),
    ],
)
def test_target_kinds_have_deterministic_canonical_forms(
    kind: TargetKind, raw: str, expected: str
) -> None:
    assert canonical(kind, raw) == expected
    assert CandidateParser.parse(raw, kind).value == expected


@pytest.mark.parametrize(
    ("kind", "raw"),
    [
        (TargetKind.FQDN, "example..com"),
        (TargetKind.FQDN, "-example.com"),
        (TargetKind.FQDN, "example-.com"),
        (TargetKind.FQDN, "10.0.0.1"),
        (TargetKind.FQDN, "example\n.com"),
    ],
)
def test_fqdn_rejects_malformed_or_control_values(kind: TargetKind, raw: str) -> None:
    with pytest.raises(TargetCanonicalizationError) as captured:
        canonical(kind, raw)

    assert captured.value.code in {
        ErrorCode.TARGET_VALUE_INVALID,
        ErrorCode.TARGET_CONTROL_CHARACTER,
    }


@pytest.mark.parametrize("raw", ["*", "*.*", "admin.*.com", "*.com", "example.com"])
def test_wildcard_requires_leftmost_label_and_safe_suffix(raw: str) -> None:
    with pytest.raises(TargetCanonicalizationError) as captured:
        canonical(TargetKind.WILDCARD, raw)

    assert captured.value.code is ErrorCode.TARGET_WILDCARD_INVALID


@pytest.mark.parametrize("kind", [TargetKind.IPV4, TargetKind.IPV6])
@pytest.mark.parametrize("raw", ["not-an-ip", "0.0.0.0/0", "::/0"])
def test_ip_kinds_reject_invalid_or_network_forms(kind: TargetKind, raw: str) -> None:
    with pytest.raises(TargetCanonicalizationError) as captured:
        canonical(kind, raw)

    assert captured.value.code in {
        ErrorCode.TARGET_IP_INVALID,
        ErrorCode.TARGET_NETWORK_UNSAFE,
    }


@pytest.mark.parametrize("raw", ["0.0.0.0/0", "::/0", "10.0.0.0", "2001:db8::"])
def test_cidr_requires_prefix_and_rejects_default_routes(raw: str) -> None:
    with pytest.raises(TargetCanonicalizationError) as captured:
        canonical(TargetKind.CIDR, raw)

    assert captured.value.code in {
        ErrorCode.TARGET_IP_INVALID,
        ErrorCode.TARGET_VALUE_INVALID,
        ErrorCode.TARGET_NETWORK_UNSAFE,
    }


@pytest.mark.parametrize(
    "raw",
    [
        "https://user:pass@example.com/secret",
        "https://example.com/path#fragment",
        "ftp://example.com/file",
        "https://*.example.com/",
        "https://example.com:invalid/",
        "https://example.com/path with spaces",
    ],
)
def test_url_rejects_credentials_fragments_unsafe_syntax(raw: str) -> None:
    with pytest.raises(TargetCanonicalizationError) as captured:
        canonical(TargetKind.URL, raw)

    assert captured.value.code in {
        ErrorCode.TARGET_URL_INVALID,
        ErrorCode.TARGET_VALUE_INVALID,
    }


def test_non_text_and_unknown_kind_are_typed_errors_without_raw_value_leakage() -> None:
    with pytest.raises(TargetCanonicalizationError) as captured:
        TargetCanonicalizer.canonicalize(TargetKind.FQDN, 123)  # type: ignore[arg-type]

    assert captured.value.code is ErrorCode.TARGET_VALUE_INVALID
    assert "123" not in captured.value.message

    with pytest.raises(CyberOSError) as unknown:
        TargetCanonicalizer.canonicalize("unknown", "example.com")  # type: ignore[arg-type]

    assert unknown.value.code is ErrorCode.TARGET_KIND_INVALID
