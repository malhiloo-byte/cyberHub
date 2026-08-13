# GitHub Setup Audit Notes

## Baseline

The repository is a monorepo rooted at `/home/ubuntu/cyberos-foundation`, containing the React foundation workspace and the Python package under `cyberos-core/`. The current managed Git remote is an internal artifact remote, not a GitHub repository. No push to GitHub is performed by this task.

The existing package README is located at `cyberos-core/README.md` and documents the Python nucleus, local setup, domain lifecycle, Scope/Target CLI, and package quality gate. A repository-facing README will be added at the monorepo root so GitHub visitors see the system vision before entering the Python package.

The root `.gitignore` already excludes Node dependencies, environment files, logs, coverage, temporary data, SQLite files, and Manus-only metadata. The package `.gitignore` excludes Python bytecode, pytest/mypy/Ruff caches, build outputs, egg-info, coverage, and htmlcov. The root policy will be extended with explicit Python virtualenv, wheel, secret, and local CyberOS runtime patterns without ignoring source documentation or migration SQL.
