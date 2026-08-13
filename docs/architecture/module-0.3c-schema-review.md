# CyberOS — Module 0.3.c

## Schema Design Review: Workspace + Engagement

**الحالة:** التصميم معتمد والتنفيذ مكتمل؛ Migration 0002 منفذة ومختبرة  
**المرجع المعتمد:** `bb49cdd3` — Module 0.3.b  
**النطاق:** جدول `workspaces` وجدول `engagements` فقط  
**خارج النطاق:** Target، Scope، Finding، Evidence، Scan، Job، Report

---

## 1. قرار الحدود

بدأت هذه الوثيقة كمراجعة تصميم فقط. بعد اعتمادها وقرار unique composite، نُفذت `0002_workspace_engagement.sql` واختُبرت فوق baseline دون تعديل 0001. توثيق التنفيذ التفصيلي موجود في `docs/development/schema-0.3c.md`.

العلاقة الحالية المقترحة هي:

```text
workspaces (1)
    │
    └── engagements (many)
```

لا نضع Targets أو Findings أو Evidence أو Scans داخل Workspace مباشرة. العلاقات المستقبلية ستشير إلى `engagements.id`، بحيث يصبح المسار المنطقي:

```text
Workspace
  └── Engagement
       ├── Scope
       ├── Targets
       ├── Tasks / Jobs
       ├── Scans
       ├── Findings
       ├── Evidence
       └── Reports
```

لن نضع أعمدة أو جداول placeholder لهذه الكيانات المستقبلية. يكفي أن يكون `engagements.id` ثابتًا ومناسبًا كمفتاح أجنبي لاحقًا.

---

## 2. A — Proposed Schema

### 2.1 تمثيل المفاتيح والأنواع

| العنصر | التمثيل المقترح | السبب |
|---|---|---|
| UUID4 IDs | `TEXT` canonical UUID string بطول 36 | متوافق مع Domain UUID4، قابل للفحص يدويًا، ولا يحتاج adapter binary الآن |
| Workspace PK | `id TEXT PRIMARY KEY` | هوية ثابتة لا تتغير |
| Engagement PK | `id TEXT PRIMARY KEY` | هوية ثابتة لا تتغير |
| Workspace FK | `workspace_id TEXT NOT NULL` | Engagement لا يعيش دون Workspace |
| Timestamp | `TEXT NOT NULL` أو nullable | ISO-8601 UTC ناتج من `ensure_utc().isoformat()` |
| Version | `INTEGER NOT NULL DEFAULT 1` | optimistic concurrency متوافق مع Domain Model |
| Status | `TEXT` مع `CHECK` allowlist | يسهل القراءة ويحمي القيم غير المعروفة |
| EngagementKind | `TEXT` مع `CHECK` allowlist | يطابق `EngagementKind` بدون numeric enum coupling |
| Authorization reference | `TEXT NULL` بحد أقصى 1000 | مرجع تنظيمي، وليس secret أو proof of authorization |

