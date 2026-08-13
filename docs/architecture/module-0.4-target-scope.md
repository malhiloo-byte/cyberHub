# Module 0.4 — Target & Scope Management

## Architecture & Schema Design Document

**الحالة:** مقترح للمراجعة والاعتماد — لا يوجد تنفيذ كودي في هذه الوثيقة  
**الإصدار:** `0.4.0-design`  
**يعتمد على:** Module 0.1 — Core Contracts، Module 0.2 — Persistence Kernel، Module 0.3 — Workspace & Engagement  
**المسار الإلزامي:** `Workspace → Engagement → Scope → Target → Scope Validation → Authorized Target → Job/Action`

> الهدف من Module 0.4 ليس تنفيذ Recon أو Scanner. الهدف هو بناء **حاجز تفويض محلي deterministic** يمنع أي وحدة تنفيذية مستقبلية من العمل على قيمة لا يثبت أنها داخل Scope مصرح به.

---

## 1. الملخص التنفيذي

يقترح هذا الموديول إضافة كيانين فقط إلى النواة: **Scope** بوصفه حدودًا منطقية مرتبطة بـEngagement، و**Target** بوصفه قاعدة هدف واحدة من نوع include أو exclude. لا يصبح أي Target صالحًا للتشغيل لمجرد أنه محفوظ في قاعدة البيانات؛ بل يجب أن يمر عبر مراحل التحقق والتفويض ثم ينتج كائنًا صريحًا من نوع `AuthorizedTarget`.

العلاقة المقترحة هي علاقة مملوكة بوضوح: Workspace يملك Engagements، وEngagement يملك Scopes، وScope يملك Targets. لا يوجد Target عالمي مستقل عن Scope، ولا يوجد lookup يسمح بإرسال raw string مباشرة إلى وحدة Job أو Action.

يستخدم Scope Matcher قواعد مطابقة محلية فقط. فهو لا يجري DNS resolution، ولا HTTP request، ولا port scan، ولا يعتمد على نتيجة أداة خارجية. هذه الحدود تمنع أن يتحول validation إلى تنفيذ شبكي غير مقصود.

### ما يدخل في Module 0.4

| المجال | النطاق المقترح |
|---|---|
| Domain | Scope وTarget وtyped IDs وlifecycle وnormalization |
| Authorization | Scope validation، authorization state، expiry، explicit exclude precedence |
| Matching | FQDN، wildcard، IPv4، IPv6، CIDR، URL بمطابقة محافظة |
| Persistence | `0003_target_scope.sql` وجدولا `scopes` و`targets` فقط |
| Application | ScopeService وTargetService وScopeValidationService |
| CLI | إنشاء وإدارة Scope وTarget، validate، authorize، evaluate read-only |
| Testing | unit، matcher، repository، migration، service، CLI، security boundary |

### ما لا يدخل في Module 0.4

لا يشمل الموديول أي Recon أو DNS lookup أو HTTP probing أو scanning أو exploitation أو Job execution أو Evidence أو Finding أو Report أو AI. كما لا يضيف authentication متعدد المستخدمين، ولا توقيعًا قانونيًا، ولا secret vault، ولا مزامنة سحابية.

---

## 2. القرارات المعمارية المقترحة للاعتماد

هذه قرارات تصميمية مقترحة وليست تنفيذًا. يلزم اعتمادها قبل بدء 0.4.a، وبالأخص القرارات التي تؤثر في معنى authorization أو اتساع المطابقة.

| القرار | المقترح | سبب القرار |
|---|---|---|
| ملكية Target | Target child داخل Scope ولا يوجد Target عالمي | منع استخدام هدف خارج سياقه |
| نوع القاعدة | `include` أو `exclude` لكل Target | تمثيل صريح وقابل للتدقيق |
| أولوية القواعد | أي Exclude مطابق يتغلب على Include | fail-closed ومنع التجاوز غير المقصود |
| الحالة القابلة للتشغيل | Scope بحالة `authorized` فقط | فصل التخزين عن التفويض التنفيذي |
| authorization reference | مطلوب عند الانتقال إلى `authorized` | منع تفويض صامت أو غير موثق |
| القاعدة الافتراضية | لا Include مطابق = رفض | deny by default |
| الحذف | archive فقط، دون hard delete | الحفاظ على السجل التاريخي |
| URL matching | مطابقة canonical exact فقط في الإصدار الأول | منع توسيع المسار ضمنيًا |
| wildcard | صيغة DNS wildcard محدودة، لا regex ولا `*` شامل | تقليل مساحة الخطأ |
| التنفيذ | `AuthorizedTarget` فقط يصل إلى Job/Action مستقبلية | منع تمرير raw target string |

