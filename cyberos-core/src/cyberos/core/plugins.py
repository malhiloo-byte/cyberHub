from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class PluginManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plugin_id: str = Field(pattern=r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
    name: str = Field(min_length=1, max_length=120)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+(?:[-+].*)?$")
    api_version: str = Field(pattern=r"^\d+\.\d+$")
    capabilities: tuple[str, ...] = ()
    requires_network: bool = False
    requires_subprocess: bool = False


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    valid: bool
    errors: tuple[str, ...] = ()


class HealthResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    healthy: bool
    message: str = ""


class PluginProtocol(Protocol):
    def manifest(self) -> PluginManifest: ...
    def validate_config(self, config: dict[str, Any]) -> ValidationResult: ...
    def healthcheck(self) -> HealthResult: ...
