# التقرير الشامل لمشروع CyberOS

## من مرحلة التأسيس حتى Module 0.3.a

**اسم المشروع:** CyberOS — Personal Cybersecurity Engineering OS  
**النطاق الحالي:** Foundation، Persistence Kernel، وبداية Domain Layer  
**الحالة الحالية:** منفّذ ومختبر حتى `0.3.a — Domain Primitives + Workspace Model`  
**آخر checkpoint:** `b80f848e`  
**تاريخ التقرير:** 13 أغسطس 2026

---

## 1. الملخص التنفيذي

CyberOS هو منظومة شخصية طويلة الأمد تهدف إلى بناء طبقة هندسية فوق أدوات ومعارف الأمن السيبراني الموجودة، بدل إعادة اختراع أدوات عامة. صُممت المنظومة لتخدم مسارًا يبدأ من Web Penetration Testing، ثم Network وAD وCloud Security، ويمتد إلى API Security وPython وData وML وDeep Learning وLLM Security وAI Red Teaming وAI Security Engineering/Research.

منذ البداية تم اعتماد أسلوب **Module-by-Module**. كل مرحلة تُصمم أولًا، ثم تُنفذ على أجزاء صغيرة، وتُختبر وتُوثق وتُحفظ في checkpoint مستقل قبل الانتقال إلى المرحلة التالية. حتى الآن تم بناء نواة Python، ثم Persistence Kernel كامل، ثم أول Domain Model وهو Workspace. لم يتم بناء Recon أو Scanner أو AI أو Web UI أو Domain Tables الخاصة بالأهداف والنتائج بعد، لأن إدخالها قبل تثبيت الأساس كان سيخلق إعادة تصميم ومشاكل تكامل مستقبلية.

> النتيجة الحالية ليست Script مؤقتًا؛ إنها بداية منتج Software قابل للتوسع، مع حدود واضحة بين Core وPersistence وDomain وCLI.

---

## 2. الرؤية والهدف

الهدف هو بناء **Personal Cybersecurity Engineering OS** يساعد المستخدم في التعلم، التدريب، تنفيذ Labs، إدارة الاختبارات المصرح بها، تنظيم الأدلة، تحليل النتائج، كتابة التقارير، أتمتة الأعمال المتكررة، AI Red Teaming، وقياس التطور الحقيقي.

المبدأ المركزي هو استخدام الأدوات الخارجية المتخصصة كـengines أو dependencies عند الحاجة، ثم بناء القيمة الشخصية المفقودة حولها: التنظيم، correlation، normalization، evidence handling، reproducibility، learning context، وقياس المسار المهني.

### المبادئ المعمارية المعتمدة

| المبدأ | كيف طُبق حتى الآن |
|---|---|
| Modular Architecture | تقسيم التنفيذ إلى Modules ثم sub-modules صغيرة ذات حدود واضحة |
| Local-first | SQLite وPython Core يعملان محليًا، ولا توجد اتصالات خارجية في النواة الحالية |
| Privacy-first | لا telemetry في النواة، redaction، file permissions، وعدم تخزين secrets |
| API-first | Application boundaries وOperationResult مصممة لتخدم CLI ثم API لاحقًا |
| Structured JSON | envelopes ومخرجات JSON ثابتة قابلة للاستهلاك البرمجي |
| Testability | Unit وContract وIntegration وCLI وSecurity tests مع temporary databases |
| Extensibility | Plugin contracts، Repository Ports، migration runner، وseparation of layers |
| Security by design | typed errors، parameterized SQL، checksum، rollback، integrity checks، ورفض symlinks |
| No premature features | لا Domain Tables ولا Recon ولا AI قبل اعتماد طبقاتها التصميمية |

---

## 3. نقطة البداية والقرار المعماري الرئيسي

المشروع الذي تم فتحه في البيئة هو React web-static scaffold. بعد تحليل الاحتياج، تم اتخاذ قرار مهم: **لا توضع نواة CyberOS داخل React**. React مناسب لاحقًا كطبقة عرض، لكنه ليس مكانًا مناسبًا لنواة تحتاج Python وSQLite وCLI وتشغيل adapters محلية.

لذلك أُنشئت حزمة Python مستقلة منطقيًا داخل:

```text
/home/ubuntu/cyberos-foundation/cyberos-core
```

