from __future__ import annotations

from uuid import UUID, uuid4

EntityId = UUID
CorrelationId = UUID
OperationId = UUID


def new_id() -> UUID:
    """Create a new opaque UUID4 identifier."""

    return uuid4()
