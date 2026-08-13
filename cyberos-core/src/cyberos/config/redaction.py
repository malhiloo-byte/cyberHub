from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SENSITIVE_TOKENS = ("secret", "token", "password", "api_key", "private_key", "credential")


def is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(token in normalized for token in SENSITIVE_TOKENS)


def redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: "[REDACTED]" if is_sensitive_key(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    return value
