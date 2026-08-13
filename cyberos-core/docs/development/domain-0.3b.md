# Module 0.3.b — Engagement Model and Lifecycle Rules

## Scope

This slice implements only the Engagement domain model and its lifecycle rules. It remains independent from SQLite, SQL, ORM, repositories, CLI, network, subprocesses, and migration 0002. Workspace from 0.3.a is referenced only through the typed `WorkspaceId` primitive.

## Implemented model

`Engagement` is an immutable model with UUID4 `id`, typed UUID4 `workspace_id`, normalized name and description, `EngagementKind`, `EngagementStatus`, optional authorization reference, optional UTC start/end timestamps, lifecycle timestamps, archive timestamp, and optimistic version.

The supported kinds are `learning`, `authorized_assessment`, and `research`. The supported statuses are `draft`, `active`, `paused`, `completed`, and `archived`.

## Lifecycle policy

```text
draft → active
draft → archived
active → paused
active → completed
active → archived
paused → active
paused → completed
paused → archived
completed → archived
```

Completed and archived states cannot return to active. Archived is terminal. Invalid transitions produce typed `ENGAGEMENT_INVALID_TRANSITION`; attempting to transition an archived Engagement produces `ENGAGEMENT_ALREADY_ARCHIVED`.

An `authorized_assessment` cannot transition to active without a non-empty `authorization_reference`. This reference is only an organizational pointer and is not treated as proof of authorization or as a secret store. Completing an Engagement requires an `end_at` timestamp, and `end_at` cannot precede `start_at`.

## Testing and security evidence

The slice adds 14 pure unit tests covering UUID4 and typed workspace reference, normalization and length boundaries, authorization reference rules, UTC and timestamp invariants, allowed transitions, forbidden transitions, completion requirements, terminal archive behavior, version increments, and immutability. The full regression suite now passes **74 tests**. Ruff, strict mypy on 42 source files, formatting, and wheel build pass.

A boundary scan confirmed that `src/cyberos/domain/engagement` has no persistence, CLI, network, socket, subprocess, or HTTP imports. No SQLite schema, migration, Repository implementation, or CLI command was added.

## Architectural compatibility

The model keeps future Scope enforcement outside Engagement itself. A later execution path must remain conceptually `Engagement → Scope → Scope Validation → Authorized Target → Job/Action`. This slice intentionally does not implement Target, Scope, Recon, Findings, Evidence, or AI features.

## Next sub-module

The next step is **0.3.c — Migration 0002 + Schema Constraints**, but only after the final relationship and constraint review confirms that the Workspace and Engagement models are stable enough for persistence mapping. The migration must reflect the domain model, not define it.