وبقيت طبقة React Web Shell منفصلة وغير مستخدمة كمصدر للحقيقة. هذا القرار يحافظ على مسار Python وData وML، ويسمح لاحقًا بإضافة HTTP API أو Web UI دون تكرار منطق المجال.

### التقنيات الحالية

| الطبقة | التقنية |
|---|---|
| Core runtime | Python 3.11+؛ الاختبارات الحالية شُغلت على Python 3.12.3 |
| Validation | Pydantic v2 |
| CLI | Typer |
| Logging | structlog مع Python logging |
| Configuration | TOML + `CYBEROS_*` environment overrides |
| Serialization | JSON |
| Database | SQLite عبر `sqlite3` Standard Library، دون ORM |
| Migrations | Internal SQL runner + SHA-256 checksums |
| Tests | pytest |
| Quality | Ruff، mypy strict، formatting، wheel build |
| Packaging | pyproject.toml، optional dev dependencies، uv.lock |

---

## 4. التسلسل الزمني والـCheckpoints

تم حفظ كل مرحلة مستقلة حتى يمكن الرجوع إليها دون استخدام تغييرات تدميرية.

| المرحلة | ما تم إنجازه | الاختبارات التراكمية | Checkpoint |
|---|---|---:|---|
| Module 0.1 | Bootstrap & Core Contracts | 14 | `07952d88` |
| 0.2.a | Database Settings + Path/Security Policy | 22 | `e65a5074` |
| 0.2.b | Connection Factory + PRAGMA Hardening | 30 | `fbe26d13` |
| 0.2.c | Migration Metadata + Runner | 37 | `c88a3a4d` |
| 0.2.d | UnitOfWork + Repository Ports | 42 | `4612d533` |
| 0.2.e | Contract Tests + Persistence Health | 47 | `af90d7e0` |
| 0.3.a | Workspace Domain Model | 60 | `b80f848e` |

آخر نقطة مستقرة هي `b80f848e`. أما `af90d7e0` فهي نقطة إغلاق Persistence Kernel قبل بدء Domain Layer.

---

## 5. Module 0.1 — Bootstrap & Core Contracts

### الهدف

كان الهدف بناء نواة تشغيل صغيرة لا تحتوي أي Cybersecurity functionality، لكنها تثبت قواعد الإعدادات والسجلات والأخطاء والمخرجات والاختبارات التي ستستخدمها كل الوحدات القادمة.

### ما تم بناؤه

#### Core contracts

تم بناء عقود للمعرّفات، correlation IDs، operation context، UTC timestamps، JSON serialization، OperationResult، ErrorPayload، وPluginManifest. المعرّفات تستخدم UUID4، والتواريخ الداخلية timezone-aware UTC.

#### Error taxonomy

تم إنشاء `CyberOSError` مع `ErrorCode` و`details` و`retryable` و`severity` وexit codes. هذا يمنع الاعتماد على رسائل نصية غير قابلة للمعالجة، ويفصل الرسالة الآمنة للمستخدم عن تفاصيل الخطأ الداخلية.

#### Configuration

تم اعتماد TOML كصيغة بشرية للإعدادات، مع environment overrides، وJSON للمخرجات. ترتيب الأولوية هو defaults ثم TOML ثم environment ثم خيارات CLI المستقبلية. لا يتم تحميل أو طباعة environment كامل، ولا يتم تخزين secrets.

#### Logging

تم إعداد structured logging بصيغة text أو JSON، مع correlation ID وoperation ID. لا تظهر stack traces أو القيم الحساسة في المخرجات العادية.

#### CLI

تم بناء الأوامر التالية:

```text
cyberos version
cyberos doctor
cyberos doctor --json
cyberos config show
cyberos config validate --file ./config/cyberos.example.toml
```

أمر `doctor` يفحص Python runtime، المسارات، وJSON serialization دون network أو subprocess.

#### Plugin contract

تم تعريف PluginManifest وPluginProtocol وValidationResult وHealthResult. لم يتم تشغيل plugins أو تحميل أدوات خارجية؛ تم تثبيت العقد فقط حتى لا نفتح سطح تنفيذ مبكرًا.

### ملفات Module 0.1 الرئيسية

