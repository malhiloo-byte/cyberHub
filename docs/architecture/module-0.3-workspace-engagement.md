# CyberOS — Module 0.3

## Workspace & Engagement Domain Layer

**الحالة:** Module 0.3 مغلق؛ 0.3.a إلى 0.3.g منفّذة ومراجعة  
**الإصدار المقترح:** 0.3.0  
**يعتمد على:** Module 0.1 — Core Contracts وModule 0.2 — Persistence Kernel  
**نطاق الوثيقة:** أول Domain Layer فقط؛ لا تشمل Targets أو Findings أو Evidence أو Recon

---

## 1. الملخص التنفيذي

### حالة التنفيذ

تم تنفيذ وإغلاق **0.3.a** إلى **0.3.g** داخل `cyberos-core/`. تشمل النتيجة Domain Models، Migration 0002، mappers، repositories، Application Services، CLI، Cross-Layer Boundary Review، والتوثيق النهائي. لم تُنفذ HTTP API أو Web UI أو Scope أو execution features.

يضيف Module 0.3 أول كيانين لهما معنى عملي داخل CyberOS: **Workspace** لتنظيم مساحة عمل طويلة الأمد، و**Engagement** لتمثيل نشاط أو اختبار أو مختبر محدد داخل تلك المساحة.

التمييز بينهما مهم. الـWorkspace يعيش فترة طويلة ويجمع السياق والأنشطة المرتبطة بمسار تعلّم أو مشروع مهني. أما الـEngagement فهو وحدة عمل محددة يمكن أن تكون مختبرًا تعليميًا، أو تقييمًا مصرحًا، أو مشروعًا بحثيًا. ستصبح Targets وTasks وScans وFindings وEvidence لاحقًا أبناءً للـEngagement، لكن لن تدخل في هذا الموديول.

> Module 0.3 يثبت هوية ومجال العمل قبل أن نضيف أي قدرة Cybersecurity تنفيذية.

التصميم يحافظ على قواعد النواة السابقة: UUID4، timestamps واعية بتوقيت UTC، typed errors، migration forward-only مع SHA-256 checksum، UnitOfWork بمعاملة صريحة، Repository Ports مستقلة عن SQL، وSQLite محلية دون ORM.

---

## 2. النطاق والحدود

### ما يدخل في Module 0.3

| المجال | ما سيتم بناؤه |
|---|---|
| Workspace domain model | هوية المساحة واسمها ووصفها وحالتها وتواريخها وversion |
| Engagement domain model | هوية النشاط وعلاقته بـWorkspace وهدفه وحالته وفترته الزمنية وversion |
| Lifecycle | transitions واضحة للـWorkspace والـEngagement مع منع الحالات غير الصالحة |
| Database migration | `0002_workspace_engagement.sql` فوق `0001_persistence_kernel.sql` |
| Constraints | FK، uniqueness، status checks، timestamp checks، وoptimistic versioning groundwork |
| Repositories | WorkspaceRepository وEngagementRepository كـports وتنفيذ SQLite |
| Application services | عمليات الإنشاء والقراءة والقائمة والأرشفة وتغيير الحالة المسموح |
| CLI | أوامر `workspace` و`engagement` بمخرجات text/JSON مستقرة |
| Tests | Unit، migration، repository، service، CLI، وsecurity tests |

### ما لا يدخل في Module 0.3

لا يشمل هذا الموديول Target أو Scope أو Scan أو Job أو Task أو Finding أو Evidence أو Report أو Recon أو API HTTP أو Web UI أو authentication أو multi-user access control. كما لا يضيف hard delete افتراضيًا، ولا يضيف tags أو metadata JSON عامة قبل ظهور use case واضح لها.

هذا التضييق مقصود؛ فالهدف هو بناء أول vertical slice domain صغير يمكن اختباره وشرحه، وليس إنشاء schema عامة لكل المستقبل دفعة واحدة.

---

