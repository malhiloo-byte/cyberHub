from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from cyberos.core.ids import CorrelationId, OperationId, new_id


class OperationContext(BaseModel):
    """Trace context passed through every application operation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    correlation_id: CorrelationId = Field(default_factory=new_id)
    operation_id: OperationId = Field(default_factory=new_id)
    actor: str = "local-user"
    environment: str = "development"
