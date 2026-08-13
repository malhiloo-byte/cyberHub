# CyberOS Core — Module 0.1

This package is the Python nucleus for CyberOS. It provides shared contracts, safe configuration loading, structured logging, typed errors, and a diagnostic CLI. It does not execute scanners, access targets, start an HTTP API, or persist domain entities.

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
```

The default configuration is local-first and writes only under `~/.cyberos` when a runtime check needs to validate the directory. No network request or external security tool is executed. Use `.env.template` only as a naming reference; do not put secrets in it.

## Quality gates

```bash
./scripts/check.sh
```

The package-level design is documented in `../docs/architecture/module-0.1-bootstrap-core-contracts.md`.
