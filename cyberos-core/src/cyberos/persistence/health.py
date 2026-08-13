from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from cyberos.core.errors import CyberOSError, ErrorCode


@dataclass(frozen=True, slots=True)
class DatabaseHealthResult:
    healthy: bool
    check: str
    details: dict[str, Any]


def run_quick_check(connection: sqlite3.Connection) -> DatabaseHealthResult:
    """Run SQLite quick_check without attempting automatic repair."""

    try:
        row = connection.execute("PRAGMA quick_check").fetchone()
    except sqlite3.DatabaseError as exc:
        raise CyberOSError(
            ErrorCode.DATABASE_INTEGRITY_FAILED, "SQLite integrity check could not run."
        ) from exc
    result = str(row[0]).lower() if row else ""
    healthy = result == "ok"
    return DatabaseHealthResult(
        healthy=healthy, check="quick_check", details={"result": result or "no-result"}
    )
