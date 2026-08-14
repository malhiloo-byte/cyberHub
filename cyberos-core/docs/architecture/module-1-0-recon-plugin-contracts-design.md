# Module 1.0 — Recon Plugin Architecture & Contracts

**Status:** Implemented — Module 1.0 scope closed; no real Recon integration  
**Scope:** Plugin foundation and an offline deterministic fixture only  
**Baseline:** Module 0 is closed at checkpoint `80001bf3` and must not be reopened

> This slice defines the contract boundary for future reconnaissance engines. It does not perform DNS, HTTP probing, network discovery, subprocess execution, cloud access, external API calls, AI inference, or real socket activity.

## 1. Purpose and non-goals

The purpose of 1.0 is to establish a stable, testable plugin boundary above the existing `Task` and `ExecutionAuthorization` contracts. A plugin may describe a capability and produce a structured result, but it may not decide whether an operation is authorized, select an arbitrary target, or change execution limits.

The slice will contain immutable contract models, manifest validation, contract/version compatibility checks, capability-policy validation, a registry boundary, and one offline fixture plugin. It will not contain a recon engine, network adapter, subprocess adapter, persistence migration, CLI command, external API connector, or AI integration.

## 2. Architectural placement

```text
ScopeValidationService
        │ creates explicit ExecutionAuthorization
        ▼
Task.create(scope_id, target_id, authorization, execution_spec)
        │ creates the existing target-bound Task
        ▼
Recon Plugin Host / Registry
        │ validates manifest, compatibility, capabilities, and request binding
        ▼
ReconPlugin.execute(PluginInvocation)
        │ returns deterministic structured value
        ▼
ReconResult
```

The host remains the security authority. The plugin is a provider of computation only. The plugin boundary does not introduce a second authorization object, a second task model, or a second timeout/output policy.

## 3. Proposed contract vocabulary

| Contract | Responsibility | Security property |
|---|---|---|
| `PluginManifest` | Describes identity, versions, capabilities, target kinds, and declared requirements | Rejects unknown fields and invalid declarations before registration |
| `PluginVersion` | Semantic version of one plugin implementation | Identifies implementation compatibility independently from host API compatibility |
| `ContractVersion` | Major/minor version of the CyberOS plugin contract | Prevents incompatible plugins from loading |
| `PluginCapability` | Named permission/requirement such as offline deterministic computation | Capability must be declared and approved by host policy |
| `ReconInput` | Explicit target-bound input and bounded plugin parameters | No implicit target selection or arbitrary target string |
| `PluginInvocation` | Host-created execution envelope containing the existing `Task` and authorization | Enforces scope, target, include rule, expiry, and Task binding |
| `ReconResult` | Deterministic success/failure result with observations and typed errors | Stable JSON shape, bounded collections, no raw process/network data |
| `ReconPlugin` | Protocol implemented by a plugin | Plugin cannot create authorization or alter host controls |

## 4. Plugin identity and manifest

Each plugin has a stable `plugin_id` using a lowercase slug such as `fixture.offline`. The identifier is the identity of the logical plugin and must never be silently reused for a different purpose. A display name and description may change without changing identity.

The proposed manifest is an immutable, extra-forbidden object:

```text
PluginManifest
├── plugin_id: PluginId
├── display_name: bounded text
├── description: bounded text
├── plugin_version: SemVer
├── contract_version: ContractVersion
├── capabilities: sorted unique tuple[PluginCapability, ...]
├── supported_target_kinds: sorted unique tuple[TargetKind, ...]
├── requirements: PluginRequirements
└── declared_limits: PluginDeclaredLimits
```

`PluginRequirements` declares whether the plugin would require capabilities such as network, subprocess, filesystem, external API, or AI access. In this slice the offline fixture may declare only `offline.deterministic`. Any capability not declared is unavailable, and any declared capability still requires an explicit host policy decision.

`PluginDeclaredLimits` is a ceiling owned by the plugin contract, not a grant. The effective limits always come from the existing `Task.execution_spec` and host policy. A plugin can request less than the Task limit; it can never increase the Task timeout or output budget.

