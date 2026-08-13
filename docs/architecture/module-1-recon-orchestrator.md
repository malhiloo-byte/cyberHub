# Module 1 — Recon Orchestrator Architecture & Contracts

## Status

Design preparation only. No reconnaissance engine, network connector, DNS lookup, HTTP probing, or scanner integration is implemented by this document.

## Purpose

Module 1 will provide a controlled orchestration layer for authorized reconnaissance workflows. It will not replace mature engines. Instead, it will translate an approved Task and Scope into a reproducible plugin invocation, capture structured outputs, and preserve provenance for later evidence and reporting modules.

## Non-goals

The first slice must not implement exploitation, credential attacks, unrestricted network discovery, autonomous target expansion, or AI-driven action selection. It must not permit a plugin to widen the authorized Scope or bypass `ExecutionAuthorization`.

## Proposed boundaries

```text
Recon CLI / future Web UI
        ↓
ReconApplicationService
        ↓
ReconPlan + ExecutionAuthorization guard
        ↓
ReconPluginRegistry → ReconPluginAdapter
        ↓
TaskExecutionEngine / SafeSubprocessRunner
        ↓
Structured ReconResult + provenance
        ↓
TaskRepository / future Evidence repository
```

The plugin contract should be deterministic and narrow. A plugin receives a typed target candidate, an immutable authorization context, an execution specification, and a correlation ID. It returns structured JSON plus bounded stdout/stderr metadata. It cannot mutate Scope, create new targets, or access secrets outside its explicit environment policy.

## Initial domain vocabulary

| Concept | Responsibility |
|---|---|
| `ReconPlan` | Immutable set of authorized plugin steps and execution limits |
| `ReconPluginId` | Stable typed identifier for a registered adapter |
| `ReconPluginManifest` | Declares capabilities, required input kinds, output schema, and risk class |
| `ReconResult` | Structured bounded output with plugin/version/provenance and Task linkage |
| `ReconCapability` | Explicit capability such as DNS metadata or HTTP headers, never an implicit network grant |
| `ReconProvenance` | Correlation ID, authorization reference, target ID, plugin version, start/end timestamps |

## Safety contract

Every plan must be bound to one Scope ID and one Target ID. The application service revalidates the current Scope before execution, rejects expired or archived scopes, denies excluded targets, and refuses plugins whose declared capability is not explicitly enabled by the plan. The adapter layer uses argv-only execution and inherits the 0.5.b output, timeout, and environment policies.

## First implementation slices

The recommended order is: plugin contracts and manifests; pure capability validation; an offline fixture plugin that consumes local structured input; application orchestration with Task integration; then one explicitly authorized network adapter only after a separate security review and user approval.

## Open decisions before implementation

The project must decide whether plugin manifests are Python-only or JSON-addressable, whether plugin versions use SemVer or immutable commit IDs, how result schemas are versioned, and whether network capability approvals are per plan, per engagement, or per environment. These decisions should be reviewed before Module 1.a code begins.
