"""Scope domain primitives for CyberOS."""

from cyberos.domain.scope.matcher import MatchDecision, MatchResult, ScopeMatcher
from cyberos.domain.scope.model import Scope
from cyberos.domain.scope.primitives import (
    ScopeId,
    ScopeStatus,
    new_scope_id,
    validate_scope_id,
)
from cyberos.domain.scope.repository import ScopeRepository

__all__ = [
    "Scope",
    "ScopeMatcher",
    "MatchDecision",
    "MatchResult",
    "ScopeId",
    "ScopeRepository",
    "ScopeStatus",
    "new_scope_id",
    "validate_scope_id",
]
