from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from typing import Any

from cyberos.core.errors import CyberOSError, ErrorCode


@dataclass(frozen=True, slots=True)
class DatabaseHealthResult:
    healthy: bool
    check: str
    details: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DatabaseHealthReport:
    healthy: bool
    schema_version: int
    schema_initialized: bool
    pragma_state: dict[str, Any]
    quick_check: DatabaseHealthResult
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


def collect_database_health(connection: Any) -> DatabaseHealthReport:
    """Collect schema, pragma, and integrity state without attempting repair."""

    quick_check = connection.quick_check()
    pragma_state = asdict(connection.pragma_state)
    try:
        rows = connection.raw.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table" not in str(exc).lower():
            raise CyberOSError(
                ErrorCode.MIGRATION_HISTORY_INVALID,
                "The migration metadata could not be inspected.",
            ) from exc
        rows = []
    versions = [int(row[0]) for row in rows]
    schema_version = max(versions, default=0)
    expected = list(range(1, schema_version + 1))
    history_contiguous = versions == expected
    schema_initialized = bool(versions) and history_contiguous
    healthy = quick_check.healthy and schema_initialized and history_contiguous
    return DatabaseHealthReport(
        healthy=healthy,
        schema_version=schema_version,
        schema_initialized=schema_initialized,
        pragma_state=pragma_state,
        quick_check=quick_check,
        details={
            "history_contiguous": history_contiguous,
            "migration_count": len(versions),
        },
    )