### قرارات تحتاج تأكيدًا صريحًا

أقترح اعتماد القيم الآتية كـdefault safety policy، لكن يجب أن يوافق المستخدم عليها قبل التنفيذ:

1. رفض `0.0.0.0/0` و`::/0` دائمًا.
2. رفض wildcard العام مثل `*` و`*.*` وأي wildcard لا يحتوي على suffix صالح.
3. السماح بوجود Include وExclude متطابقين في Scope واحد؛ ويظل Exclude هو الفائز. هذا مفيد لتوثيق استثناء ضيق، لكنه يظهر كتحذير في validation.
4. اعتبار URL مطابقة exact بعد canonicalization؛ لا يوجد path-prefix أو host-only matching في الإصدار الأول.
5. منع target جديد داخل Scope مؤرشف أو Engagement مؤرشف.
6. اعتبار `expires_at` حدًا زمنيًا للتفويض؛ بعد انتهائه تكون النتيجة رفضًا حتى لو بقيت الحالة مخزنة كـ`authorized`.

---

## 3. Domain Models & Boundary Rules

### 3.1 Scope

```text
Scope
├── id: ScopeId (UUID4)
├── engagement_id: EngagementId (UUID4)
├── name: str, 1..160 بعد trim
├── description: str, 0..4000
├── status: draft | validated | authorized | archived
├── authorization_reference: str | None, max 1000
├── validated_at: aware UTC datetime | None
├── authorized_at: aware UTC datetime | None
├── expires_at: aware UTC datetime | None
├── created_at: aware UTC datetime
├── updated_at: aware UTC datetime
├── archived_at: aware UTC datetime | None
└── version: positive int, default 1
```

قواعد Scope المقترحة هي أن `draft` لا يملك timestamps الخاصة بالتحقق أو التفويض، وأن `validated` يملك `validated_at` دون `authorized_at`، وأن `authorized` يملك `validated_at` و`authorized_at` ومرجع تفويض غير فارغ. حالة `archived` نهائية ولا تقبل Targets جديدة ولا transitions عكسية.

لا يعني `validated` أن Scope مسموح للتشغيل. التحقق يثبت أن القواعد syntactically وsemantically صالحة، بينما `authorized` يثبت أن المستخدم اختار تفويض هذه الحدود صراحة.

### 3.2 Target

```text
Target
├── id: TargetId (UUID4)
├── scope_id: ScopeId (UUID4)
├── rule: include | exclude
├── kind: fqdn | wildcard | ipv4 | ipv6 | cidr | url
├── value: str (canonical value only)
├── status: active | archived
├── created_at: aware UTC datetime
├── updated_at: aware UTC datetime
├── archived_at: aware UTC datetime | None
└── version: positive int, default 1
```

يخزن `value` بصيغة canonical واحدة بعد نجاح parser خاص بالنوع. لا يعتمد النظام على مقارنة raw strings. لا نستخدم `COLLATE NOCASE` على القيمة كلها لأن URL path وquery قد يكونان case-sensitive؛ بدل ذلك يخفض canonicalizer الأجزاء التي تسمح بها semantics الخاصة بكل نوع.

`Target` لا يملك authorization مستقلًا عن Scope. فهو يرث سياقه، لكن matcher لا يعيده كـ`AuthorizedTarget` إلا عندما يكون Scope نفسه `authorized` وغير منتهٍ وغير مؤرشف، ويكون Target active ومطابقًا.

### 3.3 Target kind semantics

