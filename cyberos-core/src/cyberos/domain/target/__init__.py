"""Target primitives and canonicalization for CyberOS."""

from cyberos.domain.target.canonicalization import (
    CandidateParser,
    CanonicalTarget,
    TargetCanonicalizer,
)
from cyberos.domain.target.primitives import (
    TargetId,
    TargetKind,
    TargetRule,
    new_target_id,
    validate_target_id,
)

__all__ = [
    "CandidateParser",
    "CanonicalTarget",
    "TargetCanonicalizer",
    "TargetId",
    "TargetKind",
    "TargetRule",
    "new_target_id",
    "validate_target_id",
]
