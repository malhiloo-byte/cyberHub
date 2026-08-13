# Module 0.2.b — Connection Factory and PRAGMA Hardening

## Scope

This sub-module consumes the `DatabaseSettings` and `prepare_database_path()` from 0.2.a. It opens a local SQLite connection, applies the required hardening policy, verifies the effective PRAGMA values, and exposes a lifecycle-bound wrapper. It does not create domain schema, run migrations, or provide a UnitOfWork yet.

## Implemented contract

`SQLiteConnectionFactory.open()` and `.connect()` prepare the path, open one SQLite connection, set a row factory, apply the deterministic policy, verify the effective state, and return `ManagedSQLiteConnection`. The wrapper supports context-manager cleanup, idempotent close, explicit `quick_check()`, and a closed-state error instead of allowing ambiguous use after close.

The effective state is represented by `SQLitePragmaState` and must be exactly:

| Setting | Required value |
|---|---|
| `foreign_keys` | `True` |
| `journal_mode` | `wal` |
| `synchronous` | `full` |
| `busy_timeout` | `5000` milliseconds |
| `secure_delete` | `True` |

The connection uses `isolation_level=None` so that the future UnitOfWork can own transaction boundaries explicitly. No migration or business write is performed by 0.2.b.

## Error handling

SQLite open, busy/locked, PRAGMA failure, PRAGMA mismatch, closed connection, and integrity failure are mapped to typed Module 0.1 errors. Raw SQL error text is not returned as the user-facing message. The health check never attempts automatic repair; a non-`ok` quick check returns an unhealthy result and leaves the database unchanged.

## Test evidence

The test suite now has 30 passing tests. New tests cover exact PRAGMA state, connection open, context-manager close after exceptions, idempotent close, closed-connection behavior, healthy quick check, unhealthy quick-check result without repair, defensive rejection of an invalid hardened policy, typed path/open failure, and the no-network/no-subprocess boundary.

The full gate passes:

```text
pytest: 30 passed
ruff check: passed
ruff format --check: passed
mypy --strict: passed on 29 source files
python -m build --wheel: passed
```

## Security boundary

The factory hardens the SQLite connection but does not encrypt the database file. File permissions remain the responsibility of 0.2.a, and migrations remain the responsibility of 0.2.c. The use of static PRAGMA statements and the absence of network/subprocess imports keep this sub-module narrow and auditable.

## Next sub-module

The next approved step is **0.2.c — Migration Metadata + Runner**, which will use the factory and its verified lifecycle without redefining connection policy.