| النوع | canonicalization والمطابقة المقترحة |
|---|---|
| `fqdn` | lower-case، إزالة trailing dot، IDNA policy ثابتة، مطابقة hostname exact |
| `wildcard` | يقبل صيغة `*.` في أول label فقط؛ يطابق subdomain وليس apex تلقائيًا |
| `ipv4` | parsing عبر IPv4 value واحد؛ لا يقبل CIDR في هذا النوع |
| `ipv6` | parsing عبر IPv6 value واحد؛ canonical compressed form |
| `cidr` | IPv4 أو IPv6 network canonical مع prefix؛ candidate IP يجب أن يقع داخله |
| `url` | scheme وhost وport وpath وquery canonical؛ exact match فقط، دون userinfo أو fragment |

لا توجد wildcard regex، ولا shell glob، ولا `startswith` عام. أي صيغة غير معروفة أو غامضة ترفع typed validation error قبل الوصول إلى persistence.

### 3.4 Scope lifecycle

```text
draft → validated → authorized → archived
draft → archived
validated → archived
```

لا يسمح الإصدار الأول بـ`authorized → validated` أو `archived → active` أو تعديل Target يؤثر في Scope authorized دون invalidation صريحة. المقترح الأكثر أمانًا هو أن أي إضافة أو أرشفة Target داخل Scope authorized تعيد Scope تلقائيًا إلى `validated` أو ترفض العملية حتى يقوم المستخدم بـrevalidate ثم reauthorize. أوصي بالخيار الثاني في أول تنفيذ: **لا تعديل على Scope authorized؛ أنشئ نسخة/Scope جديدة أو نفّذ أمرًا صريحًا يعيد الحالة إلى draft**. هذا القرار يحتاج اعتمادًا لأنه يؤثر في UX.

### 3.5 Typed results

يُنتج matcher كائن قرار immutable، وليس Boolean فقط:

```text
ScopeDecision
├── allowed: bool
├── scope_id: ScopeId
├── target_id: TargetId | None
├── canonical_candidate: str
├── reason_code: ALLOWED | EXPLICIT_EXCLUDE | NO_INCLUDE_MATCH |
│   SCOPE_NOT_AUTHORIZED | SCOPE_EXPIRED | SCOPE_ARCHIVED |
│   TARGET_ARCHIVED | INVALID_CANDIDATE
├── evaluated_at: aware UTC datetime
├── policy_version: str
└── correlation_id: CorrelationId
```

وعند `allowed=true` فقط تنشئ الطبقة application كائنًا أضيق من `ScopeDecision` اسمه `AuthorizedTarget`. أي Job/Action مستقبلي يستقبل هذا الكائن بدل `str` أو URL حر.

---

## 4. Scope Matcher Engine & Safety Guards

### 4.1 مكونات المحرك

| المكون | المسؤولية |
|---|---|
| CandidateParser | تحليل candidate إلى نوع وقيمة canonical دون network |
| TargetCanonicalizer | توحيد القيمة عند الإدخال وعند التقييم |
| TargetRuleMatcher | تنفيذ exact/FQDN/wildcard/IP/CIDR/URL semantics |
| ScopeSafetyPolicy | رفض القواعد واسعة الخطورة أو غير الصالحة |
| ScopeValidationService | فحص جميع Targets وتوليد validation report |
| AuthorizationGate | رفض أي قرار قبل authorized وexpiry checks |
| DecisionFactory | إنشاء ScopeDecision وAuthorizedTarget immutable |

### 4.2 خوارزمية المطابقة

لأي candidate يصل من طبقة مستقبلية، تكون العملية deterministic بالترتيب التالي:

1. يرفض النظام candidate الفارغ، غير القابل للتحليل، المحتوي على control characters، أو الذي لا يطابق نوعًا معروفًا.
2. يجري CandidateParser canonicalization محلية فقط. لا يتم حل اسم DNS ولا إرسال طلب HTTP.
3. يتحقق AuthorizationGate من أن Scope موجود، غير مؤرشف، حالته `authorized`، وأن `expires_at` غير منتهٍ.
4. يحمّل Targets ذات الحالة `active` فقط.
5. يبحث عن جميع قواعد `exclude` المطابقة. إذا وجد واحدة، يرجع `allowed=false` و`reason_code=EXPLICIT_EXCLUDE` دون النظر إلى نتيجة Include.
6. إذا لم يوجد Exclude مطابق، يبحث عن Include مطابق. وجود أي Include يرجع `allowed=true` مع Target المطابق الأكثر تحديدًا.
7. عند عدم وجود Include، يرجع `allowed=false` و`reason_code=NO_INCLUDE_MATCH`.
8. لا توجد نتيجة implicit allow. كل فشل parsing أو authorization هو deny.

