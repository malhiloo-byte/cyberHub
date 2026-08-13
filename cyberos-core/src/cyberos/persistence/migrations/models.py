from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    path: Path
    checksum: str
    sql: str


@dataclass(frozen=True, slots=True)
class AppliedMigration:
    version: int
    name: str
    checksum: str
    applied_at: str
    execution_ms: int


@dataclass(frozen=True, slots=True)
class MigrationRunResult:
    applied: tuple[Migration, ...]
    current_version: int