## 3. المصطلحات والعلاقة بين الكيانات

```text
Workspace
  └── Engagement (one-to-many)
        ├── Targets       # Module لاحق
        ├── Tasks         # Module لاحق
        ├── Scans         # Module لاحق
        ├── Findings      # Module لاحق
        └── Evidence      # Module لاحق
```

### Workspace

يمثل مساحة تنظيمية طويلة الأمد، مثل `Web Pentest Learning` أو `AI Security Research`. يمكن أن تحتوي المساحة على Engagements متعددة. لا تُحذف عادةً؛ تُؤرشف.

### Engagement

يمثل نشاطًا أو اختبارًا أو مختبرًا محددًا داخل Workspace، مثل `DVWA Practice — Week 1` أو `Authorized API Assessment — Client A`. لا يكون Engagement بلا Workspace.

### نوع Engagement وauthorization

لدعم مسار المستخدم دون تحويل Module 0.3 إلى نظام authorization كامل، نستخدم `kind` محدودًا:

| kind | الاستخدام |
|---|---|
| `learning` | مختبر أو تدريب أو مشروع تعليمي |
| `authorized_assessment` | تقييم أمني مصرح به |
| `research` | بحث أو تجربة تحليلية غير تشغيلية |

يوجد حقل `authorization_reference` نصي اختياري من حيث schema، لكنه يصبح مطلوبًا قبل نقل `authorized_assessment` إلى الحالة `active`. هذا الحقل ليس secret vault ولا إثباتًا قانونيًا؛ هو مرجع أو وصف يذكّر المستخدم بأساس التصريح دون تخزين مستند حساس داخل قاعدة البيانات.

---

## 4. Domain Models

### 4.1 قواعد مشتركة

كل model يستخدم `ConfigDict(extra="forbid", frozen=True)` حتى لا تدخل حقول غير معروفة بصمت. يتم إنشاء ID بواسطة `new_id()` من Module 0.1، ويجب أن يكون UUID4. التواريخ الداخلية هي timezone-aware UTC، ويُرفض `datetime` غير المرتبط بمنطقة زمنية. الـpersistence mapper يحولها إلى ISO-8601 نصي.

الأسماء تُنظف من المسافات المحيطة وتُرفض إذا كانت فارغة. لا نستخدم slug مستقلًا في الإصدار الأول؛ الاسم هو واجهة المستخدم الأساسية، وتُفرض uniqueness غير الحساسة لحالة الأحرف على مستوى قاعدة البيانات.

### 4.2 Workspace

```text
Workspace
├── id: UUID4
├── name: str, 1..120 بعد trim
├── description: str, 0..4000
├── status: WorkspaceStatus = active | archived
├── created_at: aware UTC datetime
├── updated_at: aware UTC datetime
├── archived_at: aware UTC datetime | None
└── version: positive int, default 1
```

قواعد المجال:

1. `archived` يتطلب `archived_at`.
2. `active` لا يحمل `archived_at`.
3. لا يمكن أرشفة Workspace مرتين كعملية تغيّر حالة؛ يمكن للخدمة التعامل مع الطلب المتكرر كـidempotent read أو إرجاع typed state error، والقرار النهائي يثبت في implementation contract.
4. لا يمكن إعادة Workspace المؤرشف إلى `active` في الإصدار الأول دون أمر صريح مستقل؛ الأفضل عدم إضافة restore قبل ظهور use case.
5. `version` لا يقل عن 1 ويزداد عند كل تحديث domain.

### 4.3 Engagement

```text
Engagement
├── id: UUID4
├── workspace_id: UUID4
├── name: str, 1..160 بعد trim
├── kind: learning | authorized_assessment | research
├── status: draft | active | paused | completed | archived
├── description: str, 0..4000
├── authorization_reference: str | None, max 1000
├── start_at: aware UTC datetime | None
├── end_at: aware UTC datetime | None
├── created_at: aware UTC datetime
├── updated_at: aware UTC datetime
├── archived_at: aware UTC datetime | None
└── version: positive int, default 1
```

