from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from types import TracebackType
from typing import Self

from cyberos.config.models import DatabaseSettings
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.persistence.health import (
    DatabaseHealthReport,
    DatabaseHealthResult,
    collect_database_health,
    run_quick_check,
)
from cyberos.persistence.path_policy import PreparedDatabasePath, prepare_database_path


@dataclass(frozen=True, slots=True)
class SQLitePragmaState:
    foreign_keys: bool
    journal_mode: str
    synchronous: str
    busy_timeout_ms: int
    secure_delete: bool


def _map_sqlite_error(error: sqlite3.Error, *, operation: str) -> CyberOSError:
    message = str(error).lower()
    if "busy" in message or "locked" in message:
        return CyberOSError(
            ErrorCode.DATABASE_BUSY,
            "The SQLite database is busy or locked.",
            retryable=True,
            details={"operation": operation},
        )
    if operation == "open":
        return CyberOSError(
            ErrorCode.DATABASE_OPEN_FAILED,
            "The SQLite database could not be opened.",
            details={"operation": operation},
        )
    return CyberOSError(
        ErrorCode.DATABASE_PRAGMA_FAILED,
        "The SQLite connection policy could not be applied.",
        details={"operation": operation},
    )


def _single_value(connection: sqlite3.Connection, pragma: str) -> object:
    row = connection.execute(f"PRAGMA {pragma}").fetchone()
    return row[0] if row else None


def _pragma_int(connection: sqlite3.Connection, pragma: str) -> int:
    return int(str(_single_value(connection, pragma) or "0"))


def _apply_pragmas(connection: sqlite3.Connection, settings: DatabaseSettings) -> SQLitePragmaState:
    if (
        settings.journal_mode != "wal"
        or settings.synchronous != "full"
        or not settings.foreign_keys
        or not settings.secure_delete
    ):
        raise CyberOSError(
            ErrorCode.DATABASE_PRAGMA_MISMATCH,
            "DatabaseSettings do not satisfy the hardened SQLite policy.",
        )
    try:
        connection.execute(
            "PRAGMA foreign_keys = ON" if settings.foreign_keys else "PRAGMA foreign_keys = OFF"
        )
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute(
            "PRAGMA secure_delete = ON" if settings.secure_delete else "PRAGMA secure_delete = OFF"
        )
        state = SQLitePragmaState(
            foreign_keys=bool(_pragma_int(connection, "foreign_keys")),
            journal_mode=str(_single_value(connection, "journal_mode") or "").lower(),
            synchronous={"0": "off", "1": "normal", "2": "full", "3": "extra"}.get(
                str(_single_value(connection, "synchronous")), "unknown"
            ),
            busy_timeout_ms=_pragma_int(connection, "busy_timeout"),
            secure_delete=bool(_pragma_int(connection, "secure_delete")),
        )
    except (sqlite3.DatabaseError, TypeError, ValueError) as exc:
        raise _map_sqlite_error(
            exc if isinstance(exc, sqlite3.Error) else sqlite3.DatabaseError(str(exc)),
            operation="pragma",
        ) from exc
    expected = SQLitePragmaState(True, "wal", "full", 5000, True)
    if state != expected:
        raise CyberOSError(
            ErrorCode.DATABASE_PRAGMA_MISMATCH,
            "SQLite did not apply the required hardening policy.",
            details={
                "actual": state.__dict__
                if hasattr(state, "__dict__")
                else {
                    "foreign_keys": state.foreign_keys,
                    "journal_mode": state.journal_mode,
                    "synchronous": state.synchronous,
                    "busy_timeout_ms": state.busy_timeout_ms,
                    "secure_delete": state.secure_delete,
                }
            },
        )
    return state


class ManagedSQLiteConnection:
    """A lifecycle-bound SQLite connection with verified hardening state."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        prepared: PreparedDatabasePath,
        pragma_state: SQLitePragmaState,
    ) -> None:
        self._connection = connection
        self.prepared = prepared
        self.pragma_state = pragma_state
        self._closed = False

    def __enter__(self) -> Self:
        self._ensure_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def raw(self) -> sqlite3.Connection:
        self._ensure_open()
        return self._connection

    def quick_check(self) -> DatabaseHealthResult:
        return run_quick_check(self.raw)

    def health(self) -> DatabaseHealthReport:
        return collect_database_health(self)

    def close(self) -> None:
        if not self._closed:
            self._connection.close()
            self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise CyberOSError(
                ErrorCode.DATABASE_CONNECTION_CLOSED, "The SQLite connection is already closed."
            )


class SQLiteConnectionFactory:
    """Creates one hardened connection per explicit lifecycle."""

    def __init__(self, settings: DatabaseSettings) -> None:
        self.settings = settings

    def open(self) -> ManagedSQLiteConnection:
        prepared = prepare_database_path(self.settings)
        try:
            connection = sqlite3.connect(
                str(prepared.path),
                timeout=self.settings.timeout_seconds,
                isolation_level=None,
                check_same_thread=True,
            )
            connection.row_factory = sqlite3.Row
            pragma_state = _apply_pragmas(connection, self.settings)
            return ManagedSQLiteConnection(connection, prepared, pragma_state)
        except CyberOSError:
            if "connection" in locals():
                connection.close()
            raise
        except sqlite3.Error as exc:
            if "connection" in locals():
                connection.close()
            raise _map_sqlite_error(exc, operation="open") from exc

    def connect(self) -> ManagedSQLiteConnection:
        """Alias for callers that prefer a connection-oriented verb."""

        return self.open()
