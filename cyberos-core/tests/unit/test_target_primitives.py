from uuid import UUID, uuid1

import pytest

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.domain.scope.primitives import ScopeStatus, new_scope_id, validate_scope_id
from cyberos.domain.target.primitives import (
    TargetId,
    TargetKind,
    TargetRule,
    new_target_id,
    validate_target_id,
)


def test_scope_and_target_ids_are_uuid4_and_strongly_typed() -> None:
    scope_id = new_scope_id()
    target_id = new_target_id()

    assert isinstance(scope_id, UUID)
    assert isinstance(target_id, UUID)
    assert scope_id.version == 4
    assert target_id.version == 4
    assert validate_scope_id(scope_id) == scope_id
    assert validate_target_id(target_id) == target_id
    assert TargetId(target_id) == target_id


@pytest.mark.parametrize("validator", [validate_scope_id, validate_target_id])
def test_identifiers_reject_non_uuid4(validator) -> None:
    with pytest.raises(CyberOSError) as captured:
        validator(uuid1())

    assert captured.value.code is ErrorCode.DOMAIN_VALIDATION_FAILED


def test_enums_are_stable_string_values() -> None:
    assert ScopeStatus.AUTHORIZED.value == "authorized"
    assert TargetRule.INCLUDE.value == "include"
    assert [kind.value for kind in TargetKind] == [
        "fqdn",
        "wildcard",
        "ipv4",
        "ipv6",
        "cidr",
        "url",
    ]