قواعد المجال:

1. `workspace_id` مطلوب ولا يمكن تغييره عبر update عادي.
2. `end_at` لا يسبق `start_at` عندما يكون كلاهما موجودًا.
3. `active` يحتاج Workspace غير مؤرشف.
4. `authorized_assessment` يحتاج `authorization_reference` غير فارغ عند الانتقال إلى `active`.
5. `completed` يحتاج `end_at`؛ ويمكن للخدمة وضعه تلقائيًا إلى UTC الآن عند تنفيذ transition صريح، لكن هذا القرار يثبت في implementation قبل الكود.
6. `archived` يحتاج `archived_at`، ولا يمكن أن يكون له children مستقبلية جديدة.
7. transitions غير المسموحة ترفع `ENGAGEMENT_INVALID_TRANSITION` بدل تعديل الحالة جزئيًا.

### Engagement status transitions

```text
draft → active
draft → archived
active → paused
active → completed
active → archived
paused → active
paused → completed
paused → archived
completed → archived
```

لا نسمح بـ`completed → active` أو `archived → active` في الإصدار الأول. إذا احتجنا reopen لاحقًا، نضيف transition موثقًا وmigration/اختبارات، ولا نفتحها كأثر جانبي.

---

## 5. Database Schema

### 5.1 الجداول

سيضيف `0002_workspace_engagement.sql` جدولين فقط:

```sql
CREATE TABLE workspaces (
    id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL COLLATE NOCASE,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    CHECK (length(trim(name)) BETWEEN 1 AND 120),
    CHECK (
        (status = 'active' AND archived_at IS NULL)
        OR (status = 'archived' AND archived_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX uq_workspaces_name_nocase
    ON workspaces (name COLLATE NOCASE);

CREATE TABLE engagements (
    id TEXT PRIMARY KEY NOT NULL,
    workspace_id TEXT NOT NULL,
    name TEXT NOT NULL COLLATE NOCASE,
    kind TEXT NOT NULL
        CHECK (kind IN ('learning', 'authorized_assessment', 'research')),
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'active', 'paused', 'completed', 'archived')),
    description TEXT NOT NULL DEFAULT '',
    authorization_reference TEXT,
    start_at TEXT,
    end_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE RESTRICT,
    CHECK (length(trim(name)) BETWEEN 1 AND 160),
    CHECK (length(description) <= 4000),
    CHECK (authorization_reference IS NULL OR length(authorization_reference) <= 1000),
    CHECK (end_at IS NULL OR start_at IS NULL OR end_at >= start_at),
    CHECK (
        (status != 'archived' AND archived_at IS NULL)
        OR (status = 'archived' AND archived_at IS NOT NULL)
    )
);

CREATE INDEX idx_engagements_workspace_id
    ON engagements (workspace_id);

CREATE INDEX idx_engagements_status
    ON engagements (status);

CREATE INDEX idx_engagements_created_at
    ON engagements (created_at);
```

### 5.2 ملاحظة حول القيود العابرة للحقول

بعض القواعد لا ينبغي وضعها في SQLite وحدها. مثلًا، شرط أن `authorized_assessment` يحتاج authorization reference عند التفعيل يعتمد على transition، لا على مجرد وجود صف. لذلك تكون القاعدة في Domain Model وApplication Service، بينما تظل قاعدة البيانات حارسة للأنواع، الأطوال، العلاقات، وحالة archive الأساسية.

### 5.3 العلاقات وCascade Policy

العلاقة هي Workspace واحد إلى Engagements متعددة. نستخدم `ON DELETE RESTRICT` بدل cascade delete. لا توجد أوامر hard delete في CLI ضمن Module 0.3؛ الأرشفة هي السياسة الافتراضية لحماية السجل التاريخي. إذا احتجنا حذفًا لاحقًا، سيكون أمرًا إداريًا منفصلًا مع confirmation وpreflight على children.

