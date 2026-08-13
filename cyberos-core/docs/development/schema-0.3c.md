# Module 0.3.c — Workspace and Engagement Schema Implementation

## Scope delivered

This slice implements only `0002_workspace_engagement.sql` on top of the unchanged `0001_persistence_kernel.sql`. It adds the `workspaces` and `engagements` tables, required indexes, the Workspace-to-Engagement foreign key, approved constraints, composite case-insensitive Engagement name uniqueness within a Workspace, and no future domain tables.

The migration contains no `IF NOT EXISTS`, no internal `BEGIN`/`COMMIT`, no seed data, and no repository, CLI, Target, Scope, Finding, Evidence, Scan, Job, Report, Recon, or AI code. It is executed by the existing Module 0.2 Migration Runner and Connection Factory.

## Schema inventory

| Object | Type | Purpose |
|---|---|---|
| `workspaces` | table | Workspace aggregate persistence |
| `engagements` | table | Engagement entity persistence |
| `uq_workspaces_name_nocase` | unique index | Workspace name uniqueness, case-insensitive |
| `uq_engagements_workspace_name_nocase` | unique index | Engagement name uniqueness within Workspace, case-insensitive |
| `idx_engagements_workspace_id` | index | Workspace child lookup |
| `idx_engagements_workspace_status` | index | Workspace + status filtering |
| `idx_engagements_created_at` | index | deterministic timeline access |

`schema_migrations` remains the metadata table from Module 0.2. No object for Target, Scope, Finding, Evidence, Scan, Job, or Report was added.

## Constraint enforcement

SQL enforces nullability, lengths, status and kind allowlists, archive invariants, version lower bounds, start/end ordering, authorization-reference presence for an active authorized assessment, completed-end requirement, and the Workspace foreign key. Domain models remain responsible for actual UUID4 validation, normalization, timezone-aware UTC semantics, and the full lifecycle transition state machine. The duplication is intentional defense in depth.

`ON DELETE RESTRICT` and `ON UPDATE RESTRICT` are enabled on `engagements.workspace_id`, while the Connection Factory enables `PRAGMA foreign_keys = ON` per connection. Workspace deletion is therefore prevented while child Engagements exist, and immutable UUID identities cannot be updated through the database.

## Tests

The migration integration suite adds 19 tests covering migration application and checksum metadata, idempotent rerun, schema health, `quick_check`, `foreign_key_check`, Workspace and Engagement insertion, Workspace name uniqueness, composite Engagement name uniqueness, same Engagement name across different Workspaces, status/kind/archive/authorization/start-end/completed/version constraints, foreign-key existence, delete/update restrict, atomic rollback with no partial tables, checksum mismatch, and absence of future domain tables.

The complete regression suite passes **93 tests**. Ruff, strict mypy, formatting, and wheel build pass. An additional audit confirms that 0002 has no `IF NOT EXISTS`, 0001 is unchanged, and the migration directory contains only 0001 and 0002.

## Deviation review

No architectural deviation was introduced. The approved composite unique index is implemented as `uq_engagements_workspace_name_nocase` on `(workspace_id, name COLLATE NOCASE)`. The only test adjustment was to test SQL-level case-insensitive uniqueness with case changes and keep whitespace trimming as a Domain responsibility, because a plain approved `COLLATE NOCASE` unique index does not trim input.

## Next slice

The next coherent slice should be persistence mapping and repository design for Workspace and Engagement, but it must be planned separately. Repository code and CLI were intentionally not included in 0.3.c.