### 4.3 أولوية المطابقة

أولوية القرار الأمنية هي `exclude > include > deny`. عند وجود عدة Includes، لا يغير ذلك القرار؛ ولغرض التقارير نختار الأكثر تحديدًا وفقًا للترتيب التالي: URL exact، FQDN exact، wildcard بأطول suffix، CIDR بأطول prefix، ثم IP exact. هذا الترتيب للتفسير وليس لتجاوز Exclude.

### 4.4 أمثلة سلوكية

| Include | Exclude | Candidate | النتيجة |
|---|---|---|---|
| `*.example.com` | لا يوجد | `api.example.com` | Allow |
| `*.example.com` | لا يوجد | `example.com` | Deny؛ wildcard لا يشمل apex |
| `*.example.com` | `admin.example.com` | `admin.example.com` | Deny؛ Explicit Exclude |
| `10.10.0.0/16` | `10.10.10.0/24` | `10.10.10.8` | Deny؛ Exclude wins |
| `10.10.0.0/16` | `10.10.10.0/24` | `10.10.20.8` | Allow |
| `https://app.example.com/login` | لا يوجد | `https://app.example.com/login` | Allow |
| `https://app.example.com/login` | لا يوجد | `https://app.example.com/login/next` | Deny؛ لا path-prefix implicit |

### 4.5 Safety guards

المحرك لا يسمح بالقواعد التالية في validation:

| الحالة | القرار المقترح |
|---|---|
| `0.0.0.0/0` أو `::/0` | رفض دائم |
| wildcard فارغ أو `*` أو `*.*` | رفض |
| wildcard على suffix غير صالح | رفض |
| Target value غير canonical | رفض قبل persistence |
| Scope بلا Include active | لا يمكن validate أو authorize |
| Scope authorized منتهٍ | deny حتى إعادة التفويض |
| Engagement archived | لا يمكن authorize أو execute |
| Target archived | لا يدخل matcher |
| Include/Exclude exact duplicate | يسمح به مع validation warning، وExclude يفوز |

أما حدود الاتساع مثل أقل prefix مسموح لشبكة داخلية، فأقترح جعلها policy versioned لا رقمًا مبعثرًا في الكود. القيم الافتراضية المقترحة هي منع `/0` دائمًا، مع تحذير أو رفض قابل للإعداد للشبكات الأوسع من `/16` في IPv4 أو `/48` في IPv6. لا يُثبت هذا القرار في التنفيذ قبل مراجعة المستخدم لأنه قد يمنع مختبرات أو بيئات مصرحًا بها واسعة.

---

## 5. Database Schema Design — Migration 0003

### 5.1 الجداول المقترحة

سيضيف `0003_target_scope.sql` جدولين فقط، ولا يعدل `0001` أو `0002`:

