# Module 1.1 — Recon Data Models & Persistence Architecture

**Status:** Implemented — Module 1.1 scope closed  
**Migration:** `0005_recon_assets.sql` created and executed through `MigrationRunner`  
**Baseline:** Module 0 and Module 1.0 remain closed and unchanged  
**Security posture:** Fail-closed, target-bound, authorization-bound, archive-only

> هذه الوثيقة هي المرجع المعتمد لتخزين مخرجات Recon المنظمة. التنفيذ الحالي يلتزم بالنطاق المعتمد ولا يتضمن Recon حقيقيًا أو أي اتصالات خارجية.

## 1. Executive decision

Module 1.1 يحول مخرجات `ReconResult` من قيمة مؤقتة إلى **Structured Recon Assets** قابلة للاستعلام والربط مع `Task` و`Target` و`Scope`. التصميم لا يحفظ plugin payload كما هو؛ بل يفصل بين هوية الأصل canonical وبين كل مشاهدة provenance له.

الطبقة المقترحة تتكون من:

1. `assets`: سجل canonical واحد لكل أصل داخل حدود Scope وTarget.
2. `asset_observations`: سجل provenance append-only لكل مشاهدة ناتجة عن Task وPlugin.
3. `subdomain_records`: projection منظم للنطاقات الفرعية.
4. `port_service_records`: projection منظم للمنافذ والخدمات.
5. `http_endpoint_records`: projection منظم لمسارات HTTP والتقنيات المحدودة.

هذا التصميم يحافظ على تاريخ المهام، يجعل إعادة إدخال النتيجة idempotent، ويمنع دمج أصلين متساويين نصيًا لكنهما تابعان لحدود تفويض مختلفة.

## 2. Scope and non-goals

### داخل النطاق

يشمل التصميم Domain vocabulary، Draft DDL لـ0005، العلاقات مع الجداول السابقة، القيود والفهارس، correlation/upsert، Repository Port، UnitOfWork boundary، structured/raw retention، واختبارات التنفيذ المستقبلية.

### خارج النطاق

لا يشمل DNS أو HTTP probing أو Nmap أو passive discovery أو real network adapters أو Plugin transport أو Recon CLI أو AI/LLM أو cloud scanners أو Evidence/Findings/Reports أو raw artifact store. كل عنصر من هذه العناصر يحتاج slice وتصميمًا مستقلًا.

## 3. Compatibility with Module 1.0

يبقى `ExecutionAuthorization` نموذج التفويض الوحيد، ويبقى `Task` نموذج التنفيذ الوحيد. لا يجوز إنشاء `AssetAuthorization` أو `ReconAuthorization` أو Task بديل.

```text
ScopeValidationService
        │ creates existing ExecutionAuthorization
        ▼
Task + ExecutionAuthorization + PluginInvocation
        │ PluginHost validates binding and limits
        ▼
ReconResult
        │ application revalidates identity and authorization
        ▼
AuthorizedReconIngestion
        │ one SQLite transaction
        ▼
assets + asset_observations + typed records
```

`AuthorizedReconIngestion` هو application command مُتحقق منه، وليس نموذج تفويض جديدًا. الـRepository يستعمله كحاجز دفاعي إضافي ولا يصبح Security Authority.

## 4. Data flow and aggregate boundaries

```text
┌──────────────────────────┐
│ Existing Task             │
│ scope_id + target_id     │
└────────────┬─────────────┘
             │ bound to
             ▼
┌──────────────────────────┐       ┌──────────────────────┐
│ Existing Authorization    │──────▶│ ReconResult          │
│ INCLUDE + not expired     │       │ deterministic output │
└────────────┬─────────────┘       └──────────┬───────────┘
             └────────────────┬───────────────┘
                              ▼
                   ┌─────────────────────┐
                   │ ReconIngestionService│
                   │ validate + correlate │
                   └──────────┬──────────┘
                              │ one UoW transaction
                              ▼
       ┌──────────────────────────────────────────┐
       │ SQLiteReconRepository                    │
       ├──────────────────────────────────────────┤
       │ assets                                   │
       │   ├── asset_observations                 │
       │   ├── subdomain_records                  │
       │   ├── port_service_records               │
       │   └── http_endpoint_records              │
       └──────────────────────────────────────────┘
```

