"""Persistence kernel primitives for local SQLite storage."""

from cyberos.persistence.connection import (
    ManagedSQLiteConnection,
    SQLiteConnectionFactory,
    SQLitePragmaState,
)
from cyberos.persistence.health import DatabaseHealthResult
from cyberos.persistence.ports import Repository, UnitOfWorkPort
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork, TransactionState

__all__ = [
    "DatabaseHealthResult",
    "ManagedSQLiteConnection",
    "Repository",
    "SQLiteConnectionFactory",
    "SQLitePragmaState",
    "SQLiteUnitOfWork",
    "TransactionState",
    "UnitOfWorkPort",
]
