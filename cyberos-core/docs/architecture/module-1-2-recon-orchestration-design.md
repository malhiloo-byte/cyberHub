# Module 1.2 — Recon Execution Orchestration & Pipeline Engine

**Status:** Implemented and closed — Module 1.2  
**Baseline:** Module 0 closed; Module 1.0 closed; Module 1.1 implemented at checkpoint `3ba4bf40`  
**Migration:** None added; Module 1.2 uses the existing 0001–0005 schema  
**Security posture:** Fail-closed, target-bound, authorization-bound, Task-limit-bound  

> هذه الوثيقة تسجل التصميم المعتمد والتنفيذ المنجز لطبقة تنظيم تنفيذ Recon فوق `PluginHost` و`ReconIngestionService`. لا ينفذ Module 1.2 Plugin حقيقيًا أو Network Adapter أو CLI أو Migration جديدة أو retry worker.

## 1. Executive decision

يقترح Module 1.2 إضافة **Pipeline Orchestrator** ينسق خطوات Plugins المصرح بها، ويحوّل كل نتيجة Plugin إلى `ReconIngestionService` فور نجاحها، مع إبقاء CyberOS صاحب السلطة الأمنية والتنفيذية الوحيد.

المحرك لا يكتشف أهدافًا جديدة من تلقاء نفسه، ولا يمنح Plugin صلاحية ضمنية، ولا ينشئ نموذج تفويض بديلًا. كل خطوة تُشغّل فوق `Task` موجود و`ExecutionAuthorization` موجودة، وتستخدم `PluginHost` المعتمد من Module 1.0، ثم تحفظ النتائج عبر وحدة معاملات مستقلة لكل مخرج Plugin.

### التوصية المتعلقة بحالة `INGESTING`

العقد الحالي لـ`TaskStatus` في Module 0 هو:

```text
PENDING → RUNNING → COMPLETED / FAILED / CANCELLED
```

ولا يحتوي على حالة `INGESTING`. لذلك لا يجوز إضافة `INGESTING` إلى `TaskStatus` داخل هذه الشريحة لأن ذلك سيعيد فتح Module 0. التوصية الآمنة هي اعتماد `PipelinePhase.INGESTING` كحالة **داخلية ephemeral** في orchestrator، بينما يبقى Task في حالة `RUNNING` حتى اكتمال ingestion أو فشلها.

هذا القرار يحافظ على baseline الحالي ويعطي audit layer دقيقًا دون تغيير Domain state machine. إضافة حالة Task دائمة أو جدول pipeline phases تُترك لقرار معماري مستقل إذا أثبتت الحاجة إليها.

## 2. Scope and non-goals

### داخل النطاق التصميمي والتنفيذي

يشمل هذا التصميم تعريف pipeline model، step contract، input derivation، orchestrator boundary، Task lifecycle semantics، authorization re-checks، budget propagation، per-step transaction boundaries، partial failures، cancellation، recovery، observability contract، وtest/security strategy.

### خارج النطاق

لا يشمل Module 1.2 إضافة Plugin جديد، ولا Nmap أو DNS أو HTTP أو Subfinder أو httpx أو Burp أو Nuclei أو cloud scanners، ولا network sockets أو external APIs أو AI/LLM، ولا subprocess orchestration، ولا queue/worker، ولا retry daemon، ولا CLI، ولا persistence migration جديدة.

## 3. Existing contracts reused

| Existing contract | Role in Module 1.2 | Forbidden change |
|---|---|---|
| `Task` | Owns execution identity, status, `ExecutionSpec`, and version | لا يتم إنشاء Task بديل ولا تعديل identity |
| `ExecutionAuthorization` | Sole authorization proof for Scope + Target + expiry | لا يتم إنشاء `ReconAuthorization` |
| `PluginHost` | Validates manifest, capability, compatibility, invocation, limits, and result | لا يتم تجاوز الـHost أو استدعاء Plugin مباشرة |
| `PluginInvocation` | Host-created immutable invocation | لا يستطيع Pipeline أو Plugin تغيير `scope_id`, `target_id`, `task_id`, أو limits |
| `ReconResult` | Deterministic Plugin output | لا يتم حفظ raw payload أو نتيجة غير bound |
| `ReconIngestionService` | Converts result to assets and commits one result atomically | لا يتم تنفيذ SQL من orchestrator |
| `SQLiteUnitOfWork` | Transaction boundary for each ingestion unit | لا توجد transaction طويلة تغطي كامل pipeline |

