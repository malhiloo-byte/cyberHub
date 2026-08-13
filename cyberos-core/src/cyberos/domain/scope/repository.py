"""Persistence port for Scope; no SQL or adapter details belong here."""

from collections.abc import Sequence
from typing import Protocol

from cyberos.domain.engagement.primitives import EngagementId
from cyberos.domain.scope.model import Scope
from cyberos.domain.scope.primitives import ScopeId


class ScopeRepository(Protocol):
    def add(self, scope: Scope) -> Scope: ...

    def get(self, scope_id: ScopeId) -> Scope | None: ...

    def list_by_engagement(self, engagement_id: EngagementId) -> Sequence[Scope]: ...

    def exists(self, scope_id: ScopeId) -> bool: ...

    def update(self, scope: Scope, *, expected_version: int) -> Scope: ...

    def archive(self, scope_id: ScopeId, *, expected_version: int) -> Scope: ...
