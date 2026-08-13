# Module 0.2.c — Migration Metadata and Runner

## Scope

This sub-module adds a small, internal migration system on top of the hardened connection factory. It creates only the `schema_migrations` metadata table, applies ordered SQL files atomically, records SHA-256 checksums, and rejects unsafe history. It does not add Workspace, Target, Finding, Evidence, or any other domain table.

## Migration metadata

The metadata table is:

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    execution_ms INTEGER NOT NULL CHECK (execution_ms >= 0)
);
```

`0001_persistence_kernel.sql` contains only this table. The SQL file is included in the built wheel, so installation does not silently lose migration assets.

## Loader policy

Migration filenames must match `0001_lowercase_name.sql`. Versions must be unique, start at 1, be contiguous, and be ordered. SQL is normalized for line endings and final whitespace before both execution and SHA-256 hashing. Non-SQL files are ignored, while malformed `.sql` filenames are rejected.

## Runner behavior

The runner opens a hardened connection, starts `BEGIN IMMEDIATE`, ensures metadata exists, validates previous history, applies only pending migrations, inserts metadata using parameterized values, runs `quick_check`, and commits. Any typed migration or SQLite failure rolls the whole transaction back. A migration that has already been applied must retain both its name and checksum; otherwise the runner raises `MIGRATION_CHECKSUM_MISMATCH` and does not modify the database.

The runner is idempotent. Re-running an unchanged migration directory applies nothing and returns the existing current version. Applied history must be contiguous and refer only to migrations available locally; otherwise the runner raises `MIGRATION_HISTORY_INVALID`. There is no automatic downgrade.

## Test evidence

The suite now contains 37 passing tests. New migration tests verify metadata-only schema creation, idempotent rerun, recorded checksum, rollback of a failed second migration including removal of the first table and metadata table, checksum mismatch rejection, invalid version gaps, duplicate versions, and invalid filenames. The complete project gate also passes Ruff, strict mypy on 33 source files, and wheel build. The wheel inspection confirms that `0001_persistence_kernel.sql` is packaged.

## Security and integrity boundary

Migration SQL is trusted repository content, while data inserted into metadata uses SQL parameters. No user-provided table or column identifiers are interpolated. There is no automatic repair, no downgrade, no network access, no subprocess, and no domain schema in this sub-module.

## Next sub-module

The next approved step is **0.2.d — UnitOfWork + Repository Ports**, which will reuse the connection factory and migration metadata without redefining migration behavior.
