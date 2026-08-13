from __future__ import annotations

import json
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from cyberos.core.errors import CyberOSError, ErrorCode


def to_jsonable(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    return value


def dumps(value: Any) -> str:
    try:
        return json.dumps(to_jsonable(value), ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise CyberOSError(
            ErrorCode.SERIALIZATION_FAILED,
            "The value could not be serialized safely.",
            details={"type": type(value).__name__},
        ) from exc