### 5.4 ID وtimestamp storage

يخزن UUID كنص canonical lowercase، ويخزن الوقت كنص UTC ISO-8601. لا تخزن SQLite timezone object مباشرة. الـmapper مسؤول عن validation عند القراءة، وأي قيمة غير صالحة ترفع `DOMAIN_DATA_INVALID` أو `PERSISTENCE_MAPPING_FAILED` بدل إرجاع model ناقص.

### 5.5 Optimistic versioning

وجود `version` في الجدولين من البداية يهيئ لتعارض التحديث بين أوامر CLI أو واجهة لاحقة. لا نحتاج الآن إلى concurrency server، لكن update repository يستخدم:

```sql
UPDATE workspaces
SET name = ?, description = ?, updated_at = ?, version = version + 1
WHERE id = ? AND version = ?;
```

إذا كان عدد الصفوف المتأثرة صفرًا، نميز بين `WORKSPACE_NOT_FOUND` و`CONCURRENCY_CONFLICT` عبر قراءة وجود ID أو استخدام نتيجة update policy موحدة.

---

## 6. Migration 0002 Compatibility

ملف `0002_workspace_engagement.sql` يجب أن يكون SQL migration عاديًا دون `BEGIN` أو `COMMIT` داخليين؛ لأن Migration Runner من Module 0.2 يملك المعاملة الذرية. يجب أن:

1. يطبق بعد `0001_persistence_kernel.sql` فقط.
2. يستخدم أسماء version صحيحة ومتسلسلة.
3. لا يعدل `schema_migrations` يدويًا؛ runner يسجل metadata.
4. لا يضيف Domain Tables أخرى غير الجدولين المحددين.
5. يحافظ على SHA-256 checksum الثابت للملف.
6. يفشل بالكامل إذا تعذر إنشاء أي constraint أو index.
7. لا يحتوي على بيانات seed أو أمثلة شخصية.

Migration ليس لها downgrade تلقائي. التراجع يكون عبر backup/restore أو migration forward جديدة، وفق سياسة Module 0.2.

---

## 7. Repository Interfaces

لن نعتمد Generic CRUD فقط؛ لأن كل كيان يحتاج استعلامات وسياسات مختلفة. نعرف ports domain-specific فوق `UnitOfWorkPort`.

### WorkspaceRepository

```python
class WorkspaceRepository(Protocol):
    def add(self, workspace: Workspace) -> Workspace: ...
    def get(self, workspace_id: UUID) -> Workspace | None: ...
    def list(self, *, status: WorkspaceStatus | None = None) -> Sequence[Workspace]: ...
    def update(self, workspace: Workspace, *, expected_version: int) -> Workspace: ...
    def archive(self, workspace_id: UUID, *, expected_version: int) -> Workspace: ...
    def exists(self, workspace_id: UUID) -> bool: ...
```

قائمة Workspace مرتبة افتراضيًا بـ`created_at DESC, id ASC` حتى تكون النتيجة deterministic. الاسم uniqueness غير حساس لحالة الأحرف، وتحوّل مخالفة unique إلى `WORKSPACE_NAME_CONFLICT`.

### EngagementRepository

```python
class EngagementRepository(Protocol):
    def add(self, engagement: Engagement) -> Engagement: ...
    def get(self, engagement_id: UUID) -> Engagement | None: ...
    def list_by_workspace(
        self,
        workspace_id: UUID,
        *,
        status: EngagementStatus | None = None,
    ) -> Sequence[Engagement]: ...
    def update(self, engagement: Engagement, *, expected_version: int) -> Engagement: ...
    def transition(
        self,
        engagement_id: UUID,
        target_status: EngagementStatus,
        *,
        expected_version: int,
        updated_at: datetime,
    ) -> Engagement: ...
    def archive(self, engagement_id: UUID, *, expected_version: int) -> Engagement: ...
```

