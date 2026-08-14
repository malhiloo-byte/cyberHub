<div align="center">

# CYBEROS

### Personal Cybersecurity Engineering OS

**A private command layer for scope, execution, evidence, and deliberate security growth.**

<p>
  <a href="https://github.com/malhiloo-byte/cyberHub/actions/workflows/ci.yml"><img src="https://github.com/malhiloo-byte/cyberHub/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI status" /></a>
  <a href="cyberos-core/pyproject.toml"><img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11+" /></a>
  <a href="cyberos-core/tests/"><img src="https://img.shields.io/badge/tests-360%20passing-238636?logo=pytest&logoColor=white" alt="360 tests passing" /></a>
  <a href="https://docs.astral.sh/ruff/"><img src="https://img.shields.io/badge/style-Ruff-D7FF64?logo=ruff&logoColor=111111" alt="Ruff" /></a>
  <a href="https://mypy.readthedocs.io/"><img src="https://img.shields.io/badge/types-mypy%20strict-1674B1" alt="mypy strict" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-2ea44f.svg" alt="MIT license" /></a>
</p>

<p>
  <a href="https://3000-iykopgya8sos5tf9mekyr-d41d7d27.us4.manus.computer">Open Command Center</a>
  ·
  <a href="cyberos-core/README.md">Read the core package guide</a>
  ·
  <a href="SECURITY.md">Security policy</a>
</p>

</div>

> **Current release posture** — Module 0 remains closed after a clean zero-state end-to-end audit: **278 Module 0 tests**. Phase 1 (Offline Foundation), including Modules 1.0 through 1.7, is now closed with **360 full-suite tests**. The Recon foundation now includes deny-by-default plugin execution, persistent asset correlation, target-bound orchestration, an evidence/provenance ledger, bounded read APIs, reporting projections, canonical in-memory exports, renderer-neutral presentation adapters, and deterministic negative/schema-drift Web API fixtures. No real network reconnaissance integration has started.

---

## The product surface

CyberOS is not another collection of disconnected security scripts. It is a **personal engineering layer** above proven tools, engines, and knowledge: a local-first system for learning, lab execution, authorized testing, evidence organization, result analysis, reporting, repeatable automation, AI red teaming, and measurable professional growth.

The platform follows one deliberate rule: **build the missing personal operating layer instead of rebuilding every tool that already exists.**

| Principle | What it means in CyberOS |
|---|---|
| **Local-first** | Personal workspaces and SQLite persistence begin on the operator’s machine. |
| **Privacy-first** | Sensitive operational data is not sent to a remote service by default. |
| **Fail-closed** | Unknown, expired, excluded, or unapproved targets are denied. |
| **API-minded** | Domain contracts and structured JSON outputs keep future interfaces composable. |
| **Evidence-oriented** | Tasks, results, timestamps, versions, and authorization context remain auditable. |

## What is already real

| Capability | Delivery status |
|---|---|
| Core contracts, configuration, typed errors, and structured logging | **Complete** |
| SQLite persistence, migrations, integrity checks, and UnitOfWork | **Complete through Migration 0006** |
| Workspace and Engagement lifecycle | **Complete and tested** |
| Scope, Target, canonicalization, and include/exclude policy | **Complete and tested** |
| Target-bound, time-aware execution authorization | **Complete and tested** |
| Safe argv-only subprocess execution with bounded output | **Complete and tested** |
| Task persistence, optimistic concurrency, and CLI | **Complete and tested** |
| Zero-state full-system integration audit | **Passed — 278 Module 0 tests** |
| Recon Plugin Architecture & Contracts (Module 1.0) | **Complete — 293 full-suite tests** |
| Recon Assets & Persistence (Module 1.1) | **Complete — 307-test milestone** |
| Recon Execution Orchestration (Module 1.2) | **Complete — 319 full-suite tests** |
| Recon Evidence & Provenance Ledger (Module 1.3) | **Complete — 328 full-suite tests** |
| Evidence Query & Offline Web-Pentest Workflow (Module 1.4) | **Complete — 335 full-suite tests** |
| Recon Reporting & Multi-Web API Offline Fixtures (Module 1.5) | **Complete — 341 full-suite tests** |
| Recon Reporting Export & Negative Offline Fixtures (Module 1.6) | **Complete — 350 full-suite tests** |
| Recon Export Presentation & Schema Drift Fixtures (Module 1.7) | **Complete — 360 full-suite tests; Phase 1 closed** |
| Live Subprocess & Execution Adapter Boundary (Module 2.0) | **Complete contract slice — 370 full-suite tests; neutral local doubles only** |
| Network & Port Scanning Adapter Boundary (Module 2.1) | **Complete offline slices 2.1.a–e — 380 full-suite tests; live tool integration not started** |
| Nmap Live Tool Specification (Module 2.1.f.a–d) | **Complete offline contract slices — 390 full-suite tests; TCP Connect profile and safe DOCTYPE compatibility verified** |
| Localhost Nmap Application Service & CLI (Module 2.1.g) | **Offline/injected integration complete — 393 full-suite tests; live trial pending explicit authorization** |
| P3 Hardening & Parser Compatibility | **Complete offline remediation — 397 full-suite tests; standard XML fixture and Task failure finalization verified** |
| Real reconnaissance tooling | **Not started — design first** |