## 4. Pipeline vocabulary

### `PipelineDefinition`

Immutable, versioned definition identified by `pipeline_id` and `pipeline_version`. It contains an ordered tuple of `PipelineStepDefinition` objects. A definition is data, not executable code, and must be validated before execution.

### `PipelineStepDefinition`

يحدد `step_id`، و`plugin_id`، ونسخة العقد المطلوبة، والـcapabilities المطلوبة، ونوع الإدخال المقبول، وسياسة الإخراج، و`max_observations` الخاصة بالخطوة. لا يحدد Target جديدًا ولا يستطيع تعديل authorization.

### `PipelineContext`

Immutable host-owned context containing only:

```text
task_id
scope_id
target_id
execution_authorization
pipeline_id / pipeline_version
current_step_id
remaining_budget
bounded_input_asset_ids
previous_step_receipts
deadline
```

لا يحتوي على database connection أو raw HTTP response أو credentials أو arbitrary filesystem path.

### `PipelinePhase`

Ephemeral orchestrator phase:

```text
VALIDATING → EXECUTING → INGESTING → NEXT_STEP / COMPLETED
                         └──────────→ FAILED / CANCELLED
```

`PipelinePhase` ليست بديلًا عن `TaskStatus` وليست persisted في Module 1.2.

## 5. Pipeline execution flow

```text
┌──────────────┐
│ Task PENDING │
└──────┬───────┘
       │ authorize + validate definition + resolve Plugin manifests
       ▼
┌─────────────────────────┐
│ Task RUNNING / VALIDATE │
└──────────────┬──────────┘
               │ re-check authorization, expiry, target, budget
               ▼
┌─────────────────────────┐
│ Build immutable Context  │◄──────────────┐
└──────────────┬──────────┘               │
               ▼                          │
┌─────────────────────────┐               │
│ PluginHost.invoke(step)  │               │
└──────────────┬──────────┘               │
               │ ReconResult              │
               ▼                          │
┌─────────────────────────┐               │
│ Validate result + limits │               │
└──────────────┬──────────┘               │
               ▼                          │
┌─────────────────────────┐               │
│ INGESTING: one UoW tx   │               │
│ ReconIngestionService   │               │
└──────────────┬──────────┘               │
               │ commit                   │ rollback
               ▼                          └──────────────► FAILED
┌─────────────────────────┐
│ Persist step receipt     │
│ Advance bounded inputs   │
└──────────────┬──────────┘
               │ more steps
               ├───────────────────────────────┐
               │                               │ no more steps
               ▼                               ▼
      ┌─────────────────┐              ┌─────────────────┐
      │ NEXT_STEP       │              │ Task COMPLETED  │
      └─────────────────┘              └─────────────────┘

Cancellation is checked before invocation, after invocation, before ingestion,
and before commit. A confirmed cancellation transitions RUNNING → CANCELLED.
```

## 6. Plugin chaining and safe asset propagation

Chaining is **derived-data chaining**, not target expansion. A later Plugin may receive only assets that were already persisted by an earlier successful step and that satisfy all of the following conditions:

| Guard | Required proof |
|---|---|
| Scope identity | `asset.scope_id == context.scope_id` |
| Target identity | `asset.target_id == context.target_id` |
| Task provenance | observation was produced by the same Task or an explicitly permitted predecessor receipt |
| Asset kind | input kind is declared in the next step’s manifest/contract |
| Canonical value | value is loaded from persisted canonical data; no raw string inference |
| Authorization | original `ExecutionAuthorization` is still valid and Include-bound |
| Budget | number and encoded size of propagated assets fit remaining limits |

