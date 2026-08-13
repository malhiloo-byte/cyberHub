from __future__ import annotations

import hashlib
import re
from pathlib import Path

from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.persistence.migrations.models import Migration

MIGRATION_PATTERN = re.compile(r"^(?P<version>\d{4})_(?P<name>[a-z0-9]+(?:_[a-z0-9]+)*)\.sql$")


def normalize_sql(sql: str) -> str:
    """Normalize line endings and trailing whitespace before hashing/execution."""

    return sql.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"


def checksum_sql(sql: str) -> str:
    return hashlib.sha256(normalize_sql(sql).encode("utf-8")).hexdigest()


def _invalid_order(message: str, details: dict[str, object]) -> CyberOSError:
    return CyberOSError(ErrorCode.MIGRATION_ORDER_INVALID, message, details=details)


def load_migrations(directory: Path) -> tuple[Migration, ...]:
    """Load, validate, sort, and checksum SQL migration files."""

    if not directory.exists() or not directory.is_dir():
        raise _invalid_order("The migrations directory does not exist.", {"path": str(directory)})
    migrations: list[Migration] = []
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        if path.suffix != ".sql":
            continue
        match = MIGRATION_PATTERN.fullmatch(path.name)
        if match is None:
            raise _invalid_order("A migration filename is invalid.", {"filename": path.name})
        version = int(match.group("version"))
        sql = normalize_sql(path.read_text(encoding="utf-8"))
        migrations.append(
            Migration(
                version=version,
                name=match.group("name"),
                path=path,
                checksum=checksum_sql(sql),
                sql=sql,
            )
        )

    if not migrations:
        raise _invalid_order("No SQL migrations were found.", {"path": str(directory)})
    versions = [migration.version for migration in migrations]
    if len(set(versions)) != len(versions):
        raise _invalid_order("Migration versions must be unique.", {"versions": versions})
    if (
        versions != sorted(versions)
        or versions != list(range(versions[0], versions[-1] + 1))
        or versions[0] != 1
    ):
        raise _invalid_order(
            "Migration versions must be ordered, contiguous, and start at 0001.",
            {"versions": versions},
        )
    return tuple(migrations)
