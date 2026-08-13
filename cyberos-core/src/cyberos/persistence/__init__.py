"""Persistence kernel primitives for local SQLite storage."""

from cyberos.persistence.connection import (
    ManagedSQLiteConnection,
    SQLiteConnectionFactory,
    SQLitePragmaState,
)
from cyberos.persistence.health import DatabaseHealthReport, DatabaseHealthResult
from cyberos.persistence.ports import Repository, UnitOfWorkPort
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork, TransactionState
from cyberos.persistence.workspace_repository import SQLiteWorkspaceRepository

__all__ = [
    "DatabaseHealthResult",
    "DatabaseHealthReport",
    "ManagedSQLiteConnection",
    "Repository",
    "SQLiteConnectionFactory",
    "SQLitePragmaState",
    "SQLiteUnitOfWork",
    "SQLiteWorkspaceRepository",
    "TransactionState",
    "UnitOfWorkPort",
]