`AssetAggregate` owns one canonical asset and its typed projection. It does not own Scope, Target, or Task aggregates. One accepted `ReconResult` is the atomic write unit; multiple independent Tasks are not one transaction.

## 5. Domain models and value objects

| Object | Responsibility | Projection |
|---|---|---|
| `AssetId` | Strong UUID4 identity | `assets.id` |
| `AssetKind` | `domain`, `subdomain`, `ip_address`, `host`, `url`, `service` | `assets.asset_kind` |
| `CanonicalAssetValue` | Normalized correlation key | `assets.canonical_value` |
| `AssetStatus` | `active` or `archived` | `assets.status` |
| `AssetAggregate` | Canonical asset plus typed projection | `assets` + one child table |
| `AssetObservationId` | Provenance event identity | `asset_observations.id` |
| `AssetObservation` | Task/Plugin observation of an asset | `asset_observations` |
| `DiscoveredSubdomain` | Canonical FQDN projection | `subdomain_records` |
| `DiscoveredService` | Transport/port/service projection | `port_service_records` |
| `DiscoveredHttpEndpoint` | Scheme/port/path/technology projection | `http_endpoint_records` |
| `AuthorizedReconIngestion` | Validated application command | no direct table |
| `ReconIngestionReceipt` | Commit summary and counts | no table in 1.1 |

The Domain layer enforces UUID4, UTC-aware timestamps, canonical values, bounded text, enum values, child-kind compatibility, Scope/Target/Task equality, monotonic first/last seen times, and archive-only lifecycle. SQLite enforces structural integrity and conservative limits.

## 6. Aggregate ER diagram

```text
workspaces
    │
    └── engagements
            │
            └── scopes ───────────────┐
                    │                 │
                    └── targets       │
                          │            │
                          └────────────┼──────────────┐
                                       │              │
tasks ─────────────────────────────────┘              │
  │                                                    │
  └──────────────┐                                     │
                 ▼                                     ▼
              assets ◀──────────── asset_observations │
                 │                                     │
        ┌────────┼──────────┐                         │
        ▼        ▼          ▼                         │
 subdomain   port/service   http endpoint             │
 records      records       records                   │

Every operational FK uses ON DELETE RESTRICT and ON UPDATE RESTRICT.
Composite keys preserve Scope/Target/Task context instead of trusting
independent duplicated columns.
```

## 7. Table responsibilities and identity

### `assets`

`assets` stores one canonical row per `(scope_id, target_id, asset_kind, canonical_value)`. `first_seen_*` fields are immutable provenance; `last_seen_*` fields are mutable monotonic metadata. The same hostname found under different Targets is intentionally not globally merged.

### `asset_observations`

`asset_observations` is append-only provenance. Its idempotency key is `(asset_id, task_id, plugin_id, result_digest)`. Replaying the same deterministic result is a no-op; a different Task produces a new observation even if the canonical asset is the same.

### `subdomain_records`

Stores canonical `fqdn` and `parent_domain`. Its domain identity is `(scope_id, target_id, fqdn)`. The Domain layer must prove that the parent asset has a compatible kind.

### `port_service_records`

Stores `(transport, port)` plus bounded service fingerprint fields. Its identity is `(scope_id, target_id, asset_id, transport, port)`. Raw banners do not belong in this table.

### `http_endpoint_records`

Stores normalized scheme, effective port, path, optional query digest, status code, bounded title, and a JSON array of bounded technology names. Raw query strings, credentials, response bodies, and arbitrary headers are excluded. Its identity is `(scope_id, target_id, asset_id, scheme, port, path)`.

## 8. Draft DDL — `0005_recon_assets.sql`

> هذا SQL Draft داخل الوثيقة فقط. لا يجب نسخه إلى `migrations/versions` أو تشغيله قبل اعتماد التصميم.

