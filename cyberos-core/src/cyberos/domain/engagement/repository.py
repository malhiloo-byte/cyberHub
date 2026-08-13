from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from cyberos.domain.engagement.model import Engagement, EngagementStatus
from cyberos.domain.engagement.primitives import EngagementId
from cyberos.domain.workspace.primitives import WorkspaceId


class EngagementRepository(Protocol):
    """Persistence port for Engagement; it contains no SQL details."""

    def add(self, engagement: Engagement) -> Engagement: ...

    def get(self, engagement_id: EngagementId) -> Engagement | None: ...

    def list_by_workspace(
        self,
        workspace_id: WorkspaceId,
        *,
        status: EngagementStatus | None = None,
    ) -> Sequence[Engagement]: ...

    def update(self, engagement: Engagement, *, expected_version: int) -> Engagement: ...

    def transition(
        self,
        engagement_id: EngagementId,
        target_status: EngagementStatus,
        *,
        expected_version: int,
        at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> Engagement: ...

    def archive(self, engagement_id: EngagementId, *, expected_version: int) -> Engagement: ...
