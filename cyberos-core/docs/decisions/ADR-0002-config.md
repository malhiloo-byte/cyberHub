# ADR-0002: TOML Configuration with Environment Overrides

## Status

Accepted for Module 0.1.

## Decision

Use optional TOML files for human-edited configuration, environment variables with the `CYBEROS_` prefix for deployment overrides, and JSON for machine-readable command output.

## Security constraints

Real secrets are not committed, printed, or stored by Module 0.1. Sensitive-looking keys are redacted at output boundaries. Secret storage is deliberately deferred until a dedicated security design exists.
