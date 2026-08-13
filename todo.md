# CyberOS Module 0.1 — Execution Checklist

- [x] تثبيت dependencies وقفل الإصدارات
- [x] تنفيذ core contracts
- [x] تنفيذ configuration وlogging
- [x] تنفيذ CLI
- [x] كتابة الاختبارات وفحوصات الجودة والأمن
- [x] تحديث التوثيق
- [x] إنشاء checkpoint وتسليم المرحلة

## Module 0.2 — Persistence Kernel

- [x] اعتماد تصميم SQLite المحلي المحصّن
- [x] تحديد Database layout وconnection lifecycle
- [x] تحديد schema versioning وmigration runner
- [x] تحديد transaction وconcurrency policy
- [x] تعريف Repository Interfaces وpersistence contracts
- [x] كتابة contract tests للـCRUD والـtransactions
- [x] اختبار rollback وعدم فقدان أو فساد البيانات
- [x] اختبار migration upgrade وdowngrade policy
- [x] مراجعة SQLite security وfile permissions وbackup boundaries
- [x] تنفيذ التوثيق والأمثلة وquality gates
- [x] إنشاء checkpoint وتسليم Module 0.2

### 0.2.a — Database Settings + Path/Security Policy

- [x] إضافة DatabaseSettings إلى configuration models
- [x] إضافة environment overrides الخاصة بقاعدة البيانات
- [x] تنفيذ path resolver آمن للمسار الافتراضي والـcustom path
- [x] تنفيذ parent directory creation بسياسة واضحة
- [x] تنفيذ file mode policy بصلاحية 0600 للملفات الجديدة
- [x] رفض المسارات غير الصالحة أو غير القابلة للكتابة بأخطاء typed
- [x] كتابة unit وsecurity tests للحالات الطبيعية والحدية
- [x] تحديث config example وREADME وتوثيق 0.2.a

### 0.2.b — Connection Factory + PRAGMA Hardening

- [x] تعريف SQLite connection contract وhealth result
- [x] تنفيذ Connection Factory بالاعتماد على DatabaseSettings
- [x] تطبيق PRAGMA allowlist بشكل حتمي والتحقق من القيم الفعلية
- [x] تنفيذ lifecycle وclose آمن للاتصالات
- [x] تنفيذ quick_check وintegrity health check
- [x] تحويل أخطاء SQLite إلى typed errors من Module 0.1
- [x] كتابة اختبارات lifecycle وclose وPRAGMA وintegrity
- [x] تشغيل quality gates وتوثيق 0.2.b قبل Migrations

### 0.2.c — Migration Metadata + Runner

- [x] تعريف MigrationRecord وmetadata schema
- [x] إنشاء 0001_persistence_kernel.sql دون Domain Tables
- [x] تنفيذ SQL migration loader مع version/order validation
- [x] تنفيذ SHA-256 checksum normalization والتحقق
- [x] تنفيذ Migration Runner بمعاملة ذرية وrollback
- [x] التعامل مع checksum mismatch وinvalid order وduplicate version
- [x] اختبار idempotent apply وschema version بعد reopen
- [x] تشغيل quality gates وتوثيق 0.2.c قبل UnitOfWork

### 0.2.d — UnitOfWork + Repository Ports

- [x] تعريف transaction state وUnitOfWork protocol
- [x] تنفيذ UnitOfWork فوق ManagedSQLiteConnection
- [x] تطبيق commit صريح وrollback تلقائي عند exception
- [x] منع commit/rollback خارج lifecycle الصحيح
- [x] تعريف Repository Port العام المعزول عن SQL
- [x] إنشاء test repository محدود للاختبارات دون Domain Tables
- [x] اختبار commit وrollback وisolation وclose
- [x] تشغيل quality gates وتوثيق 0.2.d قبل contract tests الأوسع

### 0.2.e — Contract Tests + Persistence Health Integration

- [x] تعريف DatabaseHealth contract النهائي
- [x] ربط schema version مع migration metadata
- [x] ربط PRAGMA state وquick_check بنتيجة health موحدة
- [x] إكمال contract tests للـRepository وUnitOfWork
- [x] اختبار health على قاعدة سليمة وفشل integrity وschema mismatch
- [x] التأكد من عدم إضافة Domain Tables
- [x] تشغيل quality gates النهائية وتحديث كامل التوثيق
- [x] إنشاء checkpoint إغلاق Module 0.2

## Module 0.3 — Workspace & Engagement Design

- [ ] تحديد نطاق Workspace وEngagement وحدودهما
- [ ] تعريف lifecycle وstatus transitions والحقول الأساسية
- [ ] تصميم العلاقات والقيود وcascade policy
- [ ] تصميم 0002_workspace_engagement.sql وchecksum compatibility
- [ ] تعريف Domain Models وvalidation وtyped errors
- [ ] تعريف Repository Interfaces وApplication Services
- [ ] تصميم CLI commands وoutput contracts
- [ ] تصميم Unit وIntegration وCLI Tests
- [ ] مراجعة security وprivacy وmigration safety
- [ ] اعتماد وثيقة التصميم قبل التنفيذ

