# Module 0.3.f — Application Services and CLI Integration

## Scope

This slice adds application orchestration and a local CLI for Workspace and Engagement. It does not add an HTTP API, Web UI, hard delete, Target, Scope, Finding, Evidence, Scan, Job, Report, Recon, or AI capability.

## Application Services

`WorkspaceService` orchestrates create, list, show, and archive operations. `EngagementService` orchestrates create, list, show, transition, and archive. Services create a UnitOfWork, call repositories, explicitly commit successful writes, and rely on UnitOfWork rollback for exceptions. CLI commands do not contain SQL or lifecycle decisions.

The shared `execute_service()` boundary returns the Module 0.1 `OperationResult` envelope with `ok`, `data` or `error`, and `meta.correlation_id`/`duration_ms`. Typed `CyberOSError` values are preserved; unexpected exceptions become a safe `INTERNAL_ERROR` without stack traces or internal details.

Engagement completion automatically supplies a UTC `end_at` when the caller does not provide one. Authorized assessments are checked in the service before activation and still protected by the Domain Model and repository path.

## CLI commands

```text
cyberos workspace create <name> [--description TEXT] [--json]
cyberos workspace list [--status STATUS] [--json]
cyberos workspace show <workspace-id> [--json]
cyberos workspace archive <workspace-id> [--expected-version N] [--json]

cyberos engagement create <workspace-id> <name> --kind KIND [--authorization-reference TEXT] [--start-at ISO]
cyberos engagement list <workspace-id> [--status STATUS] [--json]
cyberos engagement show <engagement-id> [--json]
cyberos engagement transition <engagement-id> <status> [--expected-version N] [--at ISO] [--end-at ISO] [--json]
cyberos engagement archive <engagement-id> [--expected-version N] [--json]
```

All domain commands support `--json`. JSON output is the stable OperationResult envelope. Human output is concise and includes the correlation ID. Hard delete is intentionally absent.

## Test evidence

The new tests cover WorkspaceService create/list/show/archive, EngagementService authorization guard and automatic completion end timestamp, all Workspace and Engagement CLI happy paths in JSON and human text, deterministic list output, invalid IDs, version conflict, and no raw SQL/traceback leakage. The full project suite passes **120 tests**. Ruff, strict mypy on 53 source files, formatting, and wheel build pass. A real CLI smoke workflow also succeeded for workspace create/list, engagement create, and transition.

## Security review

Services are the only orchestration layer between CLI and repositories. CLI parsing errors are converted into typed envelopes and exit codes. Raw SQLite errors and stack traces are not emitted. IDs must be UUID4, timestamps supplied to CLI must include timezone offsets, and all writes retain UnitOfWork transaction boundaries.

## Next slice

The next step is **0.3.g — Documentation + Final Module Checkpoint**, which should consolidate the module documentation, run a final cross-layer audit, and close Workspace & Engagement before introducing Scope or execution-oriented features.