```text
cyberos-core/
├── pyproject.toml
├── uv.lock
├── README.md
├── config/cyberos.example.toml
├── src/cyberos/core/
│   ├── ids.py
│   ├── time.py
│   ├── context.py
│   ├── errors.py
│   ├── result.py
│   ├── serialization.py
│   └── plugins.py
├── src/cyberos/config/
│   ├── models.py
│   ├── loader.py
│   └── redaction.py
├── src/cyberos/logging/setup.py
├── src/cyberos/application/
│   ├── version.py
│   └── doctor.py
├── src/cyberos/cli/app.py
└── tests/
    ├── unit/
    └── cli/
```

### نتيجة الاختبار

نجحت 14 اختبارات، ثم نجحت Ruff وmypy strict وwheel build. تم حفظ المرحلة في `07952d88`.

---

## 6. Module 0.2 — Persistence Kernel

كان هذا الموديول طبقة التخزين المحلية الكاملة، وقد أُغلق رسميًا في `af90d7e0`. تم تقسيمه إلى خمسة أجزاء حتى لا يتم خلط path policy مع connection أو migrations أو transactions.

### 6.1 — 0.2.a Database Settings + Path/Security Policy

تمت إضافة `DatabaseSettings` إلى `CyberOSConfig`، مع القيم الافتراضية الآتية:

```toml
[database]
path = "~/.cyberos/cyberos.sqlite3"
timeout_seconds = 5.0
journal_mode = "wal"
synchronous = "full"
foreign_keys = true
secure_delete = true
create_parent = true
```

تم دعم environment variables مثل `CYBEROS_DATABASE_PATH` و`CYBEROS_DATABASE_TIMEOUT_SECONDS` و`CYBEROS_DATABASE_FOREIGN_KEYS`.

تم تنفيذ `prepare_database_path()`، وهي تتحقق من أن المسار absolute، ترفض directory كملف قاعدة، ترفض symlink للملف أو parent، تنشئ parent بصلاحية `0700`، وتنشئ ملف قاعدة جديدًا بصلاحية `0600` على POSIX. الملفات الموجودة ذات الصلاحيات الأوسع تُرفض بدل تعديلها بصمت، مع تضييق parent المملوك للمستخدم عند الحاجة.

### 6.2 — 0.2.b Connection Factory + PRAGMA Hardening

تم بناء `SQLiteConnectionFactory` و`ManagedSQLiteConnection`. كل اتصال يمر من factory واحدة، وتطبق السياسة التالية بشكل حتمي:

| PRAGMA | القيمة |
|---|---|
| `foreign_keys` | ON |
| `journal_mode` | WAL |
| `synchronous` | FULL |
| `busy_timeout` | 5000 ms |
| `secure_delete` | ON |

بعد التطبيق يتم قراءة القيم الفعلية والتحقق منها، وليس الاكتفاء بإرسال الأوامر. تم دعم context manager، close idempotent، منع استخدام الاتصال بعد إغلاقه، و`quick_check` دون auto-repair.

### 6.3 — 0.2.c Migration Metadata + Runner

تم بناء migration loader وrunner داخليين. يستخدم loader أسماء مثل `0001_persistence_kernel.sql`، ويتحقق من أن versions تبدأ من 1، متسلسلة، وغير مكررة. يتم تطبيع line endings والمسافات النهائية قبل حساب SHA-256.