```sql
-- Draft only: 0005_recon_assets.sql
-- No IF NOT EXISTS. No BEGIN/COMMIT inside this file.

-- Composite parent keys are required by the context-preserving FKs below.
CREATE UNIQUE INDEX uq_tasks_scope_target_id_bridge
    ON tasks (scope_id, target_id, id);

CREATE UNIQUE INDEX uq_targets_scope_id_bridge
    ON targets (scope_id, id);

CREATE TABLE assets (
    id TEXT PRIMARY KEY NOT NULL,
    scope_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    asset_kind TEXT NOT NULL
        CHECK (asset_kind IN ('domain', 'subdomain', 'ip_address', 'host', 'url', 'service')),
    canonical_value TEXT NOT NULL,
    display_value TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived')),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    first_seen_task_id TEXT NOT NULL,
    last_seen_task_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    version INTEGER NOT NULL DEFAULT 1
        CHECK (version >= 1),
    FOREIGN KEY (scope_id, target_id)
        REFERENCES targets(scope_id, id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY (scope_id, target_id, first_seen_task_id)
        REFERENCES tasks(scope_id, target_id, id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY (scope_id, target_id, last_seen_task_id)
        REFERENCES tasks(scope_id, target_id, id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CHECK (length(trim(id)) = 36),
    CHECK (length(trim(scope_id)) = 36),
    CHECK (length(trim(target_id)) = 36),
    CHECK (length(trim(first_seen_task_id)) = 36),
    CHECK (length(trim(last_seen_task_id)) = 36),
    CHECK (length(trim(canonical_value)) BETWEEN 1 AND 4096),
    CHECK (length(trim(display_value)) BETWEEN 1 AND 4096),
    CHECK (last_seen_at >= first_seen_at),
    CHECK (status = 'active' AND archived_at IS NULL
        OR status = 'archived' AND archived_at IS NOT NULL)
    -- Expand the exact UTC ISO-8601 checks used by 0003/0004 for every timestamp.
);

CREATE UNIQUE INDEX uq_assets_scope_target_kind_value
    ON assets (scope_id, target_id, asset_kind, canonical_value);

CREATE UNIQUE INDEX uq_assets_scope_target_id_bridge
    ON assets (scope_id, target_id, id);

CREATE INDEX idx_assets_scope_status_kind
    ON assets (scope_id, status, asset_kind);

CREATE INDEX idx_assets_target_last_seen
    ON assets (target_id, last_seen_at DESC);

CREATE TABLE asset_observations (
    id TEXT PRIMARY KEY NOT NULL,
    asset_id TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    plugin_id TEXT NOT NULL,
    plugin_version TEXT NOT NULL,
    contract_version TEXT NOT NULL,
    result_digest TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (scope_id, target_id, asset_id)
        REFERENCES assets(scope_id, target_id, id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY (scope_id, target_id)
        REFERENCES targets(scope_id, id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY (scope_id, target_id, task_id)
        REFERENCES tasks(scope_id, target_id, id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CHECK (length(trim(id)) = 36),
    CHECK (length(trim(asset_id)) = 36),
    CHECK (length(trim(plugin_id)) BETWEEN 1 AND 80),
    CHECK (length(trim(plugin_version)) BETWEEN 1 AND 64),
    CHECK (length(trim(contract_version)) BETWEEN 1 AND 16),
    CHECK (length(trim(result_digest)) = 64)
    -- Expand the exact UTC ISO-8601 checks for observed_at and created_at.
);

CREATE UNIQUE INDEX uq_asset_observations_idempotency
    ON asset_observations (asset_id, task_id, plugin_id, result_digest);

CREATE INDEX idx_asset_observations_target_seen
    ON asset_observations (target_id, observed_at DESC);

CREATE TABLE subdomain_records (
    id TEXT PRIMARY KEY NOT NULL,
    asset_id TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    fqdn TEXT NOT NULL,
    parent_domain TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived')),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    version INTEGER NOT NULL DEFAULT 1
        CHECK (version >= 1),
    FOREIGN KEY (scope_id, target_id, asset_id)
        REFERENCES assets(scope_id, target_id, id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY (scope_id, target_id)
        REFERENCES targets(scope_id, id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY (scope_id, target_id, task_id)
        REFERENCES tasks(scope_id, target_id, id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CHECK (length(trim(fqdn)) BETWEEN 1 AND 4096),
    CHECK (length(trim(parent_domain)) BETWEEN 1 AND 4096),
    CHECK (last_seen_at >= first_seen_at),
    CHECK (status = 'active' AND archived_at IS NULL
        OR status = 'archived' AND archived_at IS NOT NULL)
    -- Domain layer enforces canonical FQDN and compatible asset kind.
);

CREATE UNIQUE INDEX uq_subdomains_scope_target_fqdn
    ON subdomain_records (scope_id, target_id, fqdn);

CREATE INDEX idx_subdomains_scope_status
    ON subdomain_records (scope_id, status, last_seen_at DESC);

CREATE TABLE port_service_records (
    id TEXT PRIMARY KEY NOT NULL,
    asset_id TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    transport TEXT NOT NULL
        CHECK (transport IN ('tcp', 'udp')),
    port INTEGER NOT NULL
        CHECK (port BETWEEN 1 AND 65535),
    service_name TEXT,
    product TEXT,
    service_version TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived')),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    version INTEGER NOT NULL DEFAULT 1
        CHECK (version >= 1),
    FOREIGN KEY (scope_id, target_id, asset_id)
        REFERENCES assets(scope_id, target_id, id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY (scope_id, target_id)
        REFERENCES targets(scope_id, id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY (scope_id, target_id, task_id)
        REFERENCES tasks(scope_id, target_id, id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CHECK (service_name IS NULL OR length(trim(service_name)) BETWEEN 1 AND 160),
    CHECK (product IS NULL OR length(trim(product)) BETWEEN 1 AND 256),
    CHECK (service_version IS NULL OR length(trim(service_version)) BETWEEN 1 AND 128),
    CHECK (last_seen_at >= first_seen_at),
    CHECK (status = 'active' AND archived_at IS NULL
        OR status = 'archived' AND archived_at IS NOT NULL)
);

CREATE UNIQUE INDEX uq_services_scope_target_asset_transport_port
    ON port_service_records (scope_id, target_id, asset_id, transport, port);

CREATE INDEX idx_services_scope_status_port
    ON port_service_records (scope_id, status, port);

CREATE TABLE http_endpoint_records (
    id TEXT PRIMARY KEY NOT NULL,
    asset_id TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    scheme TEXT NOT NULL
        CHECK (scheme IN ('http', 'https')),
    port INTEGER NOT NULL
        CHECK (port BETWEEN 1 AND 65535),
    path TEXT NOT NULL,
    query_fingerprint TEXT,
    status_code INTEGER,
    title TEXT,
    technologies_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived')),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    version INTEGER NOT NULL DEFAULT 1
        CHECK (version >= 1),
    FOREIGN KEY (scope_id, target_id, asset_id)
        REFERENCES assets(scope_id, target_id, id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY (scope_id, target_id)
        REFERENCES targets(scope_id, id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY (scope_id, target_id, task_id)
        REFERENCES tasks(scope_id, target_id, id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CHECK (length(trim(path)) BETWEEN 1 AND 4096),
    CHECK (substr(path, 1, 1) = '/'),
    CHECK (query_fingerprint IS NULL OR length(trim(query_fingerprint)) = 64),
    CHECK (status_code IS NULL OR status_code BETWEEN 100 AND 599),
    CHECK (title IS NULL OR length(title) <= 512),
    CHECK (length(trim(technologies_json)) > 0
        AND json_valid(technologies_json) = 1
        AND json_type(technologies_json) = 'array'),
    CHECK (last_seen_at >= first_seen_at),
    CHECK (status = 'active' AND archived_at IS NULL
        OR status = 'archived' AND archived_at IS NOT NULL)
);

CREATE UNIQUE INDEX uq_http_scope_target_asset_scheme_port_path
    ON http_endpoint_records (scope_id, target_id, asset_id, scheme, port, path);

CREATE INDEX idx_http_scope_status_last_seen
    ON http_endpoint_records (scope_id, status, last_seen_at DESC);
```