## 5. Versioning and compatibility

Plugin implementation versions use SemVer: `MAJOR.MINOR.PATCH`. Contract versions use `MAJOR.MINOR`.

| Change | Compatibility rule |
|---|---|
| Plugin patch increment | Bug fix or internal change with no contract meaning change |
| Plugin minor increment | Backward-compatible plugin behavior or additive metadata |
| Plugin major increment | Breaking plugin behavior; identity or compatibility review required |
| Contract patch-equivalent change | Documentation or validation clarification only |
| Contract minor increment | Additive optional fields and capabilities; old hosts may reject newer minor versions |
| Contract major increment | Incompatible model, lifecycle, or security semantics; rejected by older hosts |

For 1.0, the host accepts only contract major `1` and a plugin minor version less than or equal to the host-supported minor version. A plugin with a different major version or a newer unsupported minor version is rejected before registration. Unknown manifest fields are rejected rather than ignored.

## 6. Capability model

Capabilities are explicit, enumerable, and policy-checkable. The initial vocabulary is deliberately small:

| Capability | Meaning in 1.0 | Fixture status |
|---|---|---|
| `offline.deterministic` | Pure computation over supplied input; no side effects | Allowed |
| `network.dns` | DNS activity | Declared for future use only; not executable in 1.0 |
| `network.http` | HTTP activity | Declared for future use only; not executable in 1.0 |
| `process.exec` | Child-process execution | Declared for future use only; not executable in 1.0 |
| `filesystem.read` | Reading local files | Declared for future use only; not executable in 1.0 |
| `external.api` | Calls to remote services | Declared for future use only; not executable in 1.0 |
| `ai.inference` | LLM/AI inference | Declared for future use only; not executable in 1.0 |

Capability validation has two gates. The manifest must be internally coherent, and the host policy must allow every declared capability for the current execution mode. A plugin that declares a future capability is not automatically executable.

## 7. Input contract

The plugin receives `ReconInput`, not a free-form target string:

```text
ReconInput
├── target_id: TargetId
├── scope_id: ScopeId
├── candidate: TargetCandidate
└── parameters: sorted tuple[(key, value), ...]
```

`candidate` reuses the existing explicit `TargetCandidate` contract. Parameters are bounded, deterministic, and extra-policy-controlled. They are not a replacement for authorization and may not contain a second target selector.

`PluginInvocation` is host-created and contains:

```text
PluginInvocation
├── plugin_id: PluginId
├── task: Task
├── authorization: ExecutionAuthorization
├── input: ReconInput
├── effective_limits: ExecutionLimits
└── contract_version: ContractVersion
```

Construction must fail closed unless all of the following hold:

1. `task.scope_id == authorization.scope_id == input.scope_id`.
2. `task.target_id == authorization.matched_target_id == input.target_id`.
3. `authorization.matching_rule == include`.
4. The authorization is not expired at invocation time.
5. The Task is valid under its existing lifecycle and execution specification.
6. The candidate kind and value are supported by the manifest and match the authorization candidate.
7. Every requested capability is allowed by the host policy.

The plugin cannot construct a valid invocation by itself because the host owns the binding checks and supplies the immutable envelope.

## 8. Output contract: `ReconResult`

`ReconResult` is an immutable, deterministic value object. It does not generate timestamps, random identifiers, environment details, or network-derived fields by itself.

```text
ReconResult
├── task_id: TaskId
├── scope_id: ScopeId
├── target_id: TargetId
├── plugin_id: PluginId
├── plugin_version: SemVer
├── contract_version: ContractVersion
├── status: success | failure
├── observations: tuple[ReconObservation, ...]
└── errors: tuple[ReconError, ...]
```

`ReconObservation` contains a bounded `observation_type`, a bounded scalar value, and deterministic metadata represented as sorted key/value pairs. `ReconError` contains a typed error code, safe public message, and optional bounded field name. Raw tracebacks, SQL details, command lines, credentials, and network payloads do not belong in the public result contract.

Result invariants are:

