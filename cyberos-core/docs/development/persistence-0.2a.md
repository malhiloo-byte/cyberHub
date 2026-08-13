# Module 0.2.a — Database Settings and Path Security

## Scope

This sub-module adds database configuration and a local path policy. It does not open a SQLite connection, apply PRAGMAs, create schema, or run migrations; those responsibilities belong to 0.2.b and 0.2.c.

## Configuration

The `DatabaseSettings` model is part of the shared `CyberOSConfig` and supports TOML plus the following environment overrides:

| Environment variable | Meaning |
|---|---|
| `CYBEROS_DATABASE_PATH` | Absolute SQLite file path |
| `CYBEROS_DATABASE_TIMEOUT_SECONDS` | Timeout between 0.1 and 60 seconds |
| `CYBEROS_DATABASE_JOURNAL_MODE` | Hardened allowlist currently accepts `wal` |
| `CYBEROS_DATABASE_SYNCHRONOUS` | Hardened allowlist currently accepts `full` |
| `CYBEROS_DATABASE_FOREIGN_KEYS` | Boolean policy flag |
| `CYBEROS_DATABASE_SECURE_DELETE` | Boolean policy flag |
| `CYBEROS_DATABASE_CREATE_PARENT` | Whether a missing parent may be created |

The defaults are local-first and conservative: `~/.cyberos/cyberos.sqlite3`, five seconds, WAL, synchronous FULL, foreign keys enabled, secure delete enabled, and parent creation enabled.

## Path policy

`prepare_database_path()` validates an absolute path, rejects directory targets and symbolic links, creates a missing parent only when explicitly allowed, and validates read/write access. New database files are created atomically with mode `0600` on POSIX systems. A parent directory created by the policy uses mode `0700`. If an existing parent owned by the current user is broader than that, the policy attempts to tighten it; it does not silently modify a parent owned by another user.

Existing database files with group/world permissions are rejected rather than silently changed. This avoids altering a file that CyberOS did not create and makes the security decision observable to the caller.

## Test evidence

The sub-module adds tests for defaults, environment typing, invalid hardening values, new file creation, mode `0600`, mode `0700` parent creation, broad existing file permissions, directory targets, symlink targets, and disabled parent creation. The complete project suite currently passes 22 tests.

## Security boundary

This policy reduces accidental local exposure; it is not encryption at rest. No database connection, network access, subprocess, backup, or migration is implemented in 0.2.a.

## Next sub-module

The next approved implementation step is **0.2.b — Connection Factory + PRAGMA Hardening**, which will consume `DatabaseSettings` and `PreparedDatabasePath` without redefining path policy.
