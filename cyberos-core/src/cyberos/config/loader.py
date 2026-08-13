from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from cyberos.config.models import CyberOSConfig
from cyberos.core.errors import CyberOSError, ErrorCode


def _parse_env_value(raw: str) -> Any:
    lowered = raw.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    return raw


def _apply_env_overrides(data: dict[str, Any], environ: dict[str, str]) -> dict[str, Any]:
    result = {section: dict(values) for section, values in data.items() if isinstance(values, dict)}
    mapping = {
        "CYBEROS_ENVIRONMENT": ("app", "environment"),
        "CYBEROS_DATA_DIR": ("runtime", "data_dir"),
        "CYBEROS_LOG_DIR": ("runtime", "log_dir"),
        "CYBEROS_LOG_LEVEL": ("runtime", "log_level"),
        "CYBEROS_LOG_FORMAT": ("runtime", "log_format"),
        "CYBEROS_OUTPUT_FORMAT": ("cli", "output_format"),
        "CYBEROS_COLOR": ("cli", "color"),
        "CYBEROS_DATABASE_PATH": ("database", "path"),
        "CYBEROS_DATABASE_TIMEOUT_SECONDS": ("database", "timeout_seconds"),
        "CYBEROS_DATABASE_JOURNAL_MODE": ("database", "journal_mode"),
        "CYBEROS_DATABASE_SYNCHRONOUS": ("database", "synchronous"),
        "CYBEROS_DATABASE_FOREIGN_KEYS": ("database", "foreign_keys"),
        "CYBEROS_DATABASE_SECURE_DELETE": ("database", "secure_delete"),
        "CYBEROS_DATABASE_CREATE_PARENT": ("database", "create_parent"),
    }
    for env_key, (section, key) in mapping.items():
        if env_key in environ:
            result.setdefault(section, {})[key] = _parse_env_value(environ[env_key])
    return result


def load_config(path: Path | None = None, environ: dict[str, str] | None = None) -> CyberOSConfig:
    raw: dict[str, Any] = {}
    if path is not None:
        try:
            with path.open("rb") as handle:
                raw = tomllib.load(handle)
        except FileNotFoundError as exc:
            raise CyberOSError(
                ErrorCode.CONFIG_NOT_FOUND,
                "The configuration file was not found.",
                details={"path": str(path)},
            ) from exc
        except OSError as exc:
            raise CyberOSError(
                ErrorCode.CONFIG_INVALID,
                "The configuration file could not be read.",
                details={"path": str(path)},
            ) from exc
        except tomllib.TOMLDecodeError as exc:
            raise CyberOSError(
                ErrorCode.CONFIG_INVALID,
                "The configuration file is not valid TOML.",
                details={"path": str(path)},
            ) from exc
    merged = _apply_env_overrides(raw, dict(os.environ) if environ is None else environ)
    try:
        return CyberOSConfig.model_validate(merged)
    except ValidationError as exc:
        fields = [".".join(str(part) for part in error["loc"]) for error in exc.errors()]
        raise CyberOSError(
            ErrorCode.CONFIG_INVALID, "Configuration validation failed.", details={"fields": fields}
        ) from exc