The next Plugin receives an immutable `PluginInputBundle` containing bounded asset references and canonical values. It does not receive a mutable repository, a Target collection, an authorization object with mutation methods, or a callback capable of creating a new invocation.

An input mapper must fail closed when an asset kind is unsupported, an asset belongs to another Target/Scope, the value is archived, the provenance is missing, or the bundle exceeds limits. It must never “skip” an unsafe item and continue silently; the step fails with a typed boundary error.

## 7. Orchestrator interfaces and service boundaries

هذه هي العقود التي تم تنفيذها في هذه الشريحة؛ وتبقى حدودها المعمارية ملزمة لأي توسعة لاحقة.

```text
ReconPipelineOrchestrator
  execute(
    task: Task,
    authorization: ExecutionAuthorization,
    definition: PipelineDefinition,
    cancellation: CancellationSignal,
  ) -> PipelineExecutionReport
```

```text
PluginStepRunner
  run_step(
    context: PipelineContext,
    step: PipelineStepDefinition,
    input: PluginInputBundle,
  ) -> ReconResult
```

```text
PipelineInputResolver
  resolve(
    context: PipelineContext,
    step: PipelineStepDefinition,
    prior_receipts: tuple[StepReceipt, ...],
  ) -> PluginInputBundle
```

```text
PipelineBudget
  derive(task_spec: ExecutionSpec, global_policy: GlobalReconPolicy) -> PipelineBudget
  reserve_step(output_bytes: int, observation_count: int) -> PipelineBudget
```

```text
PipelineExecutionReport
  task_id
  pipeline_id / pipeline_version
  status: completed | failed | cancelled
  step_receipts: tuple[StepReceipt, ...]
  committed_observation_count
  committed_asset_count
  failure: PipelineFailure | None
```

### Boundary ownership

| Responsibility | Owner | Must not be owned by |
|---|---|---|
| Authorization decision | existing Scope/application services | Plugin, pipeline definition |
| Task state transition | Task/application service | Plugin, repository mapper |
| Plugin compatibility/capability validation | `PluginHost` | Orchestrator shortcuts |
| Input derivation | `PipelineInputResolver` | Plugin arbitrary target selector |
| Result validation | `PluginHost` + ingestion boundary | raw persistence adapter alone |
| Asset correlation/persistence | `ReconIngestionService` + repository | Plugin or orchestrator SQL |
| Transaction commit/rollback | `UnitOfWork` | one transaction around whole pipeline |
| Cancellation decision | orchestrator/application boundary | Plugin unilateral state mutation |

## 8. Task lifecycle and state matrix

Because the current Task state machine has no `INGESTING` status, the following matrix distinguishes persisted Task status from ephemeral pipeline phase.

| Event | Persisted Task status | Ephemeral phase | Allowed outcome |
|---|---|---|---|
| Pipeline accepted | `PENDING` | `VALIDATING` | authorization and definition checks only |
| Execution starts | `RUNNING` | `EXECUTING` | version-guarded transition |
| Plugin returns success | `RUNNING` | `INGESTING` | result validation and one short UoW |
| Ingestion commits | `RUNNING` | `NEXT_STEP` | continue only if budget/auth remain valid |
| Last step commits | `COMPLETED` | `COMPLETED` | terminal success |
| Plugin contract failure | `FAILED` | `FAILED` | previous committed steps remain |
| Ingestion rollback | `FAILED` | `FAILED` | current result leaves no partial rows |
| Cancellation before invocation | `CANCELLED` | `CANCELLED` | no Plugin call |
| Cancellation after Plugin return | `CANCELLED` | `CANCELLED` | result is not ingested unless explicit policy says commit-before-cancel; default is reject |
| Cancellation during ingestion | `FAILED` or `CANCELLED` according to commit point | `CANCELLED` | transaction is atomic; no half-result |
| Authorization expiry | `FAILED` | `FAILED` | no subsequent step or ingestion |

### Required state-transition decision

The recommended default is **cancel-before-ingest**: if cancellation is observed after a Plugin returns but before ingestion begins, the result is rejected and the Task becomes `CANCELLED`. If cancellation is observed after the transaction has committed, that committed result is retained and the orchestrator stops before the next step. This avoids inventing a rollback over durable audit data.

