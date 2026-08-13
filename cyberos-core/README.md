# CyberOS Core — Module 0.1

This package is the Python nucleus for CyberOS. It provides shared contracts, safe configuration loading, structured logging, typed errors, SQLite persistence, Workspace and Engagement domain models, repositories, application services, and a local CLI. It does not execute scanners, access targets, start an HTTP API, or implement Scope, Target, Finding, Evidence, Scan, Job, Report, Recon, or AI features.

## Development setup

```bash
cd cyberos-core
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[dev]'
```

## Run

```bash
cyberos version
cyberos doctor
cyberos doctor --json
cyberos config show
cyberos config validate --file ./config/cyberos.example.toml
cyberos workspace create "Web Security Lab"
cyberos workspace list --json
```

The default configuration is local-first and writes only under `~/.cyberos` when a runtime check needs to validate the directory. No network request or external security tool is executed. Use `.env.template` only as a naming reference; do not put secrets in it.

## Workspace and Engagement CLI

Use a custom TOML file when you want an isolated database during development:

```toml
[database]
path = "/absolute/path/to/cyberos.sqlite3"

[runtime]
data_dir = "/absolute/path/to/runtime"
log_dir = "/absolute/path/to/runtime/logs"
```

The first Workspace commands are:

```bash
cyberos workspace create "Web Security Lab" --description "Personal learning workspace"
cyberos workspace list
cyberos workspace list --json
cyberos workspace show <workspace-uuid>
cyberos workspace archive <workspace-uuid> --expected-version 1
```

Engagement commands operate inside an active Workspace:

```bash
cyberos engagement create <workspace-uuid> "API Security Practice" --kind learning
cyberos engagement create <workspace-uuid> "Authorized Review" \
  --kind authorized_assessment --authorization-reference approval-123
cyberos engagement list <workspace-uuid> --json
cyberos engagement show <engagement-uuid>
cyberos engagement transition <engagement-uuid> active --expected-version 1
cyberos engagement transition <engagement-uuid> completed --expected-version 2
cyberos engagement archive <engagement-uuid> --expected-version 3
```

Every domain command supports `--json`. JSON is a stable `OperationResult` envelope:

```json
{
  "ok": true,
  "data": { "id": "...", "name": "...", "version": 1 },
  "error": null,
  "meta": { "correlation_id": "...", "duration_ms": 2 }
}
```

Human-readable output includes the important entity fields and the correlation ID. Errors use typed codes and exit codes; raw SQLite errors and tracebacks are not part of the user-facing contract.

## Domain lifecycle

Workspace starts as `active` and can be archived. Engagement transitions are deliberately explicit:

```text
draft → active → paused → active
active → completed
draft / active / paused / completed → archived
```

An `authorized_assessment` requires a non-empty authorization reference before activation. Completion records `end_at`; archiving records `archived_at` and increments the optimistic version. There is no hard-delete command.

## Layer boundaries

The intended dependency direction is:

```text
Domain Models → Persistence Mappers → Repositories → Application Services → CLI
```

Domain models do not import SQLite, SQL, repositories, or CLI. Mappers are the only layer that converts database rows to domain objects. Repositories own SQL but not transaction lifecycle. Services own use-case orchestration and explicit UnitOfWork commit/rollback. CLI performs parsing and presentation only.

## Quality gates

```bash
./scripts/check.sh
```

The package-level designs are documented in `../docs/architecture/`. Module 0.3 implementation notes are in `docs/development/domain-0.3a.md`, `domain-0.3b.md`, `schema-0.3c.md`, `repository-0.3d.md`, `repository-0.3e.md`, and `services-cli-0.3f.md`.
