# Testing and Quality Gates

Module 0.1 is intentionally testable without network access, real targets, security tools, or user secrets. Unit tests cover the framework-independent contracts and configuration rules. CLI tests exercise the public command boundary through Typer's isolated runner. Doctor tests use temporary directories, so the test suite does not depend on a particular workstation layout.

Run the complete gate from the package directory:

```bash
source .venv/bin/activate
bash scripts/check.sh
```

The gate runs pytest, Ruff linting, Ruff formatting verification, mypy in strict mode, and a wheel build. A successful run is evidence that the package is syntactically valid, typed, formatted, tested, and packageable. It does not claim that future scanners or adapters are tested; those belong to later modules.