```sql
CREATE TABLE scopes (
    id TEXT PRIMARY KEY NOT NULL,
    engagement_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'validated', 'authorized', 'archived')),
    authorization_reference TEXT,
    validated_at TEXT,
    authorized_at TEXT,
    expires_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    FOREIGN KEY (engagement_id) REFERENCES engagements(id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CHECK (length(trim(name)) BETWEEN 1 AND 160),
    CHECK (length(description) <= 4000),
    CHECK (authorization_reference IS NULL
        OR length(trim(authorization_reference)) BETWEEN 1 AND 1000),
    CHECK (expires_at IS NULL OR authorized_at IS NULL OR expires_at > authorized_at),
    CHECK (
        (status = 'draft' AND validated_at IS NULL AND authorized_at IS NULL)
        OR (status = 'validated' AND validated_at IS NOT NULL AND authorized_at IS NULL)
        OR (status = 'authorized' AND validated_at IS NOT NULL
            AND authorized_at IS NOT NULL
            AND authorization_reference IS NOT NULL)
        OR (status = 'archived' AND archived_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX uq_scopes_engagement_name_nocase
    ON scopes (engagement_id, name COLLATE NOCASE);

CREATE INDEX idx_scopes_engagement_status
    ON scopes (engagement_id, status);

CREATE INDEX idx_scopes_created_at
    ON scopes (created_at);

CREATE TABLE targets (
    id TEXT PRIMARY KEY NOT NULL,
    scope_id TEXT NOT NULL,
    rule TEXT NOT NULL CHECK (rule IN ('include', 'exclude')),
    kind TEXT NOT NULL
        CHECK (kind IN ('fqdn', 'wildcard', 'ipv4', 'ipv6', 'cidr', 'url')),
    value TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    FOREIGN KEY (scope_id) REFERENCES scopes(id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CHECK (length(trim(value)) BETWEEN 1 AND 4096),
    CHECK (
        (status = 'active' AND archived_at IS NULL)
        OR (status = 'archived' AND archived_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX uq_targets_scope_rule_kind_value
    ON targets (scope_id, rule, kind, value);

CREATE INDEX idx_targets_scope_status_rule
    ON targets (scope_id, status, rule);

CREATE INDEX idx_targets_scope_kind
    ON targets (scope_id, kind);
```

### 5.2 Constraint matrix

| القاعدة | SQL | Domain | Application | الموقف |
|---|---:|---:|---:|---|
| UUID text non-null وPK | نعم | نعم | لا | both للتكامل والدقة |
| Engagement/Scope FK | نعم | نعم | نعم | both؛ يمنع orphan |
| ON DELETE/UPDATE RESTRICT | نعم | نعم | لا | حماية السجل |
| name/value length | نعم | نعم | لا | both |
| status/rule/kind enum | نعم | نعم | لا | both |
| archive timestamp invariant | نعم | نعم | لا | both |
| version >= 1 | نعم | نعم | لا | both |
| canonical target syntax | لا | نعم | نعم | لا يمكن لـSQLite فهم semantics كاملة |
| Scope يحتوي Include | لا | نعم | نعم | يعتمد على active child rows |
| Exclude overrides Include | لا | نعم | نعم | matcher policy |
| authorized يحتاج validation/reference | جزئي | نعم | نعم | transition rule لا constraint ثابت فقط |
| expiry أثناء التقييم | لا | نعم | نعم | يعتمد على current time |
| Engagement غير مؤرشف عند authorize | لا | نعم | نعم | cross-aggregate application guard |

### 5.3 Timestamp وversion representation

يستمر النظام في تخزين timestamps كنصوص UTC ISO-8601 canonical، وUUID كنص lowercase canonical، وversion كـpositive INTEGER. Mappers ترفض القيم غير القابلة للتحليل بدل إرجاع domain object ناقص.

### 5.4 Migration policy

الـMigration يجب أن يكون ملف SQL عاديًا دون `BEGIN` أو `COMMIT` داخليين ودون `IF NOT EXISTS`. يطبقه Migration Runner من Module 0.2 بعد 0002 داخل transaction واحدة، يسجل SHA-256 metadata، ويظل forward-only. لا يوجد downgrade تلقائي؛ rollback المقصود هو rollback للمعاملة عند الفشل قبل تسجيل migration، أما إزالة schema بعد تطبيق ناجح فتحتاج قرارًا إداريًا مستقلًا.

---

## 6. Foreign-Key وArchive Policy

العلاقة هي `engagements 1 → N scopes 1 → N targets`. نستخدم `ON DELETE RESTRICT` و`ON UPDATE RESTRICT` في المستويين. هذا ينسجم مع عدم وجود hard delete، ويمنع فقدان Scope أو Target بسبب حذف أب أعلى.

لا يكفي `ON DELETE RESTRICT` وحده لمنع التشغيل على بيانات مؤرشفة؛ لذلك تبقى guards في Domain وApplication وMatcher. عند أرشفة Engagement، لا يسمح التطبيق بإنشاء أو authorize Scope جديد داخله. وعند أرشفة Scope، يتوقف matcher عن إصدار AuthorizedTarget حتى لو بقيت Targets active في الصفوف التاريخية.

---

## 7. Repository Ports وPersistence Mapping

