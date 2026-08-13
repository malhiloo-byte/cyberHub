# Module 0.5.c — Task Persistence & Migration 0004

## Design status

تم اعتماد هذه الوثيقة وتنفيذها. القرار المحايد للـResult وTaskRecord وschema 0004 هو baseline لهذه الشريحة.

## Boundary decision: ownership of ExecutionResult

يحتاج persistence إلى حفظ `Task` ونتيجة التنفيذ معًا، بينما لا ينبغي أن يعتمد Domain repository port على طبقة infrastructure execution. القرار المقترح هو نقل تعريف `ExecutionResult` إلى value-object محايد في `cyberos.domain.task.result` أو `cyberos.core`، ثم يعيد `cyberos.execution.runner` تصديره backward-compatible. بهذه الطريقة يعتمد كل من execution وpersistence على عقد محايد، ولا يعتمد Domain على SQLite أو subprocess.

سيتم تمثيل القراءة بسجل immutable محايد `TaskRecord` يحتوي `task: Task` و`result: ExecutionResult | None`. النتيجة تكون `None` للحالة `pending` أو `running`، وتكون موجودة للحالات terminal. لا يُضاف result إلى Task aggregate في هذه الشريحة لأن ذلك سيخلط lifecycle domain مع output retention policy.

## Proposed `tasks` schema

| Column | Type | Policy |
|---|---|---|
| `id` | `TEXT` | UUID4 string, primary key, not null |
| `scope_id` | `TEXT` | required FK to `scopes(id)`, RESTRICT/RESTRICT |
| `target_id` | `TEXT` | required FK to `targets(id)`, RESTRICT/RESTRICT |
| `status` | `TEXT` | one of `pending`, `running`, `completed`, `failed`, `cancelled` |
| `command_json` | `TEXT` | JSON array of non-empty argv strings |
| `timeout_seconds` | `INTEGER` | 1..3600 |
| `max_output_bytes` | `INTEGER` | 1..16 MiB |
| `env_policy_json` | `TEXT` | JSON array of allowlisted environment names |
| `authorization_expires_at` | `TEXT` | nullable UTC ISO-8601 with `+00:00` |
| `created_at`, `updated_at` | `TEXT` | required UTC ISO-8601 |
| `started_at`, `completed_at`, `failed_at`, `cancelled_at` | `TEXT` | nullable UTC ISO-8601 |
| `version` | `INTEGER` | not null, `>= 1` |
| `exit_code` | `INTEGER` | nullable execution result |
| `stdout` | `BLOB` | nullable bounded raw bytes |
| `stderr` | `BLOB` | nullable bounded raw bytes |
| `truncated` | `INTEGER` | nullable boolean, only 0/1 |
| `duration_ms` | `INTEGER` | nullable non-negative duration |
| `timeout_exceeded` | `INTEGER` | nullable boolean, only 0/1 |
| `error_message` | `TEXT` | nullable safe machine-readable reason, never raw traceback |

The command and environment policy are stored as JSON because `ExecutionSpec` is immutable and tuple-based. The mapper validates the decoded JSON before constructing `ExecutionSpec`; malformed stored JSON becomes `PERSISTENCE_MAPPING_FAILED`.

## SQL invariants

Database constraints enforce identifiers’ non-empty UUID-length shape, supported statuses, positive version, bounded command/spec scalar values, UTC timestamp lexical shape, boolean representations, non-negative duration, and parent foreign keys. Domain-level Pydantic validation remains authoritative for UUID4 version, exact tuple/string semantics, timestamp ordering, state transition history, authorization expiry relation, and the consistency between status and execution timestamps.

The status/result matrix is intentionally enforced in both layers for defense in depth:

| Status | Required timestamp | Result policy |
|---|---|---|
| `pending` | none | all result columns null |
| `running` | `started_at` | all result columns null |
| `completed` | `completed_at` | result present, `exit_code = 0`, `timeout_exceeded = 0`, `error_message` null |
| `failed` | `failed_at` | result present; timeout may be 0 or 1; safe error message optional |
| `cancelled` | `cancelled_at` | result may be null because cancellation can happen before spawn |

`ON DELETE RESTRICT` on both parents prevents deletion of a Scope or Target that has historical Tasks. `ON UPDATE RESTRICT` protects typed identity stability. No cascade or hard delete is introduced.

## Index plan

The migration creates `idx_tasks_scope_status` on `(scope_id, status)` and `idx_tasks_target_status` on `(target_id, status)`. `created_at DESC, id ASC` is the deterministic ordering for both list methods; the primary key provides the stable tie-breaker.

## Repository contract

The domain-facing port will expose `add`, `get`, `list_by_scope`, `list_by_target`, and `update_status_and_result`. Each returns `TaskRecord` or a tuple of records, never `sqlite3.Row`. The concrete `SQLiteTaskRepository` receives an active `SQLiteUnitOfWork` and never commits or rolls back. Every mutation uses parameterized SQL and re-reads the row after a successful update.

`update_status_and_result` accepts a fully validated immutable Task, an optional `ExecutionResult`, and `expected_version`. It updates all persisted Task fields and result fields under `WHERE id = ? AND version = ?`; zero rowcount is translated to `TASK_NOT_FOUND` or `CONCURRENCY_CONFLICT` after a safe existence check.

## Test plan

Tests will apply migrations through 0004, verify checksum/idempotency/forward-only behavior, exercise `quick_check` and `foreign_key_check`, validate all status/result constraints, prove FK protection for missing parents and RESTRICT deletion, verify Task/ExecutionSpec/ExecutionResult round-trip, assert exact truncated bytes, test deterministic list ordering, stale-version rejection, rollback on exception, and absence of raw SQLite objects at the boundary. No subprocess or network tool is used by this slice.

## Future extension points

Output retention, compression, artifact storage, report generation, CLI, and task scheduling remain outside this migration. A future result-artifact table can reference `tasks(id)` without changing the Task identity model. A future event/audit table can append lifecycle transitions while keeping the current row as the latest snapshot.