### DDL review notes

The repeated timestamp constraints are intentionally represented by comments in this design draft to keep the document readable. The actual migration, after approval, must expand the exact UTC ISO-8601 `CHECK` expressions already used by migrations 0003 and 0004 for every timestamp column. The migration must contain no `IF NOT EXISTS`, no inner `BEGIN`, and no inner `COMMIT`; the existing MigrationRunner owns ordering, checksum, transaction, and rollback.

The bridge indexes do not modify Module 0 semantics. They make the duplicated Scope/Target context structurally verifiable by SQLite composite foreign keys. If the project rejects adding these supporting unique indexes to existing tables, the alternative is to remove duplicated context columns and accept weaker database-level correlation; that alternative is not recommended.

## 9. Constraint matrix

| Invariant | SQL | Domain/Application | Decision |
|---|---:|---:|---|
| UUID shape and non-null identity | Yes | Yes | Both |
| FK to Scope/Target/Task/Asset | Yes | Yes | Both |
| `ON DELETE RESTRICT` and `ON UPDATE RESTRICT` | Yes | Yes | Both |
| Scope/Target/Task composite consistency | Yes | Yes | Both |
| Allowed enum values | Yes | Yes | Both |
| Canonical FQDN/IP/URL normalization | No | Yes | Domain only |
| Asset-kind to child compatibility | No | Yes | Domain only |
| Unique canonical correlation key | Yes | Yes | Both |
| UTC timestamp shape and ordering | Yes | Yes | Both |
| Version and optimistic concurrency | Yes | Yes | Both |
| Archive-only lifecycle | Yes | Yes | Both |
| Authorization validity and expiry | No | Yes | Application only |
| Plugin capability policy | No | Yes | Host only |