| Invariant | Enforcement |
|---|---|
| Success has no fatal plugin error | Domain/contract validation and tests |
| Failure contains at least one typed error | Domain/contract validation and tests |
| `task_id`, `scope_id`, and `target_id` match the invocation | Host boundary and contract validation |
| Observation and error ordering is deterministic | Canonical sorting before model creation |
| Collection sizes and field lengths are bounded | Contract validation and effective limits |
| JSON serialization is stable | Existing serialization conventions plus contract tests |

## 9. Execution requirements and limits

The existing `ExecutionSpec` remains the source of execution controls. The plugin contract does not create a parallel timeout or output model.

The host computes `effective_limits` as the strictest intersection of:

```text
Task ExecutionSpec
∩ host policy
∩ plugin declared ceiling
```

The following controls are mandatory:

| Control | Owner | Rule |
|---|---|---|
| Timeout | Existing Task / host | Plugin cannot extend it |
| Output bytes | Existing Task / host | Plugin result is rejected or truncated according to the contract; no unbounded collection |
| Observation count | Host / contract | Bounded before result acceptance |
| Input size | Host / contract | Bounded before invocation |
| Environment | Existing Task execution boundary | Plugin does not receive arbitrary inherited environment |
| Network/subprocess | Capability policy | Disabled for 1.0 fixture and rejected by fixture host mode |

For the offline fixture, the allowed execution profile is pure in-process computation with no network, subprocess, filesystem, external API, or AI capability.

## 10. Failure semantics and error model

Failures are typed and safe. They do not leak raw exceptions across the plugin boundary.

| Error family | Example code | Meaning |
|---|---|---|
| Manifest | `PLUGIN_MANIFEST_INVALID` | Manifest schema, duplicate capability, or identity validation failed |
| Compatibility | `PLUGIN_CONTRACT_UNSUPPORTED` | Contract major/minor is not supported by the host |
| Capability | `PLUGIN_CAPABILITY_DENIED` | Declared capability is not allowed in the current host policy |
| Input | `PLUGIN_INPUT_INVALID` | Input is malformed, ambiguous, or exceeds limits |
| Authorization | `PLUGIN_AUTHORIZATION_INVALID` | Task, target, scope, rule, or expiry binding failed |
| Lifecycle | `PLUGIN_NOT_READY` | Plugin was invoked before successful registration/validation |
| Execution | `PLUGIN_EXECUTION_FAILED` | Plugin returned a controlled failure |
| Result | `PLUGIN_RESULT_INVALID` | Output violated the deterministic result contract |
| Limit | `PLUGIN_LIMIT_EXCEEDED` | Plugin exceeded effective time, output, or collection limits |

The host converts unexpected plugin exceptions into a safe `PLUGIN_EXECUTION_FAILED` result and records the correlation context through existing logging. The raw exception is not part of the user-facing result.

## 11. Plugin lifecycle

```text
discovered → manifest_validated → compatibility_checked
          → capability_checked → registered → ready
          → invoked → completed | failed
          → retired
```

Registration is atomic: a plugin is not visible as `ready` until all validation gates pass. A failed registration leaves no usable registry entry. Retirement prevents new invocations but does not mutate historical results.

## 12. Compatibility and registry rules

The registry is keyed by `plugin_id` and rejects duplicate identities. It stores the validated manifest and the plugin protocol implementation, not database connections, authorization factories, or arbitrary host services.

The registry must reject:

- invalid plugin identifiers or SemVer values;
- duplicate capabilities or target kinds;
- unsupported contract versions;
- manifests whose requirements contradict their capability list;
- capabilities denied by the active host policy;
- duplicate plugin identities;
- plugin implementations that do not satisfy the protocol;
- fixture invocations with mismatched Task and authorization bindings.

## 13. Security boundary

The boundary is enforced in layers rather than by plugin cooperation:

1. `ScopeValidationService` creates the only accepted `ExecutionAuthorization`.
2. `Task.create` binds scope, target, include rule, expiry, and `ExecutionSpec`.
3. The plugin host validates the immutable `PluginInvocation` against the existing Task and authorization.
4. Manifest and capability policy validation runs before plugin invocation.
5. The plugin receives no repository, UnitOfWork, database connection, shell, socket, HTTP client, or authorization factory.
6. The result validator rejects identity mismatches, malformed output, unknown fields, and limit violations.