## 9. Atomic ingestion and partial failures

Each successful Plugin result forms one ingestion unit:

```text
BEGIN short transaction
  re-check Scope/Target/Task parents
  re-check result identity and authorization binding
  correlate/upsert assets
  insert idempotent observations
  insert typed projections
  verify row counts and budget consumption
COMMIT
```

A failure rolls back only the current ingestion unit. Results committed by earlier steps are not deleted, rewritten, or marked as if they never happened. The final report must expose the committed step receipts and the failed step, without exposing raw SQL or credentials.

There is no automatic retry in 1.2. A future retry policy must use the same Task/authorization model, a new explicit attempt identity, idempotent result digest, and a bounded retry budget. Silent retry is prohibited because it can duplicate side effects in future real-world Plugins.

## 10. Cancellation and recovery policy

Cancellation is cooperative at the orchestrator boundary. The orchestrator checks a monotonic cancellation signal at these points:

1. before transitioning `PENDING → RUNNING`;
2. before each Plugin invocation;
3. immediately after Plugin return;
4. before starting ingestion;
5. inside the ingestion boundary before commit;
6. before starting the next step.

The Plugin contract must not receive a capability to mutate Task state or commit independently. A non-cooperative future external executor is outside this slice and requires a separate process-control design.

Recovery is restart-safe at the result level: an already committed result can be presented again because asset identity and observation idempotency digest prevent duplicate durable observations. A pipeline restart must not infer that an uncommitted step succeeded merely because its Plugin was invoked.

## 11. Resource constraints and authorization enforcement

The effective budget is the minimum of Task limits, global policy, and the remaining pipeline budget:

```text
effective_timeout      = min(task.timeout, global.timeout, remaining.timeout)
effective_output_bytes = min(task.output_cap, global.output_cap, remaining.output_cap)
effective_assets        = min(global.max_assets, remaining.max_assets)
effective_payload       = min(global.max_payload, remaining.payload)
```

No Plugin, manifest, pipeline definition, or step may increase any Task limit. The host rejects an invocation when a requested limit exceeds the Task budget; it does not silently clamp it. The same rejection rule applies to results: oversized output, too many observations, oversized canonical values, or oversized propagated asset bundles are rejected rather than truncated.

Budget accounting is cumulative across the pipeline. A step consumes budget only after its result passes validation and its ingestion transaction commits. A failed or rolled-back step does not become a source of downstream inputs.

Authorization is revalidated before every step and before every ingestion unit. The required checks are:

```text
authorization.scope_id == task.scope_id
authorization.matched_target_id == task.target_id
authorization.matching_rule == INCLUDE
authorization.expires_at is absent OR now < expires_at
result.scope_id == task.scope_id
result.target_id == task.target_id
result.task_id == task.id
```

Any mismatch is a typed failure and stops the pipeline fail-closed.

## 12. Failure taxonomy

| Failure class | Example | Persisted result |
|---|---|---|
| Definition invalid | duplicate step ID, unsupported contract major | `FAILED`, no Plugin call |
| Capability mismatch | step requests capability not approved by manifest/host | `FAILED`, no Plugin call |
| Authorization invalid | expired, excluded, cross-target, cross-scope | `FAILED`, no ingestion |
| Input boundary invalid | archived asset, wrong kind, oversized bundle | `FAILED`, no Plugin call |
| Plugin contract failure | malformed or incompatible `ReconResult` | `FAILED`, current step not committed |
| Resource exceeded | timeout, payload, observation, asset budget | `FAILED`, current step not committed |
| Ingestion failure | FK, constraint, mapper, correlation conflict | `FAILED`, current transaction rolled back |
| Cancellation | user/system cancellation at safe checkpoint | `CANCELLED`, prior commits retained |
| Persistence infrastructure | database unavailable or transaction failure | `FAILED`, current transaction rolled back |

No raw database exception, traceback, command line, credential, or raw plugin payload crosses the application result boundary.

## 13. Security verification strategy

