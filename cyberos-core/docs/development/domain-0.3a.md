# Module 0.3.a — Workspace Domain Model

## Scope

This sub-module implements only the Workspace aggregate and its primitives. It deliberately contains no SQLite integration, migration, repository, CLI, or Engagement code. Persistence mapping will be added after the domain model is accepted.

## Implemented model

`Workspace` is an immutable Pydantic model with a typed UUID4 `id`, normalized name, normalized description, `active`/`archived` status, UTC-aware timestamps, optional `archived_at`, and positive optimistic `version`. `Workspace.create()` is the safe construction entry point and returns typed `DOMAIN_VALIDATION_FAILED` errors for invalid creation values.

The model enforces the following invariants: names are trimmed and contain 1–120 characters, descriptions are trimmed and capped at 4000 characters, timestamps cannot be naive, `updated_at` cannot precede `created_at`, active workspaces cannot carry `archived_at`, archived workspaces must carry it, and versions start at one. `archive()` creates a new immutable instance, sets the archive and update timestamps, and increments the version. Re-archiving is rejected with `WORKSPACE_ALREADY_ARCHIVED`.

## Test evidence

The Workspace unit suite contains 13 tests covering UUID4 generation and explicit IDs, normalization, length boundaries, naive timestamps, invalid UUID versions, timestamp ordering, archive state and version increment, re-archive rejection, immutability, and active/archived invariants. The complete project suite passes **60 tests**. Ruff, strict mypy on 39 source files, formatting, and wheel build pass as well.

## Boundary confirmation

The implementation does not import SQLite, Engagement, repositories, or CLI. It is therefore safe to review as a pure domain slice before schema and persistence mapping are introduced in later sub-modules.

## Next sub-module

The next approved step is **0.3.b — Engagement Model + Lifecycle Rules**. It should remain pure domain code initially and depend on Workspace only through `WorkspaceId` and explicit service-level policies.
