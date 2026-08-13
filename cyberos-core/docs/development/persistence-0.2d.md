# Module 0.2.d — UnitOfWork and Repository Ports

## Scope

This sub-module adds an explicit transaction boundary over the hardened SQLite connection and defines SQL-independent repository ports. It deliberately uses a test-only record repository to verify the contracts; it does not add domain tables or domain repositories.

## UnitOfWork contract

`SQLiteUnitOfWork` owns one connection and one transaction. Entering the context opens the hardened connection and issues `BEGIN`. Application code must call `commit()` explicitly. If the context exits while active, it rolls back automatically. The connection is then closed. Valid states are `NEW`, `ACTIVE`, `COMMITTED`, and `ROLLED_BACK`.

Commit, rollback, and raw adapter access outside an active transaction raise typed errors. Commit and rollback are not silently repeated after the transaction has reached a terminal state. A commit failure attempts a rollback and reports `TRANSACTION_COMMIT_FAILED`; a rollback failure reports `TRANSACTION_ROLLBACK_FAILED`.

## Repository ports

The generic `Repository[RecordT]` protocol defines `get`, `add`, `update`, `delete`, and `exists` using UUID identifiers and typed records. It contains no SQL, table names, SQLite rows, or pagination assumptions. Domain modules will create their own mapping and repository implementations in 0.3 or later.

The test repository is intentionally isolated under `tests/` and exists only to prove that the production transaction boundary works. It is not a CyberOS domain model and is not included in the production package.

## Isolation behavior

The tests use two separate UnitOfWork instances over the same SQLite file. A reader that has already started its transaction does not observe an uncommitted writer change, and its snapshot remains stable until its own transaction ends. After the writer commits, a fresh verifier sees the record. This confirms that the UnitOfWork does not auto-commit repository operations.

## Test evidence

The full suite now contains 42 passing tests. New tests cover commit persistence, exception-triggered rollback, two-reader isolation, invalid lifecycle operations, explicit rollback and close, and the test-only repository behavior. Ruff, strict mypy on 35 source files, formatting verification, and wheel build also pass.

## Security and scope boundary

Repositories must use parameterized values. The `raw` connection property is an adapter-level escape hatch for persistence implementations and test fixtures; application services must use repository ports rather than SQL. No Domain Tables were added. The next step is to design the broader repository contract tests and then start Module 0.3 domain modeling only after the persistence kernel is accepted.

## Next sub-module

The next recommended step inside the kernel is **0.2.e — Contract Tests + Persistence Health Integration**, or, if the user prefers to close the kernel now, a design review of Module 0.3 — Workspace & Engagement before adding domain schema.