يجب أن يثبت التنفيذ المنجز، دون network access، ما يلي:

| Test family | Required proof |
|---|---|
| Start guard | Task must be `PENDING`, authorization must be Include-bound and unexpired |
| Step guard | Every step re-checks Task/Scope/Target/expiry and compatibility |
| Chaining | Later step receives only persisted same-target assets with approved kinds |
| Scope isolation | Cross-scope and cross-target asset injection is rejected before Plugin call |
| Limit monotonicity | Pipeline and Plugin cannot raise timeout, output, asset, or payload limits |
| Atomicity | Failed current ingestion leaves zero current-step rows while earlier commits remain |
| Cancellation | No call after cancellation; no partial commit; prior commits retained |
| Idempotency | Restarting a committed result does not duplicate observations |
| Failure redaction | Typed errors contain no SQL, credentials, raw payload, or traceback |
| Static boundary | No socket, DNS, HTTP, subprocess, external API, AI/LLM, or scanner invocation |
| Concurrency | Stale Task or asset versions fail closed and do not overwrite newer data |

## 14. Observability and audit contract

Every pipeline execution should produce a structured audit record at the application boundary containing correlation ID, Task ID, pipeline ID/version, ordered step IDs, start/end timestamps, outcome, committed counts, and typed failure code. It should not contain raw target query strings, credentials, raw response bodies, or arbitrary Plugin metadata.

The audit record is not a second authorization model and is not a substitute for `asset_observations`. Durable audit persistence is a separate decision; Module 1.2 design assumes existing logging/audit facilities and does not add a migration.

## 15. Approved decisions and implementation status

| Decision | Implemented decision | Reason |
|---|---|---|
| `INGESTING` representation | Ephemeral `PipelinePhase`, Task remains `RUNNING` | Protects closed Module 0 state machine |
| Cancellation after Plugin return | Cancel before ingest; retain commits already completed | Prevents durable partial current-step results |
| Retry policy | No automatic retry in 1.2 | Avoids duplicate side effects before attempt model exists |
| Chaining input | Same-target persisted canonical assets only | Prevents scope expansion and arbitrary target selection |
| Budget behavior | Reject over-limit requests/results; never silently clamp/truncate | Preserves explicit security semantics |
| Transaction boundary | One short UoW per successful Plugin result | Atomic partial failure recovery |
| Pipeline persistence | No new migration in 1.2 | Keep orchestration design separate from durable execution history |
| Non-cooperative executor | Deferred to process-control/sandbox design | Not safe to imply cancellation guarantees prematurely |

## 16. Implementation record and closure

The approved decisions above were implemented without reopening Module 0 or changing the existing Task state machine. The implementation consists of `src/cyberos/recon/pipeline.py`, the additive `PluginHost.invoke_running` route in `src/cyberos/recon/host.py`, `src/cyberos/application/recon_task_result.py`, and the integration/security matrix in `tests/integration/test_recon_orchestration.py`.

The final verification completed with **319 passing tests** across the full regression suite. `bash scripts/check.sh` passed pytest, Ruff check, Ruff format check, `mypy --strict`, and wheel build. The explicit boundary scan passed after correcting the scan expression to avoid the legitimate `MigrationRunner.run()` false positive; no network API, DNS, HTTP, subprocess, external API, AI/LLM, or migration 0006+ was introduced.

Module 1.2 is therefore closed at this boundary. Module 1.3 must not begin until a new architecture document is reviewed and explicitly approved.

## Internal references

1. Module 1.0 plugin contracts: `cyberos-core/src/cyberos/recon/contracts.py` and `cyberos-core/src/cyberos/recon/host.py`.
2. Module 1.1 ingestion boundary: `cyberos-core/src/cyberos/application/recon_ingestion.py`.
3. Module 1.1 persistence boundary: `cyberos-core/src/cyberos/persistence/recon_repository.py`.
4. Existing Task state machine: `cyberos-core/src/cyberos/domain/task/model.py`.
5. Approved Module 1.1 design: `cyberos-core/docs/architecture/module-1-1-recon-assets-persistence-design.md`.
