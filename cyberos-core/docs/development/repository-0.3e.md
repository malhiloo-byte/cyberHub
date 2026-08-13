# Module 0.3.e — Engagement Repository and Persistence Mapping

## Scope

This slice adds the Engagement persistence port, SQLite mapper, and `SQLiteEngagementRepository` on top of the approved Module 0.2 UnitOfWork and the Workspace repository patterns. It does not add CLI, Application Services, HTTP API, Target, Scope, Finding, Evidence, Scan, Job, Report, Recon, or AI features.

## Mapper contract

`engagement_to_params()` maps UUID4 identifiers to canonical text, enum values to their stable string values, UTC-aware timestamps to ISO-8601 strings, optional authorization/start/end/archive fields to nullable parameters, and version to an integer. `engagement_from_row()` validates the full domain model and translates invalid stored rows to `PERSISTENCE_MAPPING_FAILED`. No `sqlite3.Row` leaves the adapter.

## Repository behavior

`SQLiteEngagementRepository` implements `add`, `get`, `list_by_workspace`, `update`, `transition`, and `archive`. All writes use parameterized SQL and require an active UnitOfWork; callers own commit and rollback. Listing is deterministic by `created_at DESC, id ASC` and supports status filtering.

Before add and before activation, the repository checks that the parent Workspace exists and is active. Missing parents produce `WORKSPACE_NOT_FOUND`; archived parents produce `WORKSPACE_ARCHIVED`. The composite unique index is translated to `ENGAGEMENT_NAME_CONFLICT`, while raw SQLite messages remain internal.

## Concurrency and lifecycle persistence

Update, transition, and archive use `WHERE id = ? AND version = ?`. Affected-row zero is distinguished between `ENGAGEMENT_NOT_FOUND` and `CONCURRENCY_CONFLICT`. Domain transitions are evaluated by `Engagement.transition()` before SQL, then the persisted status, timestamps, archive state, and version are written atomically. Moving an Engagement to another Workspace is rejected with `ENGAGEMENT_WORKSPACE_IMMUTABLE`.

## Test evidence

The new suite adds 11 integration tests covering exact round-trip mapping, active and missing Workspace guards, archived Workspace rejection, list/status filtering, scoped case-insensitive uniqueness, same name in different Workspaces, transition timestamp/version persistence, authorization guard preservation, stale-version conflict, archive persistence, UnitOfWork rollback, and no internal row leakage. The full project suite passes **112 tests**. Ruff, strict mypy on 49 source files, formatting, and wheel build pass.

## Security review

All values are parameterized. SQL errors are translated into stable domain-facing codes and messages. The repository does not execute network or subprocess operations, and it does not expand the approved scope into CLI, HTTP, Recon, or AI features. Workspace activity is enforced before insertion and activation, but authorization semantics remain a future Scope/Authorization domain responsibility.

## Next slice

The next approved step is **0.3.f — Application Services + CLI Integration**, which should orchestrate repositories and UnitOfWork without placing SQL or lifecycle rules inside CLI commands.