### 7.1 ScopeRepository

```text
add(scope) -> Scope
get(scope_id) -> Scope | None
list_by_engagement(engagement_id, include_archived=False) -> Sequence[Scope]
exists(scope_id) -> bool
update(scope, expected_version) -> Scope
archive(scope_id, expected_version, archived_at) -> Scope
```

لا يحتوي port على SQL أو `sqlite3.Row`. يعيد domain models فقط، ويترجم duplicate names إلى typed errors مثل `SCOPE_NAME_CONFLICT`، ويطبق optimistic concurrency كما في Module 0.3.

### 7.2 TargetRepository

```text
add(target) -> Target
get(target_id) -> Target | None
list_by_scope(scope_id, include_archived=False) -> Sequence[Target]
exists(target_id) -> bool
update(target, expected_version) -> Target
archive(target_id, expected_version, archived_at) -> Target
```

قبل `add` يجب أن يضمن Application Service وجود Scope active وقابلًا للتعديل، وأن يمرر Target عبر canonicalizer. Repository لا يعيد تفسير regex أو network rules؛ مسؤوليته persistence mapping وtransaction boundary فقط.

### 7.3 Mapping rules

يتم تحويل `ScopeId` و`TargetId` و`EngagementId` من وإلى UUID canonical، وتحويل status/rule/kind إلى enums typed، وتحويل timestamps مع تحقق UTC، وإخفاء أي SQLite exception خلف `PERSISTENCE_*` أو domain-specific typed error. لا يتسرب SQL أو row object إلى Service أو CLI.

---

## 8. Application Services

### ScopeService

يقترح أن يقدم `create`, `get`, `list`, `validate`, `authorize`, `archive`. عملية `validate` تحمل Scope وTargets داخل UnitOfWork، تشغل ScopeValidationService، وتثبت `validated_at` فقط إذا لم توجد أخطاء blocking. عملية `authorize` تعيد فحص validation ولا تثق بحالة مخزنة قديمة، وتتطلب `authorization_reference` وoptional `expires_at`، وتتحقق من أن Engagement غير مؤرشف.

### TargetService

يقترح أن يقدم `add`, `get`, `list`, `archive`. عملية `add` تنفذ parsing وcanonicalization وScope guard قبل repository، وتمنع تعديل Scope authorized وفق القرار المقترح. عملية `archive` لا تحذف الصف بل تزيد version وتضع `archived_at`.

### ScopeValidationService

هذا service هو pure/use-case boundary ولا ينفذ database writes أو network calls داخل matcher. يستقبل Scope وactive Targets و`ScopeSafetyPolicy`، ويرجع `ScopeValidationReport` يحتوي على errors وwarnings وnormalized target summaries. لا يكفي وجود report ناجح لتشغيل action؛ يجب بعدها transition صريح إلى `authorized`.

### AuthorizedTarget boundary

ستكون واجهة Job/Action المستقبلية مصممة لتقبل `AuthorizedTarget` فقط. لا يقبل أي adapter مستقبلي `candidate: str` مباشرة. إذا احتاج adapter إلى raw rendering، يحصل عليه من `AuthorizedTarget.canonical_candidate` بعد إنشاء القرار، مع correlation ID وpolicy version لأغراض التدقيق.

---

## 9. CLI Interface Design

الأوامر المقترحة لا تنفذ فحصًا شبكيًا. كل أمر يدعم `--json` ويعيد OperationResult نفسه من Module 0.1، مع correlation ID وtyped exit codes.

### Scope commands

```bash
cyberos scope create <engagement-id> "External API Scope" \
  --description "Approved boundary for the engagement"
cyberos scope list <engagement-id> [--include-archived] [--json]
cyberos scope show <scope-id> [--json]
cyberos scope validate <scope-id> [--json]
cyberos scope authorize <scope-id> \
  --authorization-reference "approval-2026-001" \
  [--expires-at <utc-iso>] [--expected-version N] [--json]
cyberos scope archive <scope-id> --expected-version N [--json]
cyberos scope evaluate <scope-id> <candidate> [--json]
```

`scope evaluate` read-only deterministic helper، ولا يجري network activity. يعرض `allowed`, `reason_code`, canonical candidate، target id المطابق إن وجد، وpolicy version.