لا يقبل repository SQL أو table names من CLI أو المستخدم. كل values تمرر كـparameters، وكل identifier يأتي من internal mapping ثابت.

### Repository error mapping

| الحالة | الخطأ المقترح |
|---|---|
| Workspace غير موجود | `WORKSPACE_NOT_FOUND` |
| Engagement غير موجود | `ENGAGEMENT_NOT_FOUND` |
| اسم Workspace مكرر | `WORKSPACE_NAME_CONFLICT` |
| Workspace الأب غير موجود | `WORKSPACE_NOT_FOUND` |
| Workspace مؤرشف مع إنشاء Engagement | `WORKSPACE_ARCHIVED` |
| update version قديمة | `CONCURRENCY_CONFLICT` |
| SQLite FK/unique/check failure | typed domain persistence error، دون raw SQL للمستخدم |

---

## 8. Application Services

نضع business decisions في services، لا في CLI ولا داخل repository.

### WorkspaceService

العمليات الأولى:

```text
create_workspace(name, description) → Workspace
list_workspaces(status?) → Sequence[Workspace]
get_workspace(id) → Workspace
archive_workspace(id, expected_version) → Workspace
```

`create_workspace` ينشئ UUID4 وUTC timestamps وversion=1. `archive_workspace` يتحقق من الحالة الحالية ثم يكتب `archived_at` وversion increment داخل UnitOfWork.

### EngagementService

العمليات الأولى:

```text
create_engagement(workspace_id, name, kind, description, authorization_reference?) → Engagement
list_engagements(workspace_id, status?) → Sequence[Engagement]
get_engagement(id) → Engagement
transition_engagement(id, target_status, expected_version) → Engagement
archive_engagement(id, expected_version) → Engagement
```

عند إنشاء Engagement، يتأكد service من وجود Workspace وأنه active. عند `draft → active` يتأكد من authorization reference إذا كان النوع `authorized_assessment`. عند `completed` يثبت `end_at` إن كانت policy المعتمدة تسمح بذلك؛ وإلا يرفض الطلب إذا لم يرسل service timestamp صريحًا. نحتاج اعتماد هذا التفصيل قبل التنفيذ.

### Transaction policy

كل command service يفتح UnitOfWork واحدة. القراءة القائمة فقط يمكن أن تستخدم connection مباشرة عبر read service، لكن الإصدار الأول يوحدها داخل UnitOfWork لضمان lifecycle واضح. لا توجد معاملات موزعة بين Workspace وEngagement؛ إنشاء Engagement لا ينشئ Workspace ضمنيًا.

---

## 9. CLI Design

### Workspace commands

```text
cyberos workspace create --name "Web Pentest Learning" \
  --description "Long-term web security learning workspace"

cyberos workspace list
cyberos workspace list --status active
cyberos workspace show <workspace-id>
cyberos workspace archive <workspace-id> --expected-version 1
```

### Engagement commands

```text
cyberos engagement create \
  --workspace-id <workspace-id> \
  --name "DVWA Practice" \
  --kind learning

cyberos engagement list --workspace-id <workspace-id>
cyberos engagement list --workspace-id <workspace-id> --status active
cyberos engagement show <engagement-id>
cyberos engagement transition <engagement-id> active --expected-version 1
cyberos engagement archive <engagement-id> --expected-version 2
```

كل أمر يدعم `--json`، ويعيد OperationResult envelope من Module 0.1. النص البشري يعرض الحقول الأساسية فقط، بينما JSON يعرض ID وstatus وtimestamps وversion. لا نضع description كاملًا في list إلا مع خيار صريح حتى تبقى النتائج قابلة للقراءة.

### CLI failure behavior