تم إنشاء `schema_migrations`:

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    execution_ms INTEGER NOT NULL CHECK (execution_ms >= 0)
);
```

ملف `0001_persistence_kernel.sql` ينشئ metadata فقط، ولا يضيف Workspace أو Target أو Finding أو Evidence.

يعمل runner باستخدام `BEGIN IMMEDIATE`، ويطبق SQL، ويسجل checksum، ويشغل quick check، ثم commit. عند الفشل يحدث rollback للمعاملة كاملة. إعادة تشغيل migration مطابقة لا تعيد التنفيذ، أما checksum mismatch أو invalid order أو history غير متسق فيؤدي إلى typed error.

### 6.4 — 0.2.d UnitOfWork + Repository Ports

تم بناء `SQLiteUnitOfWork` بحالات:

```text
NEW → ACTIVE → COMMITTED
NEW → ACTIVE → ROLLED_BACK
```

يبدأ UnitOfWork بمعاملة صريحة، ولا يوجد auto-commit بعد كل repository operation. يجب استدعاء `commit()` صراحة. عند خروج context مع exception يتم rollback تلقائيًا، ثم يغلق الاتصال. أي commit أو rollback خارج lifecycle الصحيح يعطي typed error.

تم تعريف `Repository[RecordT]` و`UnitOfWorkPort` كواجهات عامة لا تعرف SQL أو أسماء الجداول. تم استخدام test repository مستقل للتحقق من commit وrollback وisolation، دون اعتباره Domain Model إنتاجيًا.

### 6.5 — 0.2.e Contract Tests + Persistence Health Integration

تم بناء `DatabaseHealthReport` الذي يعكس:

| الحقل | المعنى |
|---|---|
| `healthy` | قاعدة مهيأة وسليمة وتاريخ migrations متسق |
| `schema_version` | أعلى migration مطبقة |
| `schema_initialized` | وجود history متسق |
| `pragma_state` | القيم الفعلية المحققة |
| `quick_check` | نتيجة integrity check |
| `details` | migration count وhistory contiguity |

القاعدة غير المهيأة ليست healthy حتى لو كان ملف SQLite صالحًا بنيويًا؛ وهذا يمنع اعتبار ملف فارغ جاهزًا للنظام. كما أن history غير المتسق يُظهر unhealthy ولا يحاول النظام إصلاحه تلقائيًا.

### نتيجة Persistence Kernel

تم إغلاق Module 0.2 رسميًا في `af90d7e0` بعد 47 اختبارًا ناجحًا. نجحت Ruff وmypy strict وformatting وwheel build، ولم تتم إضافة أي Domain Tables.

---

## 7. Module 0.3 — Workspace & Engagement Design

قبل التنفيذ تم إعداد وثيقة تصميم كاملة لـWorkspace وEngagement. الفكرة هي أن Workspace مساحة طويلة الأمد، بينما Engagement نشاط أو مختبر أو تقييم محدد داخل Workspace.

### القرارات التصميمية المعتمدة

| القرار | المعتمد |
|---|---|
| Workspace status | `active` و`archived` |
| Engagement kinds | `learning` و`authorized_assessment` و`research` |
| Engagement statuses | `draft` و`active` و`paused` و`completed` و`archived` |
| Delete policy | لا hard delete؛ archive و`ON DELETE RESTRICT` |
| Versioning | optimistic version يبدأ من 1 |
| Authorization | `authorization_reference` قبل تفعيل authorized assessment |
| Migration | `0002_workspace_engagement.sql` فوق 0001 |
| CLI | workspace وengagement مع `--json` وexpected-version |

### ما لم يُنفذ بعد

رغم اعتماد التصميم، لم يتم حتى الآن تنفيذ Engagement أو migration 0002 أو Workspace Repository أو Workspace CLI. التنفيذ الحالي بدأ فقط بالجزء الأصغر 0.3.a، حفاظًا على أسلوب العمل المرحلي.

---

## 8. 0.3.a — Workspace Domain Model

### النموذج

تم بناء Workspace كـimmutable aggregate model مستقل عن persistence:

```text
Workspace
├── id: UUID4
├── name: str, 1..120 بعد trim
├── description: str, 0..4000 بعد trim
├── status: active | archived
├── created_at: aware UTC datetime
├── updated_at: aware UTC datetime
├── archived_at: aware UTC datetime | None
└── version: positive int
```

### قواعد validation

يتم trim للاسم والوصف. الاسم الفارغ أو الأطول من 120 مرفوض، والوصف الأطول من 4000 مرفوض. المعرف UUID4، ويتم رفض UUID versions الأخرى. التواريخ naive مرفوضة، و`updated_at` لا يجوز أن يسبق `created_at`.

### قواعد archiving

Workspace الجديد يبدأ `active` وversion=1. `archive()` ينشئ نسخة immutable جديدة بحالة `archived`، ويضع `archived_at` و`updated_at`، ويزيد version إلى 2 أو القيمة التالية. لا يمكن أرشفة Workspace المؤرشف مرة أخرى.

### الاختبارات

تمت كتابة 13 Unit Tests تغطي:

1. إنشاء UUID4 وUTC timestamps.
2. قبول UUID4 صريح.
3. trim وname boundaries.
4. description limit.
5. رفض naive timestamp.
6. رفض non-UUID4.
7. timestamp ordering.
8. archive status/timestamps/version.
9. immutability.
10. active/archived invariants.

أصبح إجمالي اختبارات المشروع **60 اختبارًا ناجحًا**، مع نجاح Ruff وmypy strict وwheel build. تم حفظ checkpoint الحالي `b80f848e`.

---

## 9. هيكل المشروع الحالي

```text
cyberos-foundation/
├── docs/
│   ├── architecture/
│   │   ├── module-0.1-bootstrap-core-contracts.md
│   │   ├── module-0.2-persistence-kernel.md
│   │   └── module-0.3-workspace-engagement.md
│   ├── development/
│   │   ├── persistence.md
│   │   ├── persistence-0.2a.md
│   │   ├── persistence-0.2b.md
│   │   ├── persistence-0.2c.md
│   │   ├── persistence-0.2d.md
│   │   ├── persistence-0.2e.md
│   │   └── domain-0.3a.md
│   └── reports/
│       └── cyberos-comprehensive-progress-report-ar.md
├── todo.md
└── cyberos-core/
    ├── pyproject.toml
    ├── uv.lock
    ├── README.md
    ├── config/
    ├── docker/
    ├── scripts/check.sh
    ├── src/cyberos/
    │   ├── core/
    │   ├── config/
    │   ├── logging/
    │   ├── infrastructure/
    │   ├── application/
    │   ├── cli/
    │   ├── persistence/
    │   └── domain/workspace/
    └── tests/
        ├── unit/
        ├── contract/
        ├── integration/
        ├── security/
        └── support/