SQL protects storage structure; it must not reimplement TargetCanonicalizer, ScopeMatcher, or authorization policy.

## 10. Deduplication and correlation

### Identity boundary

Correlation is never global. The minimum identity is:

```text
scope_id + target_id + asset_kind + canonical_value
```

Equal values under different authorized Targets remain separate assets. A future analytical projection may relate them, but persistence must not erase authorization provenance.

### Atomic upsert algorithm

For one validated successful result, `ReconIngestionService` performs these operations inside one UnitOfWork transaction:

1. Re-check Task identity, Scope, Target, Include decision, and expiry.
2. Validate `ReconResult` identity against Task, plugin manifest, contract, schema, and effective limits.
3. Canonicalize each observation and calculate a stable SHA-256 digest from the canonical structured representation.
4. Find or insert the `assets` row by the canonical identity key.
5. Insert `asset_observations` unless the exact idempotency key already exists.
6. Insert or update the appropriate typed projection.
7. Update only mutable last-seen metadata and increment version when meaningful metadata changes.
8. Commit all changes together; any validation, uniqueness, FK, or concurrency failure rolls back the whole result.

First-seen fields are immutable. Last-seen fields are monotonic. Equal observation timestamps use Task UUID lexicographic order as a deterministic tie-breaker.

| Situation | Semantics |
|---|---|
| Same Task, plugin, and digest | Idempotent no-op |
| Same asset from another Task | One asset plus a new observation |
| Changed mutable fingerprint | Same identity, updated projection, new observation |
| Conflicting immutable identity | Reject correlation conflict; never merge silently |
| Out-of-target result | Reject entire ingestion; no partial rows |
| Failed result | No asset rows; existing Task failure remains the audit record |
| Missing/expired/excluded authorization | Reject before write |

## 11. Repository and UnitOfWork contracts

### `ReconRepositoryPort`

```text
ingest(AuthorizedReconIngestion) -> ReconIngestionReceipt
get_asset(AssetId) -> AssetAggregate | None
list_assets(ScopeId, TargetId | None, AssetFilter) -> tuple[AssetAggregate, ...]
list_observations(AssetId) -> tuple[AssetObservation, ...]
list_subdomains(ScopeId, TargetId | None) -> tuple[DiscoveredSubdomain, ...]
list_services(ScopeId, TargetId | None) -> tuple[DiscoveredService, ...]
list_http_endpoints(ScopeId, TargetId | None) -> tuple[DiscoveredHttpEndpoint, ...]
archive_asset(AssetId, expected_version) -> AssetAggregate
archive_record(record_id, expected_version) -> ArchivedRecord
```

The port is persistence-agnostic. `SQLiteReconRepository` maps rows to Domain objects, uses parameterized SQL, translates SQLite exceptions into typed errors (`RECON_ASSET_DUPLICATE`, `RECON_CORRELATION_CONFLICT`, `RECON_PARENT_NOT_FOUND`, `RECON_RESULT_INVALID`, `CONCURRENCY_CONFLICT`), and never leaks SQL rows or raw database exceptions.

### Transaction boundary

```text
BEGIN
  validate parent context
  correlate/upsert assets
  insert idempotent observations
  upsert typed records
  verify row counts and invariants
COMMIT
```

Plugin execution is outside the database transaction. A single result is atomic. Independent Tasks are not grouped into a long-running transaction.

## 12. Structured versus raw artifact retention

SQLite stores canonical identity, typed records, provenance, timestamps, digests, plugin identity/version, and bounded display metadata. It must not store raw response bodies, raw banners, full headers, credentials, large logs, or arbitrary plugin dictionaries.

