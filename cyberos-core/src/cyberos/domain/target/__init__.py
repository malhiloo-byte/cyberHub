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
from cyberos.domain.target.repository import TargetRepository

__all__ = [
    "CandidateParser",
    "CanonicalTarget",
    "TargetCanonicalizer",
    "Target",
    "TargetRepository",
    "TargetId",
    "TargetKind",
    "TargetRule",
    "TargetStatus",
    "new_target_id",
    "validate_target_id",
]