### Target commands

```bash
cyberos target add <scope-id> \
  --rule include --kind fqdn --value api.example.com [--json]
cyberos target add <scope-id> \
  --rule exclude --kind fqdn --value admin.example.com [--json]
cyberos target list <scope-id> [--include-archived] [--json]
cyberos target show <target-id> [--json]
cyberos target archive <target-id> --expected-version N [--json]
```

المخرجات النصية تشرح القرار دون طباعة stack trace أو SQL. المخرجات JSON مستقرة ومناسبة للأتمتة، وتفصل بين validation errors وauthorization denials وconcurrency conflicts.

---

## 10. Error Taxonomy المقترحة

| Error code | متى يظهر |
|---|---|
| `SCOPE_NOT_FOUND` | Scope ID غير موجود |
| `SCOPE_NAME_CONFLICT` | اسم مكرر داخل Engagement |
| `SCOPE_ARCHIVED` | محاولة تعديل Scope مؤرشف |
| `SCOPE_NOT_VALIDATED` | authorize قبل نجاح validation |
| `SCOPE_NO_INCLUDE_RULE` | لا يوجد Include active |
| `SCOPE_AUTHORIZATION_REQUIRED` | reference فارغ عند authorize |
| `SCOPE_EXPIRED` | التقييم بعد expiry |
| `TARGET_NOT_FOUND` | Target ID غير موجود |
| `TARGET_VALUE_INVALID` | syntax أو canonicalization فاشلة |
| `TARGET_BROADNESS_REJECTED` | قاعدة واسعة أو خطرة |
| `TARGET_NAME_CONFLICT` | duplicate canonical target/rule/kind |
| `EXPLICIT_EXCLUDE` | قرار رفض أمني بسبب Exclude |
| `OUT_OF_SCOPE` | لا يوجد Include مطابق |
| `CONCURRENCY_CONFLICT` | expected version قديمة |
| `WORKSPACE_OR_ENGAGEMENT_ARCHIVED` | parent غير قابل للتشغيل |

قرار evaluate الرافض ليس exception داخليًا بالضرورة؛ يمكن إرجاع OperationResult ناجحًا من ناحية النقل مع `data.allowed=false`، بينما أخطاء الإدخال أو lifecycle تكون typed errors ذات exit code واضح. يجب تثبيت هذا distinction في implementation contract قبل CLI coding.

---

## 11. Test Plan

### Domain وcanonicalization

يجب اختبار UUID4 وUTC وtrim وlength وimmutable models، وقبول ورفض كل Target kind، canonicalization لـFQDN وwildcard وIPv4 وIPv6 وCIDR وURL، ورفض userinfo/control characters/empty values/ambiguous wildcard.

### Matcher

يجب اختبار exact FQDN، wildcard لا يشمل apex، CIDR boundaries، IPv4 مقابل IPv6، URL exactness، Include/Exclude precedence، no-include deny، archived target، archived/expired/unauthorized scope، وتعدد Includes مع اختيار الأكثر تحديدًا للتفسير.

### Schema وMigration

يجب اختبار 0003 ordering وchecksum وidempotency وatomic rollback وquick_check وforeign_key_check، وFK إلى Engagement وScope، `ON DELETE/UPDATE RESTRICT`، duplicate scope names، duplicate canonical targets، status/archive/version checks، وعدم وجود أي future tables.

### Repositories وServices

يجب اختبار round-trip كامل، deterministic listing، typed error translation، optimistic concurrency، UnitOfWork rollback، ومنع تعديل authorized Scope، ومنع إنشاء child تحت parent مؤرشف، وإعادة التحقق قبل authorize.

### Security boundary

يجب إثبات أن matcher لا يستدعي DNS أو HTTP أو subprocess، وأن CLI لا يحتوي SQL أو matching logic، وأن raw candidate لا يصل إلى Job/Action interface، وأن القرار يحمل reason code وpolicy version وcorrelation ID.

### CLI

يجب اختبار text/JSON output، validation failures، explicit excludes، expired authorization، ID غير موجود، duplicate rules، conflict version، deterministic ordering، وعدم تسريب SQL أو stack trace.