| الحالة | السلوك |
|---|---|
| ID غير صالح | `INVALID_INPUT` مع exit code معروف |
| ID صالح لكن غير موجود | `WORKSPACE_NOT_FOUND` أو `ENGAGEMENT_NOT_FOUND` |
| اسم مكرر | `WORKSPACE_NAME_CONFLICT` |
| transition غير مسموح | `ENGAGEMENT_INVALID_TRANSITION` |
| version قديمة | `CONCURRENCY_CONFLICT` |
| قاعدة غير مهيأة | `DATABASE_NOT_INITIALIZED` أو health failure واضح |

لا تعرض CLI stack trace افتراضيًا. correlation ID يظهر في JSON meta ويسجل في logs.

---

## 10. Testing Strategy

### Unit tests

تختبر models وservices دون SQLite قدر الإمكان:

1. قبول UUID4 ورفض ID غير الصحيح.
2. رفض naive datetime.
3. trim وlength validation للأسماء والوصف.
4. Workspace status invariants وarchive timestamps.
5. Engagement kind/status validation.
6. كل transition مسموح وكل transition مرفوض.
7. منع تفعيل authorized assessment بلا authorization reference.
8. منع end قبل start.
9. version increment وتعارض expected version.

### Migration tests

تستخدم قاعدة مؤقتة وتتحقق من:

1. تطبيق 0001 ثم 0002 بالترتيب.
2. checksum metadata للـ0002.
3. وجود الجدولين والفهارس فقط ضمن نطاق الموديول.
4. وجود FK فعال من Engagement إلى Workspace.
5. رفض migration gap أو checksum mismatch.
6. عدم وجود أي Target أو Finding أو Evidence table.

### Repository integration tests

تغطي:

1. Workspace add/get/list/archive.
2. uniqueness غير الحساسة لحالة الأحرف.
3. Engagement add/get/list_by_workspace.
4. منع Engagement تحت Workspace مؤرشف.
5. FK failure عند workspace غير موجود.
6. update optimistic version success وconflict.
7. transition state persisted مع UTC timestamps.
8. rollback عند فشل command.
9. عدم تسرب `sqlite3.Row` إلى domain model.

### Service tests

تستخدم fake repositories وfake UnitOfWork لتثبت أن القرارات domain في service وليست في CLI. تشمل إنشاء Workspace، إنشاء Engagement، archive، transition، errors، وcommit/rollback calls.

### CLI tests

تتحقق من الأوامر text وJSON، بما في ذلك:

1. create يعيد ID وversion.
2. list يرتب النتائج deterministic.
3. show لعنصر غير موجود.
4. archive يحتاج expected version.
5. transition غير مسموح.
6. JSON صالح في النجاح والفشل.
7. لا تظهر raw SQL أو stack trace أو secrets.

### Security tests

يجب أن تثبت الاختبارات أن الاسم الذي يحتوي SQL-like text لا يغير schema، وأن القيم تستخدم parameters، وأن إنشاء Engagement لا يتجاوز Workspace archived policy، وأنه لا توجد network/subprocess capabilities في Module 0.3.

---

## 11. Security وPrivacy Model

Module 0.3 يخزن تنظيمًا وسياقًا فقط. لا يجب تخزين كلمات مرور أو API keys أو tokens أو أدلة حساسة في description أو authorization reference. نضيف redaction عند logging، ونرفض طباعة environment أو SQL.

الأرشفة بدل الحذف تحمي التاريخ، لكن لا تعني immutable audit log كاملًا. إذا أصبح audit requirement مهمًا، نضيف Audit Trail module مستقلًا بدل حشو Workspace schema.

لا يعتبر `authorization_reference` إثبات تفويض فعليًا. هو تذكير منظم للمستخدم، ويجب أن تبقى مسؤولية التأكد من نطاق التصريح خارج النظام حتى نبني Scope module مخصصًا.

---

## 12. خطة التنفيذ المرحلية

لن ننفذ Module 0.3 دفعة واحدة. الخطة المقترحة:

