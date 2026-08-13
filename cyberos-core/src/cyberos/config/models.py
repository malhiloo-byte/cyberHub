from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = "cyberos"
    environment: str = "development"


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    data_dir: Path = Path("~/.cyberos").expanduser()
    log_dir: Path = Path("~/.cyberos/logs").expanduser()
    log_level: str = "INFO"
    log_format: str = "text"

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("log_level must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")
        return normalized

    @field_validator("log_format")
    @classmethod
    def validate_log_format(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"text", "json"}:
            raise ValueError("log_format must be text or json")
        return normalized


class CliSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    output_format: str = "text"
    color: bool = True

    @field_validator("output_format")
    @classmethod
    def validate_output_format(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"text", "json"}:
            raise ValueError("output_format must be text or json")
        return normalized


class CyberOSConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    app: AppSettings = Field(default_factory=AppSettings)
    runtime: RuntimeSettings = Field(default_factory=RuntimeSettings)
    cli: CliSettings = Field(default_factory=CliSettings)
