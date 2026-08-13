"""Target primitives and canonicalization for CyberOS."""

from cyberos.domain.target.canonicalization import (
    CandidateParser,
    CanonicalTarget,
    TargetCanonicalizer,
)
from cyberos.domain.target.model import Target
from cyberos.domain.target.primitives import (
    TargetId,
    TargetKind,
    TargetRule,
    TargetStatus,
    new_target_id,
    validate_target_id,
)

__all__ = [
    "CandidateParser",
    "CanonicalTarget",
    "TargetCanonicalizer",
    "Target",
    "TargetId",
    "TargetKind",
    "TargetRule",
    "TargetStatus",
    "new_target_id",
    "validate_target_id",
]