```text
0.3.a — Domain primitives + Workspace model
  → 0.3.b — Engagement model + lifecycle rules
    → 0.3.c — Migration 0002 + schema constraints
      → 0.3.d — WorkspaceRepository + service + CLI
        → 0.3.e — EngagementRepository + service + CLI
          → 0.3.f — Contract/integration/CLI/security tests
            → 0.3.g — Documentation + final quality gate + checkpoint
```

### 0.3.a

نبدأ بـWorkspace فقط، ونثبت naming وtimestamps وstatus وarchive وversion، مع unit tests. لا Engagement بعد إذا أردنا أصغر vertical slice ممكن.

### 0.3.b

نضيف Engagement model وtransition matrix وauthorization guard كمنطق domain مستقل، دون SQL أولًا.

### 0.3.c

نكتب 0002 بعد تثبيت model decisions. نطبق migration على قاعدة temporary ونتحقق من FK وindexes وCHECKs وعدم وجود domain tables أخرى.

### 0.3.d و0.3.e

ننفذ كل repository/service/CLI في slice منفصلة حتى تكون Workspace قابلة للاستخدام قبل Engagement، ثم نضيف Engagement فوقها.

### 0.3.f و0.3.g

نغلق الاختبارات والتوثيق وquality gates وننشئ checkpoint. لا ننتقل إلى Targets قبل اعتماد النتيجة.

---

## 13. Definition of Done لـModule 0.3

يُعتبر الموديول مكتملًا عند تحقق الآتي:

1. Domain Models immutable ومتحققة بـUUID4 وUTC.
2. Workspace وEngagement lifecycle موثق ومختبر.
3. Migration 0002 تعمل فوق 0001 مع checksum صحيح.
4. الجداول والقيود والعلاقات والفهارس مطابقة للتصميم.
5. Repository implementations تستخدم UnitOfWork وparameterized SQL.
6. Services تحتوي قرارات المجال ولا يحتوي CLI business logic.
7. أوامر workspace وengagement تعمل text وJSON.
8. اختبارات unit/integration/CLI/security ناجحة.
9. لا توجد Domain Tables مستقبلية خارج Workspace وEngagement.
10. لا توجد network/subprocess أو secrets في هذه الوحدة.
11. README وADRs وdevelopment docs محدثة.
12. quality gates وwheel build ناجحة.
13. checkpoint منفصل محفوظ قبل الانتقال إلى Module 0.4.

---

## 14. قرارات تحتاج اعتمادًا قبل التنفيذ

| القرار | المقترح |
|---|---|
| Workspace status | `active` و`archived` فقط |
| Engagement kinds | `learning` و`authorized_assessment` و`research` |
| Engagement statuses | `draft` و`active` و`paused` و`completed` و`archived` |
| Delete policy | لا hard delete؛ `ON DELETE RESTRICT` وarchive |
| Uniqueness | Workspace names unique case-insensitively؛ Engagement names يمكن تكرارها بين Workspaces |
| Versioning | optimistic `version` يبدأ من 1 ويزداد مع update/transition |
| Authorization | `authorization_reference` مطلوب قبل تفعيل authorized assessment، لكنه ليس secret storage أو legal proof |
| Migration | `0002_workspace_engagement.sql`، forward-only، دون BEGIN/COMMIT داخليين |
| CLI | workspace وengagement commands مع `--json` وexpected-version للكتابة المتزامنة |
| Implementation order | Workspace model أولًا، ثم Engagement، ثم schema، repositories، services، CLI، tests |

بعد اعتمادك لهذه الوثيقة، أقترح أن نبدأ بـ**0.3.a — Domain Primitives + Workspace Model** فقط، ثم نرجع بنتائج اختبارها قبل الانتقال إلى Engagement.

---

## References

هذه الوثيقة تمثل تصميمًا مقترحًا خاصًا بمشروع CyberOS، مبنيًا على عقود Module 0.1 وPersistence Kernel Module 0.2، وتحتاج اعتماد صاحب المشروع قبل التنفيذ.