## Operating model

```text
                              CYBEROS COMMAND CENTER
┌──────────────────────────────────────────────────────────────────────────────┐
│  CLI / Web Surface  →  Application Services  →  Domain Contracts             │
└───────────────┬──────────────────────────────┬─────────────────────────────┘
                │                              │
                ▼                              ▼
       Task Orchestration              Scope Validation & Authorization
                │                              │
                └──────────────┬───────────────┘
                               ▼
                    Safe Execution Boundary
             argv-only · isolated env · bounded output
                               │
                               ▼
                   Repositories + Persistence Mappers
                               │
                               ▼
                    UnitOfWork → SQLite local store

       Future engines and plugins connect through authorized Task contracts only.
```

The boundary is intentional: **Domain → Persistence Mappers → Repositories → Application Services → CLI**. The domain does not know SQLite, SQL, or Click/Typer. The CLI does not own business logic. Execution never bypasses `ExecutionAuthorization`.

## Security posture

> **Authorization is a prerequisite, not a post-processing label.**

Every executable Task must carry an explicit authorization whose `scope_id`, `target_id`, decision, and expiry are bound to the requested operation. Exclude rules take precedence over include rules. An unauthorized, expired, malformed, or unknown target is denied without inference.

The execution boundary accepts an **argv tuple**, never a shell command string. The child process receives an isolated allowlisted environment, output is capped, and timeouts escalate from termination to kill. SQL details and raw tracebacks are not exposed through the CLI contract.

CyberOS is intended for **owned systems, approved labs, and explicitly authorized engagements**. It is not designed to bypass authorization or facilitate harmful activity. See the complete [responsible disclosure and acceptable-use policy](SECURITY.md).

## Learning path

The roadmap is aligned to a long-term security engineering path rather than a list of unrelated features.

| Stage | Focus | Status |
|---:|---|---|
| 0 | Core domain, scope safety, task execution, persistence, and audit | **Closed** |
| 1 | Recon Plugin Foundation, Orchestrator, Evidence Ledger, Reporting, Presentation, and Offline Web API Fixtures | **Closed — 1.7; Phase 1 complete** |
| 2 | Live adapter boundary, safe subprocess mediation, and approved tool integrations | **2.0 contract slice complete; tool-specific adapters not started** |
| 2 | Web Pentest Workflow and Evidence Capture | Planned |
| 3 | Network and Active Directory Security | Planned |
| 4 | Cloud Security Operations | Planned |
| 5 | API Security Engineering | Planned |
| 6 | Python, Data, and ML Security Analytics | Planned |
| 7 | Deep Learning Security | Planned |
| 8 | LLM Security | Planned |
| 9 | AI Red Teaming | Planned |
| 10 | AI Security Engineering | Planned |
| 11 | Research Workbench | Planned |
| 12 | Knowledge, Evidence, and Findings Graph | Planned |
| 13 | Reporting, Metrics, and Progress Measurement | Planned |
| 14 | Platform Hardening, Extensibility, and Operations | Planned |

## Quickstart

The core package targets **Python 3.11+**. The recommended workflow is an isolated virtual environment with runtime data outside the repository.

```bash
git clone https://github.com/malhiloo-byte/cyberHub.git cyberos
cd cyberos/cyberos-core

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[dev]'

# Run the complete local quality gate.
./scripts/check.sh
```

For a local configuration, keep paths explicit and use a private runtime directory:

```toml
[database]
path = "/absolute/path/to/cyberos.sqlite3"

[runtime]
data_dir = "/absolute/path/to/cyberos-runtime"
log_dir = "/absolute/path/to/cyberos-runtime/logs"
```

## CLI walkthrough

CyberOS requires target kinds to be explicit. There is no automatic target inference, and every output can be rendered as human-readable text or structured JSON.

```bash
# Establish the hierarchy.
cyberos workspace create "Web Security Lab" --json
cyberos engagement create <workspace-id> "Authorized API Lab" --kind learning --json
cyberos scope create <engagement-id> "Approved API Scope" --json

# Add explicit include and exclude rules.
cyberos target add <scope-id> --rule include --kind fqdn --value api.example.com --json
cyberos target add <scope-id> --rule exclude --kind fqdn --value admin.example.com --json
cyberos scope authorize <scope-id> \
  --authorization-reference approval-123 \
  --json

# Evaluate before execution.
cyberos scope evaluate <scope-id> \
  --kind fqdn \
  --value api.example.com \
  --json

# The argv delimiter is mandatory before the command being executed.
cyberos task run <scope-id> <target-id> \
  --kind fqdn \
  --value api.example.com \
  --json -- \
  echo "authorized local task"

cyberos task list --scope-id <scope-id> --json
cyberos task show <task-id> --json
```

