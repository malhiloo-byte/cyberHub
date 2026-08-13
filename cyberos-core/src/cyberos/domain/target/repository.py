"""Persistence port for Target; no SQL or adapter details belong here."""

from collections.abc import Sequence
from typing import Protocol

from cyberos.domain.scope.primitives import ScopeId
from cyberos.domain.target.model import Target
from cyberos.domain.target.primitives import TargetId


class TargetRepository(Protocol):
    def add(self, target: Target) -> Target: ...

    def get(self, target_id: TargetId) -> Target | None: ...

    def list_by_scope(self, scope_id: ScopeId) -> Sequence[Target]: ...

    def exists(self, target_id: TargetId) -> bool: ...

    def update(self, target: Target, *, expected_version: int) -> Target: ...

    def archive(self, target_id: TargetId, *, expected_version: int) -> Target: ...
