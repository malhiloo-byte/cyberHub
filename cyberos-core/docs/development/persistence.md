# CyberOS Persistence Kernel — Module 0.2

This page is the implementation index for Module 0.2. Read the sub-module notes in order: `persistence-0.2a.md`, `persistence-0.2b.md`, `persistence-0.2c.md`, `persistence-0.2d.md`, and `persistence-0.2e.md`.

The kernel is local-first and SQLite-based without an ORM. It does not yet define Workspace, Engagement, Target, Finding, or Evidence tables. Those entities require a separate domain design and belong to Module 0.3 or later.

The validation command is:

```bash
cd cyberos-core
source .venv/bin/activate
bash scripts/check.sh
```

The current closed-kernel gate is 47 passing tests, Ruff, strict mypy, and wheel build. The next step is a design-only review of Workspace & Engagement rather than adding schema opportunistically.