### 2.2 جدول Workspace المقترح

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
    version INTEGER NOT NULL DEFAULT 1
        CHECK (version >= 1),
    CHECK (length(trim(id)) = 36),
    CHECK (length(trim(name)) BETWEEN 1 AND 120),
    CHECK (length(description) <= 4000),
    CHECK (length(trim(created_at)) > 0),
    CHECK (length(trim(updated_at)) > 0),
    CHECK (
        (status = 'active' AND archived_at IS NULL)
        OR
        (status = 'archived' AND archived_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX uq_workspaces_name_nocase
    ON workspaces (name COLLATE NOCASE);
```

### 2.3 جدول Engagement المقترح

```sql
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
    version INTEGER NOT NULL DEFAULT 1
        CHECK (version >= 1),
    FOREIGN KEY (workspace_id)
        REFERENCES workspaces(id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT,
    CHECK (length(trim(id)) = 36),
    CHECK (length(trim(workspace_id)) = 36),
    CHECK (length(trim(name)) BETWEEN 1 AND 160),
    CHECK (length(description) <= 4000),
    CHECK (
        authorization_reference IS NULL
        OR length(authorization_reference) <= 1000
    ),
    CHECK (
        start_at IS NULL
        OR end_at IS NULL
        OR end_at >= start_at
    ),
    CHECK (length(trim(created_at)) > 0),
    CHECK (length(trim(updated_at)) > 0),
    CHECK (
        (status <> 'archived' AND archived_at IS NULL)
        OR
        (status = 'archived' AND archived_at IS NOT NULL)
    ),
    CHECK (
        NOT (
            kind = 'authorized_assessment'
            AND status = 'active'
            AND length(trim(coalesce(authorization_reference, ''))) = 0
        )
    ),
    CHECK (status <> 'completed' OR end_at IS NOT NULL)
);

CREATE INDEX idx_engagements_workspace_id
    ON engagements (workspace_id);

CREATE INDEX idx_engagements_workspace_status
    ON engagements (workspace_id, status);

CREATE INDEX idx_engagements_created_at
    ON engagements (created_at);
```

### 2.4 قرار معتمد: Engagement name uniqueness

التصميم الأساسي لا يحتاج إلى uniqueness عام لاسم Engagement؛ يمكن أن يتكرر الاسم بين Workspaces. يوجد قراران ممكنان داخل Workspace نفسه:

| البديل | الأثر |
|---|---|
| A — لا uniqueness لـEngagement name | مرونة أعلى، لكن قد توجد Engagements متشابهة جدًا في Workspace واحد |
| B — `UNIQUE(workspace_id, name COLLATE NOCASE)` | يمنع الغموض في CLI، لكنه يمنع تكرار اسم مشروع عبر نسخ أو دورات مختلفة |

**القرار المعتمد:** البديل B، عبر `UNIQUE(workspace_id, name COLLATE NOCASE)`. يبقى UUID الهوية التقنية الأساسية، بينما يمنع القيد الغموض البشري داخل Workspace.

تمت إضافة unique composite في التنفيذ باسم `uq_engagements_workspace_name_nocase`.

---

## 3. B — Constraint Matrix

### 3.1 Workspace constraints

| القيد | SQL | Domain | القرار |
|---|---:|---:|---|
| `id` غير فارغ وبطول 36 | نعم | نعم UUID4/version | كلاهما، مع Domain كمرجع UUID الحقيقي |
| `name` غير فارغ، 1–120 | نعم | نعم مع trim | كلاهما للدفاع العميق |
| `description` بحد 4000 | نعم | نعم مع trim | كلاهما |
| status allowlist | نعم | نعم enum | كلاهما |
| active لا يملك `archived_at` | نعم | نعم | كلاهما |
| archived يملك `archived_at` | نعم | نعم | كلاهما |
| timestamps غير فارغة | نعم | نعم UTC-aware | كلاهما، SQL لا يثبت timezone بالكامل |
| version >= 1 | نعم | نعم | كلاهما |
| name uniqueness | index unique مقترح | Service mapping | كلاهما؛ SQL يمنع race conditions |

### 3.2 Engagement constraints

| القيد | SQL | Domain | القرار |
|---|---:|---:|---|
| `id` UUID string غير فارغ | نعم جزئيًا | نعم UUID4 | كلاهما |
| `workspace_id` غير فارغ | نعم | نعم typed `WorkspaceId` | كلاهما |
| Workspace الأب موجود | FK | Service/repository lookup | كلاهما |
| name 1–160 | نعم | نعم مع trim | كلاهما |
| description <= 4000 | نعم | نعم | كلاهما |
| kind allowlist | نعم | نعم enum | كلاهما |
| status allowlist | نعم | نعم enum | كلاهما |
| `start_at <= end_at` | نعم بشرط canonical UTC text | نعم بقوة | كلاهما، Domain هو المرجع الزمني |
| archived invariant | نعم | نعم | كلاهما |
| authorized active يحتاج reference | نعم | نعم transition guard | كلاهما |
| completed يحتاج `end_at` | نعم | نعم transition guard | كلاهما |
| version >= 1 | نعم | نعم | كلاهما |
| allowed transitions | لا | نعم فقط | Domain فقط؛ SQL لا يمثل state machine كاملة |
| Scope authorization | لا | لاحقًا Scope Domain | خارج 0.3.c |

### 3.3 لماذا نكرر بعض القيود؟

التكرار هنا مقصود كـdefense in depth. Domain Model يمنع الحالات غير الصحيحة في الذاكرة ويوفر typed errors مفهومة، بينما SQL يمنع corruption الناتج عن bug أو import أو future adapter يتجاوز service. لكن SQL لا يحل محل lifecycle Domain؛ لا يجب أن تتحول repository إلى مكان يقرر transitions.

---

## 4. C — Index Plan

| الفهرس | الغرض | ضروري الآن؟ |
|---|---|---:|
| `uq_workspaces_name_nocase` | منع duplicate Workspace names وتحسين lookup بالاسم | نعم إذا اعتمدنا uniqueness |
| `idx_engagements_workspace_id` | list Engagements داخل Workspace | نعم |
| `idx_engagements_workspace_status` | list حسب Workspace وstatus | نعم؛ يغطي query متوقعًا |
| `idx_engagements_created_at` | ترتيب أو timeline عام | اختياري، التوصية إبقاؤه الآن لرخصه |
| فهرس `engagements.name` | بحث بالاسم | لا، لا يوجد command بحث بعد |
| فهارس Target/Scope/Findings | مستقبلية | ممنوعة الآن |

إذا اعتمدنا composite uniqueness لEngagement، يصبح فهرس `UNIQUE(workspace_id, name COLLATE NOCASE)` مفيدًا للهوية البشرية وللاستعلامات داخل Workspace، ويمكن أن يغطي جزءًا من `workspace_id`، لكن لا نعتبر ذلك سببًا لإضافة القرار دون موافقة.

---

## 5. D — Foreign-Key وDelete Policy

### السياسة الحالية

نستخدم:

```sql
FOREIGN KEY (workspace_id)
REFERENCES workspaces(id)
ON DELETE RESTRICT
ON UPDATE RESTRICT
```

مع تفعيل `PRAGMA foreign_keys = ON` من Connection Factory في كل اتصال. وجود النص في schema وحده لا يكفي؛ SQLite يتطلب enforcement على مستوى كل connection، ولذلك يجب أن يكون فحص PRAGMA جزءًا من اختبارات migration وhealth.

### هل `ON DELETE RESTRICT` كافٍ؟

**نعم، للمعنى الحالي، بشرطين:**

1. لا نعرّف hard-delete commands في Workspace أو Engagement service/CLI.
2. تبقى الأرشفة هي وسيلة الإخفاء أو الإغلاق الطبيعية.

`RESTRICT` يمنع حذف Workspace إذا كان يحتوي Engagements، ويحمي التاريخ من cascade غير مقصود. وهو أفضل من `CASCADE` لأن مستقبل Workspace سيحتوي على سياق قد ترتبط به أدلة وتقارير حساسة.

لكن `RESTRICT` ليس بديلًا عن authorization أو audit. كما أنه لا يمنع حذف Engagement إذا لم توجد بعد جداول children؛ عندما تُضاف Scope أو Evidence لاحقًا، يجب أن تشير هي أيضًا إلى Engagement مع `ON DELETE RESTRICT`. لذلك policy الحالية كافية، لكنها يجب أن تستمر كقاعدة عامة عبر المستقبل.

### `ON UPDATE RESTRICT`

المعرفات immutable في Domain Model، لذلك لا ينبغي أن يحدث update للـPK. وضع `ON UPDATE RESTRICT` يجعل خرق هذه القاعدة يفشل صراحة بدل إعادة كتابة references. لا نستخدم `CASCADE` للمفاتيح لأن UUID identity لا تتغير.

---

## 6. تمثيل timestamps وversion وstatus وkind

### Timestamps

تُخزن جميع timestamps كـ`TEXT` بصيغة UTC canonical التي ينتجها `datetime.isoformat()` بعد `ensure_utc()`. مثال:

```text
2026-08-13T12:30:00+00:00
```

يُمنع تخزين naive datetime في Domain. SQLite لا يفهم timezone semantics كقاعدة بيانات زمنية؛ لذلك التحقق من canonical UTC يبقى Domain/mapper responsibility. شرط `end_at >= start_at` في SQL مفيد فقط لأن القيم canonical ومطبّعة قبل التخزين.

### Version

`INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1)`. لا يستخدم version كـtimestamp أو global revision. عند update يتم استخدام expected version في `WHERE`، ثم version increment atomically. إذا كانت affected rows صفرًا، يرفع repository `CONCURRENCY_CONFLICT` بعد التمييز بين not found وstale version.

### Status

`TEXT` مع allowlist `CHECK` بدل integers أو database enum غير موجود في SQLite. هذا يحافظ على قابلية القراءة ويجعل schema failure واضحًا عند إضافة status جديد دون migration.

### EngagementKind

`TEXT` مع القيم المحددة في Domain: `learning`، `authorized_assessment`، `research`. إضافة kind مستقبلية تحتاج Domain decision واختبارات، ثم migration إذا كان SQL CHECK سيمنع القيمة.

### Authorization reference

`TEXT NULL` بحد 1000 character. لا نضيف `UNIQUE` ولا نعتبره authorization proof. لا يتم تسجيل محتواه كاملًا في logs، ولا يستخدم لتخزين token أو secret أو document body. Scope module اللاحق هو الذي يقرر authorization semantics الفعلية.

---

## 7. E — Migration Plan

### Ordering

```text
0001_persistence_kernel.sql
    ↓
0002_workspace_engagement.sql
```

Migration 0002 لا تعمل منفردة على قاعدة فارغة؛ runner يفرض contiguous ordering، ويطبق 0001 ثم 0002 داخل مسار واحد.

### Transaction boundary

لا تحتوي migration file على `BEGIN` أو `COMMIT`. يقوم Migration Runner من Module 0.2 بـ:

1. فتح connection hardened.
2. بدء transaction ذري.
3. التأكد من migration metadata.
4. التحقق من history وchecksum السابق.
5. تنفيذ `CREATE TABLE` و`CREATE INDEX` للـ0002.
6. تشغيل `quick_check`، ثم `foreign_key_check` ضمن اختبار/health migration policy.
7. تسجيل checksum وversion في `schema_migrations`.
8. commit مرة واحدة.

يفضل أن تستخدم 0002 `CREATE TABLE` و`CREATE INDEX` بدون `IF NOT EXISTS` حتى يكشف drift أو schema collision بدل إخفائه. إذا كانت migration مسجلة، لا يعيد runner تنفيذها؛ وإذا لم تكن مسجلة لكن tables موجودة، يفشل checksum/history أو SQL بدل تبني حالة غير موثوقة.

### SHA-256

يُحسب checksum بعد نفس normalization المستخدمة في Module 0.2. أي تعديل في whitespace أو SQL semantics بعد التطبيق يعتبر checksum mismatch ويحتاج migration forward جديدة، لا تعديل الملف القديم.

---

## 8. F — Rollback Plan

### أثناء تطبيق 0002

إذا فشل إنشاء أي table أو index أو constraint، يقوم runner بrollback للمعاملة كاملة. لا يجب أن تبقى `workspaces` وحدها أو `engagements` وحدها، ولا يجب أن يُسجل version 2 في metadata.

### بعد نجاح 0002

لا نضيف downgrade migration تلقائية. rollback إلى ما قبل 0002 يكون عبر:

| البيئة | الخطة |
|---|---|
| Test/temp DB | حذف الملف وإعادة البناء من migrations |
| Local development | restore من backup معروف أو إعادة إنشاء local DB إذا لم توجد بيانات مهمة |
| بيانات مهمة | backup/restore موثوق؛ لا `DROP TABLE` تلقائي |

إذا ظهرت مشكلة تصميم بعد اعتماد 0002، نفضل `0003` forward migration. لا نعدل 0002 بعد تطبيقها على بيانات مستخدمة، لأن ذلك يكسر checksum والتاريخ.

---

## 9. G — Upgrade Compatibility وRisks

### ما هو متوافق

الترقية من Module 0.2 إلى 0.3.c متوافقة لأن 0002 تضيف جداول جديدة ولا تعدل `schema_migrations` أو جداول سابقة. قواعد PRAGMA وUnitOfWork وMigration Runner تبقى نفسها.

### المخاطر

| الخطر | الأثر | المعالجة |
|---|---|---|
| تطبيق 0002 على schema drift | فشل أو حالة جزئية | transaction ذري، no `IF NOT EXISTS`، checksum/history checks |
| SQLite foreign_keys disabled في connection | orphan Engagement ممكن | PRAGMA hardening + test كل connection + `foreign_key_check` |
| تغيير status أو kind في Domain دون SQL migration | runtime/database mismatch | compatibility review قبل كل enum extension |
| اختلاف timestamp format | ترتيب زمني غير موثوق | canonical UTC mapper وtests |
| duplicate Engagement names | UX ambiguity | اعتماد A أو B صراحة قبل implementation |
| hard delete مستقبلي | فقدان سياق وأدلة | RESTRICT + archive policy + service لا يعرض delete |
| authorization_reference يُفهم كدليل قانوني | false sense of authorization | توثيق صريح وScope/Authorization module لاحق |
| UUID TEXT غير canonical | duplicate أو FK mismatch | Domain validation وpersistence mapper normalization |

### قرار uniqueness المفتوح

الخطر الوحيد الذي يحتاج قرارًا قبل SQL هو uniqueness داخل Workspace. أوصي بأن نؤجل إنشاء unique composite إذا كان تكرار أسماء Engagements التدريبية مقصودًا. إذا كانت UX تتطلب اسمًا واحدًا واضحًا لكل Workspace، نضيفه الآن قبل migration.

---

## 10. H — Security Review

1. **SQL injection:** migration SQL trusted repository content، أما قيم Domain فتدخل لاحقًا عبر parameterized queries. لا يسمح CLI أو repository بإدخال table/column identifiers.
2. **Foreign-key bypass:** `foreign_keys=ON` مطبق في Connection Factory ويجب أن يُختبر لكل connection؛ لا نعتمد على default SQLite.
3. **Data leakage:** authorization reference ليس secret، لكن لا يُطبع كاملًا في logs. الوصف قد يحتوي معلومات حساسة، لذلك redaction/output policy مطلوبة في CLI لاحقًا.
4. **File security:** SQLite file inherits Module 0.2 path policy `0600` وparent `0700`، ولا توجد encryption at rest في هذا التصميم.
5. **Integrity:** migration ذرية، checksum protected، quick_check موجود، وforeign_key_check يجب أن يكون جزءًا من integration tests.
6. **Authorization boundary:** وجود Engagement أو authorization_reference لا يخول تنفيذ أي Target action. Scope وAuthorized Target validation يجب أن يسبقا أي Job/Action مستقبلي.
7. **Auditability:** وجود `engagements.id` وtimestamps وversion يسمح لاحقًا بإضافة Audit Trail يحتوي engagement_id وtarget_id وevidence_id دون إعادة تعريف هوية الكيان.

---

## 11. I — Test Plan

### Migration tests

| الاختبار | الهدف |
|---|---|
| apply 0001 then 0002 | إثبات ordering وschema version 2 |
| checksum recorded | مطابقة SHA-256 metadata |
| atomic DDL failure | لا يبقى table جزئيًا ولا metadata record |
| rerun unchanged | idempotent migration behavior |
| checksum mismatch | رفض تعديل 0002 بعد التطبيق |
| foreign_keys pragma | التأكد من enforcement على connection |
| foreign_key_check | لا توجد orphan rows |
| quick_check | integrity health سليمة |
| table inventory | وجود Workspaces وEngagements فقط من Domain scope |
| no future tables | عدم وجود Target/Scope/Finding/Evidence/Scan/Job/Report |

### Constraint tests

يجب اختبار كل `NOT NULL` و`CHECK` وFK من خلال إدخال row invalid مباشرة على test connection، لأن هذه الاختبارات تثبت أن SQL guard يعمل حتى خارج Domain Service. كما يجب اختبار أن Domain Models ترفض نفس الحالات قبل الوصول إلى SQL.

### Repository preparation tests

ليست جزءًا من تنفيذ Schema Review، لكنها مطلوبة قبل اعتماد 0.3.d: mapping round-trip لكل field، `WorkspaceId` و`EngagementId` canonical، list by workspace، status filter، optimistic version conflict، archive persistence، وparameterized values.

### Future relationship test

لا ننشئ tables مستقبلية الآن. يكفي في 0.3.c اختبار أن `engagements.id` يمكن استخدامه كمفتاح أجنبي من test-only temporary table، ثم حذف الـtemporary table ضمن نفس test DB. لا يُحفظ هذا الجدول في migration.

---

## 12. SQL-vs-Domain Decision Summary

| القاعدة | SQL | Domain | الملاحظة |
|---|---:|---:|---|
| UUID4 الحقيقي | جزئيًا length فقط | نعم | SQL لا يثبت UUID version bits بأمان |
| normalize/trim | لا يعتمد عليه | نعم | SQL يحمي length بعد normalization |
| enum values | نعم | نعم | يمنع unknown values في كل طبقة |
| timestamps UTC-aware | لا بالكامل | نعم | SQL يخزن text فقط |
| start/end ordering | نعم مشروطًا | نعم | SQL defense، Domain authority |
| archive invariants | نعم | نعم | يمنع inconsistent rows |
| authorization عند activation | نعم | نعم | SQL row invariant + Domain transition semantics |
| completed needs end_at | نعم | نعم | defense in depth |
| allowed transitions | لا | نعم | state machine لا توضع في SQL |
| Workspace existence | FK نعم | Service نعم | كلاهما |
| optimistic version | SQL WHERE لاحقًا | Service/Repository | لا يثبت في DDL وحده |
| Scope authorization | لا | لاحقًا | خارج 0.3.c بالكامل |

---

## 13. Recommendation and Approval Gate

التصميم المقترح مناسب للمعنى الحالي: Workspace حاوية عليا، Engagement child محدد، archive بدل delete، وRESTRICT لحماية التاريخ. `ON DELETE RESTRICT` كافٍ للمرحلة الحالية لأن hard delete غير موجود، لكنه يجب أن يستمر مع أي child tables مستقبلية.

قبل كتابة 0002، أحتاج اعتماد قرار واحد مفتوح: **هل تكون أسماء Engagement فريدة case-insensitively داخل Workspace، أم يسمح بتكرارها ويكون UUID هو الهوية الوحيدة؟**

توصيتي الافتراضية هي السماح بالتكرار إذا كانت Labs أو المشاريع قد تتكرر عبر دورات زمنية، مع الاعتماد على UUID في CLI. إذا كانت الأولوية لتقليل الغموض البشري، نعتمد unique composite `(workspace_id, name COLLATE NOCASE)`.

بعد اعتماد هذه الوثيقة وقرار uniqueness، يمكن الانتقال إلى كتابة `0002_workspace_engagement.sql` فقط، ثم تشغيل اختبارات migration دون إنشاء repositories أو CLI في نفس الخطوة.

---

## References

هذه الوثيقة تصميم داخلي لمشروع CyberOS، مبني على العقود المعتمدة في Module 0.1 وPersistence Kernel في Module 0.2 وDomain Models في Module 0.3.a و0.3.b. لا تم تنفيذ SQL أو تعديل قاعدة البيانات أثناء إعداد هذه المراجعة.