```

---

## 10. الملفات والواجهات الأساسية

### Core وconfiguration

الملفات الأساسية هي `core/ids.py` و`core/time.py` و`core/context.py` و`core/errors.py` و`core/result.py` و`core/serialization.py` و`core/plugins.py`. أما إعدادات TOML وenvironment وredaction فتوجد في `config/models.py` و`config/loader.py` و`config/redaction.py`.

### Persistence

أهم ملفات التخزين هي `persistence/path_policy.py` و`persistence/connection.py` و`persistence/health.py` و`persistence/unit_of_work.py` و`persistence/ports.py`، إضافة إلى `persistence/migrations/loader.py` و`models.py` و`runner.py` و`versions/0001_persistence_kernel.sql`.

### Domain

الجزء المنفذ حاليًا هو `domain/workspace/primitives.py` و`domain/workspace/model.py`. لا توجد بعد Engagement package أو repositories domain-specific أو migration 0002.

### Tests

الاختبارات موزعة حسب المسؤولية: `unit` للعقود والنماذج، `contract` للواجهات، `integration` لSQLite وmigrations وUnitOfWork، `security` للتحصين، و`cli` للحدود الخارجية.

---

## 11. أوامر التشغيل والاختبار

```bash
cd /home/ubuntu/cyberos-foundation/cyberos-core
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[dev]'
```

تشغيل النواة الحالية:

```bash
cyberos version
mkdir -p ~/.cyberos/logs
cyberos doctor --json
cyberos config validate --file ./config/cyberos.example.toml
```

تشغيل كل الاختبارات وفحوصات الجودة:

```bash
bash scripts/check.sh
```

ينفذ `scripts/check.sh` pytest، Ruff lint، Ruff format check، mypy strict، وwheel build. النتيجة الأخيرة المثبتة هي 60 اختبارًا ناجحًا.

---

## 12. المراجعة الأمنية الحالية

تم تطبيق عدة ضوابط من البداية. لا توجد network calls أو subprocess في الوحدات الحالية. SQL values في Persistence تستخدم parameters، ولا يتم تمرير table أو column identifiers من المستخدم. Migrations تتحقق من checksum ولا تملك downgrade تلقائيًا. المعاملات ذرية، والـhealth check لا يقوم بإصلاح تلقائي عند فساد أو عدم اتساق.

ملف SQLite الجديد ينشأ بصلاحية `0600`، والـparent directory بسياسة `0700`. symlinks غير الآمنة مرفوضة. لا توجد encryption at rest، ولا ندعي وجودها؛ هذا يحتاج قرارًا مستقلًا مستقبلًا. كذلك لا توجد secret vault أو authentication أو audit log كامل بعد.

في Domain Layer، يتم منع تفعيل authorized assessment بلا authorization reference، لكن هذا الحقل ليس إثباتًا قانونيًا للتفويض. Scope Management سيأتي في موديول مستقل، ولن يتم بناء قدرات تنفيذية خارج النطاق المصرح به.

---

## 13. المشاكل التي ظهرت وتمت معالجتها

خلال التنفيذ ظهرت مشاكل هندسية صغيرة وتم التعامل معها بدل تجاهلها:

| المشكلة | المعالجة |
|---|---|
| optional dev dependencies لم تُثبت عبر pip extra أولًا | إضافة `[project.optional-dependencies]` و`uv.lock` |
| مخالفات Ruff لطول الأسطر وترتيب imports | تشغيل format/lint وإعادة تنظيم الكود |
| أخطاء mypy في نتائج PRAGMA وtyping | إضافة helpers typed وتحديد return types |
| SyntaxError بسبب قوس زائد في persistence init | إصلاحه قبل متابعة الاختبارات |
| تعارض import اسم tests | إزالة الاعتماد غير الضروري وتضمين fixture محليًا |
| تحذير Pytest من اسم TestRecord | إعادة تسمية fixture لتجنب collection warning |
| bug في `Workspace.archive()` بسبب duplicate kwargs | دمج values قبل إعادة validation |

هذه النقاط موثقة ضمن مسار الاختبارات العملي، ونتيجتها أن المرحلة الحالية لا تعتمد على تجاهل warnings أو إخفاء failures.

---

## 14. ما تم تأجيله عمدًا

لم يتم بناء Recon Orchestrator أو Scanner أو Nmap Adapter أو Subdomain Adapter أو Evidence Vault أو Finding Engine أو Report Factory أو AI Copilot أو LLM Security features. كما لم يتم إنشاء Target أو Scope أو Task أو Scan أو Finding أو Evidence tables.

السبب ليس نقصًا في الخطة؛ بل لأن هذه الوحدات ستستخدم البيانات المشتركة نفسها، ولذلك يجب أن تأتي بعد تثبيت domain ownership، persistence contracts، Workspace، Engagement، وScope. هذا يقلل مخاطر إعادة بناء schema وإعادة كتابة repositories لاحقًا.

---

## 15. الخطة التالية

الخطوة المعتمدة التالية هي `0.3.b — Engagement Model + Lifecycle Rules`، وستبقى pure domain code دون SQLite في البداية. بعدها نثبت `0.3.c — Migration 0002`، ثم Workspace Repository وApplication Service وCLI، ثم Engagement persistence وCLI.

التسلسل المقترح:

```text
0.3.a Workspace Domain Model              [مكتمل]
0.3.b Engagement Model + Lifecycle       [التالي]
0.3.c Migration 0002 + Schema Constraints
0.3.d Workspace Repository + Service + CLI
0.3.e Engagement Repository + Service + CLI
0.3.f Contract/Integration/CLI/Security Tests
0.3.g Documentation + Final Checkpoint
```

بعد إغلاق Module 0.3، يمكن الانتقال إلى Module 0.4 — Target & Scope، ثم Tasks/Jobs، ثم Recon Adapters. Evidence وFindings والتقارير تأتي بعد توفر domain records مستقرة.

---

## 16. الخلاصة النهائية

من الصفر تم الانتقال من فكرة عامة إلى بنية عملية قابلة للتوسع: نواة Python بعقود مشتركة، configuration وlogging وtyped errors، Persistence Kernel محلي محصن، migrations ذرية مع checksum، UnitOfWork وRepository Ports، Database Health، ثم أول Domain Model فعلي لـWorkspace.

الحالة الحالية قوية من ناحية الأساس البرمجي والاختبار، لكنها ليست منظومة Cybersecurity تشغيلية كاملة بعد، وهذا مقصود ومعلن. ما تم بناؤه هو الأساس الذي يمنع الوحدات القادمة من أن تصبح scripts منفصلة أو schema غير متناسقة. آخر نتيجة مثبتة هي checkpoint `b80f848e` مع 60 اختبارًا ناجحًا، والخطوة التالية الواضحة هي Engagement Domain Model.

---

## References

هذا التقرير يلخص قرارات وتنفيذًا داخليًا لمشروع CyberOS، ولا يعتمد على مصادر خارجية. المراجع التنفيذية الأساسية داخل المشروع هي وثائق `docs/architecture/` و`docs/development/` والـcheckpoints المذكورة في هذا التقرير.
