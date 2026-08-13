# ADR-0001: Python as the CyberOS Core Runtime

## Status

Accepted for Module 0.1.

## Decision

Use Python 3.11+ for the local-first CyberOS core and keep the React web shell as a future presentation client.

## Rationale

The roadmap includes Python, data, ML, deep learning, LLM security, and AI red teaming. A Python core keeps future adapters and analysis workflows close to that path while preserving a clean boundary for a later CLI, API, and web UI.

## Consequences

The repository contains an isolated `cyberos-core` package. The web shell is not used as the source of truth for domain logic. A future API must call application services rather than duplicate them.
