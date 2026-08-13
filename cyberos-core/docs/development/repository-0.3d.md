# Module 0.3.d — Workspace Repository and Persistence Mapping

## Scope

This slice adds the Workspace persistence port, a SQLite mapper, and `SQLiteWorkspaceRepository` on top of the approved Module 0.2 Connection Factory and UnitOfWork. It does not implement EngagementRepository, CLI, Target, Scope, Finding, Evidence, Scan, Job, Report, Recon, or AI features.

## Mapper contract

`workspace_to_params()` converts a validated Workspace into parameter values: canonical UUID text, normalized strings, enum values, UTC ISO-8601 timestamps, nullable archive timestamp, and integer version. `workspace_from_row()` accepts an internal SQLite row and returns a validated immutable Workspace. SQLite row objects never cross the repository boundary; invalid stored data becomes `PERSISTENCE_MAPPING_FAILED`.

The round-trip tests verify UUID identity, UTC timestamp equality, status, archive state, description, and version without exposing `sqlite3.Row`.

## Repository contract

`WorkspaceRepository` provides `add`, `get`, `list`, `update`, `archive`, and `exists`. `SQLiteWorkspaceRepository` owns SQL statements but not transaction lifecycle. Every write requires an active `SQLiteUnitOfWork`; the caller explicitly commits or allows the UnitOfWork context to roll back on exception.

List ordering is deterministic: `created_at DESC, id ASC`. Optional status filtering uses a parameterized value. Duplicate Workspace names translate to `WORKSPACE_NAME_CONFLICT` without exposing SQLite table names or raw constraint messages.

## Optimistic concurrency

Update and archive use `WHERE id = ? AND version = ?`. If no row is affected, the repository distinguishes a missing Workspace from a stale version and returns `WORKSPACE_NOT_FOUND` or `CONCURRENCY_CONFLICT`. Successful updates increment the database version atomically. Archive writes one UTC timestamp to both `archived_at` and `updated_at`, changes status to archived, and increments version.

## Test evidence

The new repository integration tests cover exact mapping round-trip, add/get/list/exists/update/archive, deterministic ordering, status filtering, duplicate-name translation, stale version conflict without modification, archive persistence, exception rollback, and no internal SQLite row leakage. The full project suite passes **101 tests**. Ruff, strict mypy on 46 source files, formatting, and wheel build pass.

## Security review

All values are parameterized. SQL and SQLite rows remain inside the persistence adapter. Domain models remain independent of SQLite and CLI. Duplicate-name messages are translated to stable typed errors. No new network, subprocess, or future-domain capabilities were introduced.

## Next slice

The next approved slice is **0.3.e — Engagement Repository + Persistence Mapping**. It should reuse the same mapper, UnitOfWork, error translation, and concurrency patterns without modifying WorkspaceRepository behavior.
