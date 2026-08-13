from __future__ import annotations

from cyberos.core.serialization import dumps


def check_serialization() -> dict[str, str | bool]:
    output = dumps({"uuid": "ok", "utc": "2026-08-13T00:00:00+00:00"})
    return {"name": "serialization", "ok": bool(output), "value": "json"}