## Repository map

```text
cyberHub/
├── cyberos-core/                 Python package and domain kernel
│   ├── src/cyberos/domain/       Immutable domain models and policies
│   ├── src/cyberos/application/  Orchestration and boundary services
│   ├── src/cyberos/persistence/  SQLite mappers, repositories, UnitOfWork
│   ├── src/cyberos/execution/    Safe subprocess execution boundary
│   ├── src/cyberos/cli/          Structured Typer/Click interface
│   ├── migrations/               Forward-only schema migrations 0001–0006
│   ├── tests/                    Unit, integration, CLI, and E2E tests
│   └── docs/                     Architecture, reviews, and module records
├── client/                       React Command Center presentation layer
├── docs/                         Project-level reports and design records
├── .github/workflows/ci.yml      Automated quality gates
├── SECURITY.md                   Responsible disclosure and use policy
└── LICENSE                       MIT license
```

## Quality gates

Every meaningful change is expected to pass the same gates locally and in GitHub Actions:

```bash
cd cyberos-core
source .venv/bin/activate

pytest -q
ruff check .
ruff format --check .
mypy --strict src
python -m build
```

The canonical command is `./scripts/check.sh`. Continuous integration runs on every `push` and `pull_request` through [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

## Project documentation

| Document | Purpose |
|---|---|
| [`cyberos-core/README.md`](cyberos-core/README.md) | Core package installation, contracts, and development workflow |
| [`cyberos-core/docs/development/module-0-final-audit.md`](cyberos-core/docs/development/module-0-final-audit.md) | Final Module 0 zero-state audit and limitations |
| [`cyberos-core/docs/architecture/module-1-0-recon-plugin-contracts-design.md`](cyberos-core/docs/architecture/module-1-0-recon-plugin-contracts-design.md) | Approved and implemented Module 1.0 plugin contracts and boundary decisions |
| [`cyberos-core/docs/architecture/module-1-2-recon-orchestration-design.md`](cyberos-core/docs/architecture/module-1-2-recon-orchestration-design.md) | Implemented Module 1.2 pipeline orchestration, chaining, budgets, cancellation, and result adapter |
| [`cyberos-core/docs/architecture/module-1-7-recon-export-presentation-and-schema-drift-fixtures-design.md`](cyberos-core/docs/architecture/module-1-7-recon-export-presentation-and-schema-drift-fixtures-design.md) | Module 1.7 presentation adapters, bounded views, and offline schema/version drift fixtures |
| [`cyberos-core/docs/architecture/module-2-1-network-port-scan-adapter-design.md`](cyberos-core/docs/architecture/module-2-1-network-port-scan-adapter-design.md) | Module 2.1 manifest, target/flag policy, offline XML/JSON parser, and provenance boundary |
| [`cyberos-core/docs/architecture/module-2-1-f-live-tool-specification-and-authorized-lab-protocol.md`](cyberos-core/docs/architecture/module-2-1-f-live-tool-specification-and-authorized-lab-protocol.md) | Nmap binary identity, localhost lab protocol, P3 approval gate, and live-trial test strategy |
| [`cyberos-core/src/cyberos/application/nmap_localhost.py`](cyberos-core/src/cyberos/application/nmap_localhost.py) | Official localhost Nmap application service and bounded provenance orchestration |
| [`docs/reports/cyberos-complete-project-report-ar.md`](docs/reports/cyberos-complete-project-report-ar.md) | Project chronology and engineering record |
| [`ideas.md`](ideas.md) | Command Center visual direction and design decisions |
| [`SECURITY.md`](SECURITY.md) | Security reporting and responsible-use boundaries |

## Status and next decision

The foundation, plugin boundary, asset persistence layer, orchestration boundary, reporting/export boundary, presentation compatibility boundary, Module 2.0 live process boundary, Module 2.1 offline port-scan adapter contracts, Nmap preflight/parser boundary, and localhost application/CLI boundary are intentionally stable. Phase 1 remains officially closed at Module 1.7. One explicitly authorized localhost P3 trial was performed and exposed an XML compatibility/failure-finalization defect; the defect is remediated and regression-tested offline at **397 passing tests**. No retry, home-network scan, or other live invocation has been performed. A distinct future authorization is required before any new localhost trial.

<div align="center">

### Built deliberately. Authorized explicitly. Audited continuously.

<sub>CyberOS is a personal cybersecurity engineering workspace for disciplined, authorized practice.</sub>

</div>

---

This project is licensed under the [MIT License](LICENSE). Security work remains subject to authorization, applicable law, and the policies of the systems being tested.
