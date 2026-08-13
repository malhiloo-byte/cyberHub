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


class DatabaseSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: Path = Path("~/.cyberos/cyberos.sqlite3").expanduser()
    timeout_seconds: float = 5.0
    journal_mode: str = "wal"
    synchronous: str = "full"
    foreign_keys: bool = True
    secure_delete: bool = True
    create_parent: bool = True

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: float) -> float:
        if not 0.1 <= value <= 60.0:
            raise ValueError("timeout_seconds must be between 0.1 and 60.0")
        return value

    @field_validator("journal_mode")
    @classmethod
    def validate_journal_mode(cls, value: str) -> str:
        normalized = value.lower()
        if normalized != "wal":
            raise ValueError("journal_mode must be wal in the hardened default policy")
        return normalized

    @field_validator("synchronous")
    @classmethod
    def validate_synchronous(cls, value: str) -> str:
        normalized = value.lower()
        if normalized != "full":
            raise ValueError("synchronous must be full in the hardened default policy")
        return normalized


class CyberOSConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    app: AppSettings = Field(default_factory=AppSettings)
    runtime: RuntimeSettings = Field(default_factory=RuntimeSettings)
    cli: CliSettings = Field(default_factory=CliSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