This makes bypass attempts fail closed. A plugin cannot widen scope, select another target, renew expiry, transition a Task, raise limits, or create an authorization.

## 14. Offline fixture plugin

The fixture plugin is intentionally boring and deterministic. It accepts one supported canonical candidate and produces a fixed observation derived only from the supplied input. It has no imports or calls for networking, subprocesses, filesystem access, randomness, wall-clock time, or external services.

The fixture test matrix will prove:

| Test family | Proof |
|---|---|
| Success | Valid manifest and invocation produce a structured `ReconResult` |
| Controlled failure | Fixture can return a typed failure for a declared invalid input case |
| Capability validation | A denied or undeclared capability blocks registration/invocation |
| Version compatibility | Supported contract loads; unsupported major/newer minor is rejected |
| Manifest rejection | Invalid identifier, version, duplicate capability, or unknown field is rejected |
| Authorization binding | Cross-scope, cross-target, excluded, or expired invocation is rejected |
| Determinism | Same explicit input produces byte-equivalent serialized output |
| Boundary security | No socket, DNS, HTTP, subprocess, filesystem, random, or external API activity occurs |

## 15. Implementation sequence after approval

1. Add contract models and typed error codes without changing existing Module 0 behavior.
2. Add manifest, capability, and contract compatibility validators.
3. Add immutable `PluginInvocation`, `ReconResult`, observation, and error models.
4. Add a minimal registry and host validation boundary.
5. Add the offline fixture plugin.
6. Add pure contract tests, fixture tests, compatibility tests, and security/boundary tests.
7. Run the complete regression suite, Ruff, formatting, mypy strict, wheel build, and static boundary checks.
8. Stop before any real recon integration and document unresolved decisions.

## 16. Unresolved architectural decisions requiring explicit review

| Decision | Recommended position for review |
|---|---|
| In-process versus out-of-process real plugins | Keep 1.0 contracts transport-neutral; require an out-of-process sandbox before untrusted third-party plugins are supported |
| Plugin trust and signing | Defer signing, but never imply that registry membership is a trust guarantee |
| ReconResult persistence | Keep results in-memory in 1.0; design a migration only in a later approved slice |
| Host capability policy source | Use a static deny-by-default policy in 1.0; make policy injection explicit later |
| Plugin configuration | Allow only bounded, schema-validated values in a future slice; no arbitrary config dictionary in 1.0 |
| Task state integration | Reuse existing Task lifecycle; do not add plugin-specific task states |
| Retry semantics | Defer retries until idempotency and evidence semantics are designed |

## Approval gate

Implementation must not begin until the following are explicitly approved:

- the manifest and versioning rules;
- the capability vocabulary and deny-by-default policy;
- the `PluginInvocation` binding to existing `Task` and `ExecutionAuthorization`;
- the deterministic `ReconResult` shape;
- the lifecycle and failure semantics;
- the unresolved decisions or their proposed deferrals.

## Implementation record

The approved design is implemented without reopening or refactoring Module 0. The implementation adds the `cyberos.recon` package with immutable manifest, version, capability, input, invocation, result, observation, and error contracts; a deny-by-default `PluginHost`; and the pure `OfflineFixturePlugin`. The host creates the only valid invocation and validates the existing `Task` against the existing `ExecutionAuthorization` before calling a plugin.

Result limits are enforced by rejection. The host never silently truncates plugin output, and a plugin cannot increase the Task timeout or output budget. No persistence, migration, CLI, network, subprocess, filesystem, external API, AI, sandbox, signing, or IPC implementation was added.

The full regression suite contains **293 tests**, including the new Module 1.0 contract and security tests. Pytest, Ruff lint, Ruff format check, mypy strict, wheel build, and explicit security/boundary tests all passed. The remaining decisions listed above are intentionally deferred to later approved slices, especially trust/signing, sandboxing, persistence, retries, and real plugin transport.
