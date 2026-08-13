from __future__ import annotations

from typing import Protocol, TypeVar
from uuid import UUID

RecordT = TypeVar("RecordT", covariant=False)


class Repository(Protocol[RecordT]):
    """SQL-independent CRUD port for a domain-specific repository."""

    def get(self, entity_id: UUID) -> RecordT | None: ...

    def add(self, record: RecordT) -> RecordT: ...

    def update(self, record: RecordT) -> RecordT: ...

    def delete(self, entity_id: UUID) -> bool: ...

    def exists(self, entity_id: UUID) -> bool: ...


class UnitOfWorkPort(Protocol):
    """Transaction boundary expected by future application services."""

    state: str

    def __enter__(self) -> UnitOfWorkPort: ...

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