### 0.3.a — Domain Primitives + Workspace Model

- [x] إنشاء domain package وعقود Workspace
- [x] تعريف WorkspaceStatus وWorkspaceId primitives
- [x] تطبيق name trim وlength validation
- [x] تطبيق description validation
- [x] تطبيق UUID4 وUTC-aware timestamps
- [x] تطبيق archive invariant وversioning
- [x] كتابة Unit Tests دون SQLite أو Engagement
- [x] تشغيل الجودة والتوثيق وإنشاء checkpoint لـ0.3.a

### 0.3.b — Engagement Model + Lifecycle Rules

- [x] تثبيت EngagementId وEngagementKind وEngagementStatus primitives
- [x] تعريف Engagement model مستقل عن SQLite وCLI
- [x] تطبيق workspace_id typed reference دون تحميل Workspace persistence
- [x] تطبيق start/end UTC invariants
- [x] تطبيق authorization_reference guard عند التفعيل
- [x] تطبيق allowed وforbidden lifecycle transitions
- [x] تعريف typed domain errors لكل transition غير صالح
- [x] كتابة Unit Tests شاملة دون SQLite أو Migration 0002
- [x] تشغيل regression وquality gates والتوثيق وإنشاء checkpoint لـ0.3.b

### 0.3.c — Schema Design Review (Approved)

- [x] مراجعة Workspace table mapping
- [x] مراجعة Engagement table mapping
- [x] تثبيت keys وNOT NULL وUNIQUE وCHECK constraints
- [x] تثبيت timestamp وversion وstatus representations
- [x] تثبيت indexes وforeign-key enforcement
- [x] مراجعة ON DELETE/ON UPDATE وfuture relationship space
- [x] تحديد migration ordering وrollback وupgrade compatibility
- [x] تحديد SQL-vs-domain invariants
- [x] إعداد integrity/security/compatibility test plan
- [x] اعتماد schema review قبل كتابة أو تنفيذ 0002

### 0.3.c — Migration 0002 Implementation

- [x] تثبيت عدم تعديل 0001 أو migrations السابقة
- [x] إنشاء 0002_workspace_engagement.sql دون IF NOT EXISTS
- [x] إنشاء workspaces table والقيود المعتمدة
- [x] إنشاء engagements table والقيود المعتمدة
- [x] إضافة UNIQUE(workspace_id, name COLLATE NOCASE)
- [x] إضافة indexes وON DELETE/ON UPDATE policies
- [x] اختبار migration ordering وchecksum وidempotency
- [x] اختبار constraint failures وFK enforcement
- [x] اختبار ON DELETE/ON UPDATE RESTRICT وatomic rollback
- [x] اختبار schema inventory وعدم وجود future Domain tables
- [x] تشغيل quick_check وforeign_key_check
- [x] تشغيل regression وRuff وmypy strict وformatting وwheel build
- [x] توثيق deviation/security review وإنشاء checkpoint لـ0.3.c

### 0.3.d — Workspace Repository + Persistence Mapping

- [x] تعريف WorkspaceRepository port domain-specific
- [x] تنفيذ Workspace SQLite mapper round-trip
- [x] تحويل UUID وUTC ISO-8601 وstatus/version بدقة
- [x] تنفيذ add/get/list/exists/update/archive
- [x] تطبيق ترتيب list حسب created_at DESC ثم id ASC
- [x] تطبيق optimistic concurrency expected_version
- [x] ترجمة duplicate name إلى WORKSPACE_NAME_CONFLICT
- [x] منع sqlite3.Row أو SQL details من التسرب خارج repository
- [x] اختبار UnitOfWork commit وrollback والعزل
- [x] تشغيل regression وRuff وmypy strict وformatting وwheel build
- [x] توثيق 0.3.d وإنشاء checkpoint قبل EngagementRepository

### 0.3.e — Engagement Repository + Persistence Mapping

- [x] تعريف EngagementRepository port domain-specific
- [x] تنفيذ Engagement SQLite mapper round-trip
- [x] تحويل UUID وEnums وUTC timestamps والحقول الاختيارية بدقة
- [x] تنفيذ add/get/list_by_workspace/update/transition/archive
- [x] تطبيق Workspace FK وactive/archived guards
- [x] ترجمة WORKSPACE_NOT_FOUND وWORKSPACE_ARCHIVED
- [x] ترجمة duplicate name إلى ENGAGEMENT_NAME_CONFLICT
- [x] تطبيق optimistic concurrency على update/transition/archive
- [x] منع sqlite3.Row أو SQL details من التسرب خارج repository
- [x] اختبار UnitOfWork commit وrollback والعزل
- [x] تشغيل regression وRuff وmypy strict وformatting وwheel build
- [x] توثيق 0.3.e وإنشاء checkpoint قبل CLI/Application Services
