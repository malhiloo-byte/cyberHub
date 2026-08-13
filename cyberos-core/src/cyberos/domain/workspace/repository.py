from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from cyberos.domain.workspace.model import Workspace, WorkspaceStatus
from cyberos.domain.workspace.primitives import WorkspaceId


class WorkspaceRepository(Protocol):
    """Persistence port for Workspace; it contains no SQL details."""

    def add(self, workspace: Workspace) -> Workspace: ...

    def get(self, workspace_id: WorkspaceId) -> Workspace | None: ...

    def list(self, *, status: WorkspaceStatus | None = None) -> Sequence[Workspace]: ...

    def update(self, workspace: Workspace, *, expected_version: int) -> Workspace: ...

    def archive(self, workspace_id: WorkspaceId, *, expected_version: int) -> Workspace: ...

    def exists(self, workspace_id: WorkspaceId) -> bool: ...
