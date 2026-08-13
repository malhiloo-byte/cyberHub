from __future__ import annotations

import sqlite3
from enum import StrEnum
from types import TracebackType
from typing import Self

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.persistence.connection import ManagedSQLiteConnection, SQLiteConnectionFactory


class TransactionState(StrEnum):
    NEW = "new"
    ACTIVE = "active"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"


class SQLiteUnitOfWork:
    """Owns one explicit SQLite transaction and its connection lifecycle."""

    def __init__(self, factory: SQLiteConnectionFactory) -> None:
        self.factory = factory
        self._managed: ManagedSQLiteConnection | None = None
        self.state = TransactionState.NEW
        self._closed = False

    def __enter__(self) -> Self:
        if self.state is not TransactionState.NEW or self._closed:
            raise CyberOSError(
                ErrorCode.TRANSACTION_NOT_ACTIVE, "A UnitOfWork can only be entered once."
            )
        self._managed = self.factory.connect()
        try:
            self._managed.raw.execute("BEGIN")
            self.state = TransactionState.ACTIVE
            return self
        except sqlite3.DatabaseError as exc:
            self._managed.close()
            self._closed = True
            raise CyberOSError(
                ErrorCode.TRANSACTION_NOT_ACTIVE, "The UnitOfWork transaction could not start."
            ) from exc

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if self.state is TransactionState.ACTIVE:
                self.rollback()
        finally:
            self.close()

    @property
    def raw(self) -> sqlite3.Connection:
        """Expose the adapter connection only to persistence implementations."""

        self._ensure_active()
        if self._managed is None:
            raise CyberOSError(
                ErrorCode.TRANSACTION_NOT_ACTIVE, "The UnitOfWork has no active connection."
            )
        return self._managed.raw

    @property
    def is_closed(self) -> bool:
        return self._closed

    def commit(self) -> None:
        self._ensure_active()
        try:
            self.raw.commit()
        except sqlite3.DatabaseError as exc:
            try:
                self.raw.rollback()
            except sqlite3.DatabaseError:
                pass
            self.state = TransactionState.ROLLED_BACK
            raise CyberOSError(
                ErrorCode.TRANSACTION_COMMIT_FAILED, "The transaction could not be committed."
            ) from exc
        self.state = TransactionState.COMMITTED

    def rollback(self) -> None:
        self._ensure_active()
        try:
            self.raw.rollback()
        except sqlite3.DatabaseError as exc:
            raise CyberOSError(
                ErrorCode.TRANSACTION_ROLLBACK_FAILED, "The transaction could not be rolled back."
            ) from exc
        self.state = TransactionState.ROLLED_BACK

    def close(self) -> None:
        if not self._closed:
            if self.state is TransactionState.ACTIVE:
                self.rollback()
            if self._managed is not None:
                self._managed.close()
            self._closed = True

    def _ensure_active(self) -> None:
        if self._closed or self.state is not TransactionState.ACTIVE:
            code = (
                ErrorCode.TRANSACTION_ALREADY_COMMITTED
                if self.state is TransactionState.COMMITTED
                else ErrorCode.TRANSACTION_ALREADY_ROLLED_BACK
                if self.state is TransactionState.ROLLED_BACK
                else ErrorCode.TRANSACTION_NOT_ACTIVE
            )
            raise CyberOSError(code, "The UnitOfWork does not have an active transaction.")