---

## 12. Phased Execution Plan

| الشريحة | النطاق | المخرجات | خارج النطاق |
|---|---|---|---|
| 0.4.a | Domain primitives وTarget canonicalization | IDs، enums، parsers، pure tests | SQLite وCLI |
| 0.4.b | Scope aggregate وlifecycle | Scope model، authorization transitions، tests | Migration |
| 0.4.c | Schema Design Review | مراجعة SQL وconstraint matrix | تنفيذ migration |
| 0.4.d | Migration 0003 | الجداول والقيود والفهارس والاختبارات | Repositories |
| 0.4.e | Scope/Target repositories | mappers، CRUD، concurrency، FK guards | Matcher orchestration |
| 0.4.f | Matcher وScopeValidationService | deterministic decisions، safety policy، tests | Network execution |
| 0.4.g | Application Services | create/validate/authorize/evaluate/archive | Web UI وHTTP API |
| 0.4.h | CLI integration وclosure | commands، regression، docs، checkpoint | Recon/scanners/jobs |

كل شريحة ستتبع المسار: تصميم/مراجعة عند الحاجة → تنفيذ محدود → unit/integration tests → Ruff/mypy/format/wheel → توثيق → checkpoint. لا يبدأ 0.4.d قبل اعتماد Schema Design Review، ولا يبدأ أي Job/Action قبل اكتمال authorization enforcement واختبارات bypass.

---

## 13. Compatibility وFuture Extension Points

يبقى `engagement_id` هو نقطة الربط الأساسية، ولذلك يمكن إضافة Scope دون تعديل Workspace أو Engagement schema. مستقبلًا يمكن أن ترتبط Jobs أو Scans بـ`scope_id` وبـ`authorized_target_id` أو Decision reference، لكن لا ينبغي إنشاء هذه الجداول داخل 0003.

إذا احتجنا لاحقًا asset discovery أو dynamic DNS، فيجب أن تكون نتائجهما طبقة منفصلة لا توسع matcher بصمت. وإذا احتجنا path-prefix أو port ranges أو cloud resource identifiers، فستكون Target kinds وpolicies جديدة مع migration واختبارات وتغيير versioned للـpolicy، لا parsing permissive.

---

## 14. Security Review Summary

التصميم fail-closed: لا authorization يعني لا execution، ولا Include يعني deny، وأي Exclude صريح يفوز، والـScope المنتهي أو المؤرشف لا ينتج AuthorizedTarget. لا يوجد network side effect في validation، ولا raw string boundary إلى الوحدات التنفيذية.

المخاطر المتبقية التي تحتاج قرارًا قبل التنفيذ هي دقة public-suffix validation للـwildcards، حدود broad CIDR، semantics URL exactness، وسياسة تعديل Scope بعد authorization. أوصي بتثبيت هذه النقاط في approval record قبل 0.4.a/0.4.c.

---

## 15. طلب الاعتماد

أطلب مراجعة واعتماد القرارات التالية قبل كتابة الكود:

1. اعتماد جدولي `scopes` و`targets` فقط في `0003_target_scope.sql`.
2. اعتماد lifecycle: `draft → validated → authorized → archived` مع deny خارج `authorized`.
3. اعتماد `exclude > include > deny`، ورفض no-include.
4. اعتماد Target kinds الستة وURL exact matching في الإصدار الأول.
5. اعتماد عدم تعديل Scope authorized مباشرة، أو اختيار سياسة بديلة صريحة.
6. اعتماد authorization reference وoptional expiry كشرطين للتفويض.
7. اعتماد تنفيذ الشرائح 0.4.a إلى 0.4.h بالترتيب، مع موافقة منفصلة قبل كل slice كبيرة.

بعد الاعتماد، ستكون الخطوة الأولى المقترحة هي **0.4.a — Domain Primitives & Target Canonicalization**، دون SQLite أو CLI أو أي network activity.

## References

هذه الوثيقة مواصفة داخلية لـCyberOS؛ القرارات الواردة فيها مقترحات معمارية تحتاج اعتماد المستخدم قبل التنفيذ. لا تعتمد على مصدر خارجي لتنفيذ أي عملية شبكية.