Raw output belongs to a future content-addressed `ArtifactStore` slice. The proposed future reference contains only `artifact_id`/SHA-256, media type, byte length, creation time, and retention class. Module 1.1 stores no raw BLOB and introduces no artifact table.

Normal APIs archive assets and typed records instead of hard-deleting them. Observations remain append-only for audit. Absence of a new observation is not proof that an asset disappeared.

## 13. Security and boundary protections

The future implementation must reject a result whose Task, Scope, Target, plugin identity, contract version, or authorization does not match the invocation. It must reject expired, excluded, missing, or non-Include authorization before any write; re-check parents inside the transaction; reject malformed canonical values, unsupported child kinds, oversized values, invalid digests, credentials, raw query material, and cross-target rows; and prevent plugins from choosing a different Scope, Target, or Task.

Persistence must not update authorization, Task state, or Scope state. It must not expose raw SQL, credentials, network payloads, or tracebacks through the application boundary. No hard delete is exposed.

The repository is a defensive persistence boundary, not a security authority. Authorization remains in the existing ScopeValidation/Application services.

## 14. Implementation test evidence
The approved implementation includes the following executable proof:

| Area | Required proof |
|---|---|
| Migration | Apply 0005 over 0004, checksum, forward-only behavior, quick_check, foreign_key_check |
| Schema | Exact table/index inventory, enum/length/time/JSON checks, composite FK rejection |
| Restriction | Task/Target/Scope/Asset delete and update blocked by RESTRICT |
| Atomicity | Invalid batch leaves zero partial rows |
| Domain | Canonical identity, child-kind compatibility, archive-only, first/last seen invariants |
| Correlation | Same-result idempotency, cross-Task observation, cross-Target isolation, conflict rejection |
| Repository | Round trip, typed error translation, optimistic concurrency, no SQL leakage |
| Security | Wrong Scope/Target, expiry, exclude, capability mismatch, oversized result, malformed digest, credential/query persistence, hard-delete attempt |
| Boundary static scan | No network, DNS, HTTP, subprocess, external API, AI/LLM, or real Recon behavior |

## 15. Performance and compatibility

Primary query paths are bounded by Scope and Target, so list indexes begin with those columns. Unique indexes serve deduplication and lookup. The design deliberately avoids global graph correlation, full-text search, JSON path indexes, and speculative optimization until measured data exists.

`0005` is forward-only above 0004. It must not alter migrations 0001–0004 or reinterpret existing Task/Target values. Existing Module 0 databases remain valid with zero Recon rows, and a fresh database must apply 0001–0005 deterministically after approval.

## 16. Decisions and implementation status

| Decision | Proposed default | Status |
|---|---|---|
| Add `asset_observations` | Required for provenance and idempotency | Approved and implemented |
| Identity boundary | `(scope_id, target_id, asset_kind, canonical_value)` | Approved and implemented |
| Composite bridge indexes | Add supporting unique indexes above 0004 | Approved and implemented |
| Cross-target global correlation | Not in 1.1 | Deferred |
| Raw artifact storage | Separate future ArtifactStore; no raw BLOB in 0005 | Approved and implemented |
| Query persistence | Digest only; never raw query | Approved and implemented |
| Hard delete | Forbidden; archive only | Fixed policy |
| FK policy | `ON DELETE/UPDATE RESTRICT` | Fixed policy |
| Migration execution | Only after design approval | Approved and executed |

## 17. Implementation record
The implementation added the `cyberos.domain.recon` models and repository port, `SQLiteReconRepository`, `ReconIngestionService`, strict persistence mapping, and migration `0005_recon_assets.sql`. It preserves the existing `ExecutionAuthorization` and `Task` contracts, re-checks Scope/Target/Task parents inside the transaction, rejects mismatched or expired authorization, rejects effective limits above the Task limits, and never persists raw query strings or raw BLOBs.

The full project suite now passes with **307 tests**. The official project gates passed: `pytest`, `ruff check`, `ruff format --check`, `mypy src/cyberos`, and `python -m build --wheel`. Module 1.1-specific tests cover migration checksum and idempotency, schema health, indexes, typed round trips, child projections, correlation idempotency, FK restrictions, rollback, authorization binding, result identity, limit rejection, and forbidden-side-effect static scanning.

No Module 0 or Module 1.0 runtime logic was reopened. No CLI, network adapter, scanner, raw artifact store, AI/LLM integration, sandbox, signing, or Module 1.2 work was added.
