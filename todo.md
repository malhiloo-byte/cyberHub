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

## Module 0.3 — Workspace & Engagement Design (Closed)

- [x] تحديد نطاق Workspace وEngagement وحدودهما
- [x] تعريف lifecycle وstatus transitions والحقول الأساسية
- [x] تصميم العلاقات والقيود وcascade policy
- [x] تصميم 0002_workspace_engagement.sql وchecksum compatibility
- [x] تعريف Domain Models وvalidation وtyped errors
- [x] تعريف Repository Interfaces وApplication Services
- [x] تصميم CLI commands وoutput contracts
- [x] تصميم Unit وIntegration وCLI Tests
- [x] مراجعة security وprivacy وmigration safety
- [x] اعتماد وثيقة التصميم قبل التنفيذ

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

### 0.3.f — Application Services + CLI Integration

- [x] تعريف service ports وOperationResult output contract
- [x] تنفيذ WorkspaceService create/list/show/archive
- [x] تنفيذ EngagementService create/list/show/transition/archive
- [x] تطبيق authorization guard وUTC completion time داخل services
- [x] إضافة CLI workspace commands
- [x] إضافة CLI engagement commands
- [x] دعم --json وcorrelation_id وhuman-readable output
- [x] دعم --expected-version وtyped exit codes
- [x] اختبار services بعيدًا عن CLI
- [x] اختبار CLI text/JSON/errors/deterministic output
- [x] تشغيل regression وRuff وmypy strict وformatting وwheel build
- [x] توثيق 0.3.f وإنشاء checkpoint قبل 0.3.g

### 0.3.g — Documentation + Final Module Checkpoint

- [x] تنفيذ Cross-Layer Boundary Review النهائي
- [x] تحديث README وArchitecture documentation
- [x] إضافة أمثلة CLI text وJSON
- [x] توثيق Transition Matrix وarchive/versioning policies
- [x] تأكيد عدم إضافة Domain Tables أو features مستقبلية
- [x] تشغيل pytest وRuff وmypy strict وformatting وwheel build
- [x] إنشاء checkpoint الإغلاق النهائي لـModule 0.3

## Module 0.4 — Target & Scope Management (Design Approved; 0.4.b In Progress)

- [x] تثبيت حدود Module 0.4 وسلسلة Engagement → Scope → Target
- [x] تعريف Scope وTarget domain models وtyped identifiers
- [x] تحديد include/exclude semantics وScope Matcher rules
- [x] تحديد authorization وsafety guards ومنع out-of-scope actions
- [x] تصميم 0003_target_scope.sql والقيود والفهارس وFK policies
- [x] تعريف ScopeRepository وTargetRepository وScopeValidationService ports
- [x] تصميم CLI commands وJSON/text output contracts
- [x] إعداد خطة الاختبارات الأمنية والوظيفية وحالات الرفض
- [x] إعداد خطة التنفيذ المرحلي 0.4.a وما بعدها
- [x] مراجعة واعتماد وثيقة تصميم Module 0.4 قبل التنفيذ

### 0.4.a — Domain Primitives + Target Canonicalization

- [x] تعريف ScopeId وTargetId كـUUID4 typed identifiers
- [x] تعريف ScopeStatus وTargetRule وTargetKind enums
- [x] تعريف typed validation errors الخاصة بالـcanonicalization
- [x] تنفيذ CandidateParser وTargetCanonicalizer دون network side effects
- [x] دعم canonicalization لـFQDN وwildcard وIPv4 وIPv6 وCIDR وURL
- [x] رفض control characters وcredentials/fragments وwildcards غير الآمنة
- [x] رفض IPv4/IPv6 default routes والتمثيلات الغامضة
- [x] كتابة pure unit tests للـprimitives والأنواع الستة وحالات الرفض
- [x] تنفيذ boundary/security review وعدم إضافة SQLite أو CLI أو Matcher
- [x] تشغيل pytest وRuff وmypy strict وformatting وwheel build
- [x] تحديث توثيق 0.4.a
- [x] إنشاء checkpoint لـ0.4.a

### 0.4.b — Scope & Target Aggregates

- [x] إضافة typed domain errors لـScope وTarget lifecycle
- [x] تنفيذ Target immutable domain model
- [x] تطبيق Target UTC/archive/version invariants
- [x] تنفيذ Scope immutable aggregate model
- [x] تطبيق Scope draft/validated/authorized/archived transitions
- [x] تطبيق authorization_reference وauthorized_at guards
- [x] تطبيق expiry وtimestamp/version invariants
- [x] منع تعديل أو إضافة أو أرشفة Target داخل Scope authorized
- [x] منع أي تعديل عكسي لـScope archived
- [x] كتابة pure unit tests للـTarget وScope وجميع edge cases
- [x] تنفيذ boundary/security review دون SQLite أو migration أو Matcher أو CLI
- [x] تشغيل pytest وRuff وmypy strict وformatting وwheel build
- [x] تحديث توثيق 0.4.b
- [x] إنشاء checkpoint لـ0.4.b

### 0.4.c — Schema Design Review + Migration 0003

- [x] مراجعة توافق Domain models مع Schema 0003
- [x] إنشاء 0003_target_scope.sql دون IF NOT EXISTS أو BEGIN/COMMIT
- [x] إنشاء جدول scopes بقيود status/length/timestamp/version وFK
- [x] إنشاء جدول targets بقيود rule/kind/status/value/version وFK
- [x] إضافة unique indexes المطلوبة لـScope وTarget
- [x] تطبيق ON DELETE/UPDATE RESTRICT في العلاقات
- [x] اختبار migration ordering وchecksum وforward-only behavior
- [x] اختبار schema creation وquick_check وforeign_key_check
- [x] اختبار uniqueness وstatus/rule/kind/length constraints
- [x] اختبار FK enforcement وRESTRICT وعدم التأثير على 0001/0002
- [x] اختبار atomic rollback عند فشل migration
- [x] تنفيذ boundary/security review دون repositories أو matcher أو CLI
- [x] تشغيل pytest وRuff وmypy strict وformatting وwheel build
- [x] تحديث توثيق 0.4.c
- [x] إنشاء checkpoint لـ0.4.c

### 0.4.e — Scope & Target Repositories + Persistence Mapping

- [x] تعريف ScopeRepository وTargetRepository ports
- [x] تنفيذ ScopeMapper round-trip مع UUID/UTC/enums/invariants
- [x] تنفيذ TargetMapper round-trip مع canonical values وUUID/UTC/enums
- [x] تنفيذ ScopeRepository add/get/list_by_engagement/exists/update/archive
- [x] تنفيذ TargetRepository add/get/list_by_scope/exists/update/archive
- [x] تطبيق optimistic concurrency expected_version
- [x] ترجمة SCOPE_NAME_CONFLICT وTARGET_DUPLICATE وبقية أخطاء SQLite
- [x] تطبيق Engagement/Scope existence وarchive guards
- [x] ضمان UnitOfWork commit/rollback وعدم تسريب sqlite3.Row أو SQL details
- [x] كتابة اختبارات round-trip وCRUD وconcurrency وtyped errors وFK protection
- [x] تنفيذ boundary/security review دون Matcher أو ScopeValidationService أو CLI أو network
- [x] تشغيل pytest وRuff وmypy strict وformatting وwheel build
- [x] تحديث توثيق 0.4.e
- [x] إنشاء checkpoint لـ0.4.e

### 0.4.f — Scope Matcher Engine + Safety Policy

- [x] تعريف MatchDecision وMatchResult value objects
- [x] تعريف ScopeMatcher pure interface دون network side effects
- [x] تطبيق precedence exclude > include > deny
- [x] تطبيق fail-closed للـScope غير authorized وغير المطابق
- [x] دعم FQDN exact وwildcard وIPv4 وIPv6 وCIDR وURL host extraction
- [x] تطبيق URL parsing محليًا مع رفض credentials/fragments غير الآمنة
- [x] كتابة Matrix Unit Tests شاملة للـprecedence والحدود
- [x] اختبار IPv4/IPv6/CIDR داخل وخارج الشبكات
- [x] اختبار wildcard root/subdomain boundaries
- [x] تنفيذ boundary/security review لمنع DNS/HTTP/subprocess
- [x] تأكيد عدم إضافة ScopeValidationService أو Application Services أو CLI
- [x] تشغيل pytest وRuff وmypy strict وformatting وwheel build
- [x] تحديث توثيق 0.4.f
- [x] إنشاء checkpoint لـ0.4.f

### 0.4.g — Application Scope Services + Boundary Guards

- [x] تعريف TargetCandidate immutable DTO مع raw_value وTargetKind
- [x] تعريف ScopeEvaluationResult وExecutionAuthorization DTOs
- [x] تعريف service contract لـScopeValidationService
- [x] ربط الخدمة بـScopeRepository وTargetRepository وUnitOfWork
- [x] تطبيق authorize_execution مع ScopeMatcher
- [x] رفض Scope غير authorized أو archived أو expired
- [x] رفض EXCLUDED وDENIED_OUT_OF_SCOPE بشكل fail-closed
- [x] توفير أسباب وبيانات audit قابلة للتدقيق دون SQL leakage
- [x] ضمان عدم تنفيذ task/subprocess/network من الخدمة
- [x] كتابة service وintegration tests للـauthorized workflow والحدود
- [x] اختبار rollback وقراءة البيانات عبر repositories
- [x] تنفيذ boundary/security review دون CLI أو Task Runner
- [x] تشغيل pytest وRuff وmypy strict وformatting وwheel build
- [x] تحديث توثيق 0.4.g
- [x] إنشاء checkpoint لـ0.4.g

### 0.4.h — Scope CLI Interface + Module 0.4 Final Wrap-up

- [x] إضافة cyberos scope create
- [x] إضافة cyberos scope authorize
- [x] إضافة cyberos target add مع فرض rule/kind/value صراحة
- [x] إضافة cyberos scope evaluate مع TargetCandidate DTO
- [x] إضافة JSON/text output envelopes قابلة للتدقيق
- [x] تطبيق exit codes 0/1/2 للنجاح والمدخلات والرفض الأمني
- [x] منع auto-inference وsubprocess وnetwork activity
- [x] كتابة CLI E2E lifecycle tests للإنشاء والإضافة والتفويض والتقييم
- [x] اختبار INCLUDED وEXCLUDED وDENIED وinvalid input ومخرجات بلا traceback
- [x] تحديث README وArchitecture وModule 0.4 closure documentation
- [x] تنفيذ final boundary/security review للموديول كاملًا
- [x] تشغيل pytest وRuff وmypy strict وformatting وwheel build
- [x] إنشاء checkpoint النهائي وإغلاق Module 0.4

## Module 0.5 — Task Execution Foundation

### 0.5.a — Task Domain Models + Execution Specs

- [x] تحديث ExecutionAuthorization وScopeEvaluationResult بإضافة expires_at
- [x] توثيق Target-Bound وTime-Aware authorization contract
- [x] تعريف TaskId كـUUID4 typed identifier
- [x] تعريف TaskStatus وقواعد state machine الصارمة
- [x] تعريف EnvPolicy immutable value object
- [x] تعريف ExecutionSpec بقيود command/timeout/max_output/env
- [x] تعريف Task aggregate مع ScopeId وtimestamps وversion
- [x] فرض ExecutionAuthorization صالح لإنشاء Task
- [x] رفض raw target strings أو authorization غير المطابق/المنتهي
- [x] تطبيق الانتقالات PENDING → RUNNING → COMPLETED/FAILED/CANCELLED
- [x] تعريف typed errors للانتقالات والتفويض والـspec
- [x] كتابة pure unit tests للـTask وExecutionSpec والحالات الأمنية
- [x] تنفيذ boundary/security review دون subprocess أو migration أو repositories أو CLI
- [x] تشغيل pytest وRuff وmypy strict وformatting وwheel build
- [x] تحديث توثيق 0.5.a
- [x] إنشاء checkpoint لـ0.5.a

### 0.5.b — Safe Subprocess Execution Engine

- [x] تثبيت عقد SafeSubprocessRunner وحدود الطبقة دون تعديل Domain أو Persistence
- [x] تعريف ExecutionResult immutable value object: exit_code/stdout/stderr/truncated/duration/timeout_exceeded
- [x] تنفيذ argv-only عبر asyncio.create_subprocess_exec دون shell=True أو shell parsing
- [x] تطبيق EnvPolicy allowlist مع بيئة معزولة وعدم توريث المتغيرات الحساسة
- [x] تطبيق output cap مستقل وآمن لـstdout وstderr مع توثيق truncated
- [x] تطبيق timeout مع SIGTERM ثم SIGKILL عند عدم الاستجابة
- [x] ترجمة نتائج timeout والفشل إلى حالات typed قابلة للتدقيق دون تسريب stack traces
- [x] كتابة integration tests محلية محايدة لـecho وsleep وpython -c فقط
- [x] اختبار shell injection prevention كـarguments عادية
- [x] اختبار timeout/process killing وoutput truncation وenvironment isolation
- [x] تنفيذ boundary/security review دون migration أو repositories أو CLI أو network tools
- [x] تشغيل pytest وRuff وmypy strict وformatting وwheel build
- [x] تحديث توثيق 0.5.b
- [x] تنفيذ TaskExecutionEngine فوق SafeSubprocessRunner
- [x] تطبيق Task transition إلى RUNNING قبل التنفيذ
- [x] تطبيق COMPLETED عند exit_code == 0 وبدون timeout
- [x] تطبيق FAILED عند timeout أو exit_code != 0
- [x] كتابة integration tests لنتائج TaskExecutionEngine والانتقالات
- [x] تحديث تصميم 0.5.b وتوثيق Option A والحدود
- [x] إعادة تشغيل quality gates والمراجعة الأمنية النهائية
- [x] إنشاء checkpoint لـ0.5.b

### 0.5.c — Task Persistence & Migration 0004

- [x] نقل ExecutionResult إلى عقد Domain محايد مع re-export متوافق من execution.runner
- [x] تعريف TaskRecord immutable projection من Task وExecutionResult
- [x] تصميم واعتماد mapping بين Task/ExecutionResult وجدول tasks
- [x] تنفيذ 0004_tasks.sql دون IF NOT EXISTS أو معاملات داخلية
- [x] إضافة قيود status/timestamps/version/lengths وFK RESTRICT
- [x] إضافة json_valid checks لـcommand_json وenv_policy_json
- [x] إضافة status/result consistency checks لـpending/running/completed/failed/cancelled
- [x] إضافة فهارس scope/status وtarget/status
- [x] اختبار migration checksum وforward-only وatomic rollback
- [x] تنفيذ TaskMapper مع UUID/UTC/enums/optional fields round-trip
- [x] تنفيذ TaskRepository add/get/list_by_scope/list_by_target
- [x] تنفيذ update_status_and_result مع optimistic concurrency
- [x] حفظ واسترجاع ExecutionResult والمخرجات المقتطعة بأمان
- [x] تطبيق FK protection لـScope وTarget غير الموجودين
- [x] دمج repository مع UnitOfWork دون تسريب sqlite3.Row أو SQL
- [x] كتابة migration وrepository integration tests
- [x] تنفيذ boundary/security review دون CLI أو subprocess أو network tools
- [x] تشغيل pytest وRuff وmypy strict وformatting وwheel build
- [x] تحديث توثيق 0.5.c
- [x] إنشاء checkpoint لـ0.5.c

### 0.5.d — Task CLI & Full System Integration Audit

- [x] مراجعة CLI/Application boundaries وتصميم Task CLI contract
- [x] تثبيت transaction policy: pending commit ثم execution خارج transaction ثم terminal update
- [x] تثبيت safe JSON serialization للـbytes وexecution metadata
- [x] تنفيذ Task application service لتنسيق authorization وexecution وpersistence
- [x] فرض ExecutionAuthorization لكل task run دون direct execution bypass
- [x] إضافة `cyberos task run` مع argv explicit وtext/JSON envelopes
- [x] إضافة `cyberos task list` بترتيب deterministic حسب scope/target
- [x] إضافة `cyberos task show` مع stdout/stderr/exit_code والـexecution metadata
- [x] تطبيق exit codes: 0 نجاح، 1 input/domain error، 2 security rejection أو task failure
- [x] كتابة CLI integration tests للـrun/list/show وJSON/text/error handling
- [x] كتابة E2E audit على SQLite جديدة من migrations 0001–0004 حتى persistence
- [x] اختبار fail-closed لهدف EXCLUDED ورفض إنشاء/تنفيذ Task
- [x] اختبار argv shell-injection prevention عبر CLI integration
- [x] تنفيذ boundary/security review دون network tools أو Module 1 features
- [x] تشغيل pytest وRuff وmypy strict وformatting وwheel build
- [x] تحديث توثيق Module 0.5 وإغلاقه
- [x] إنشاء checkpoint لـ0.5.d وإغلاق Module 0.5

### Final Module 0 — Zero-State E2E Integration Audit

- [x] إنشاء قاعدة SQLite جديدة وتشغيل migrations 0001–0004
- [x] التحقق من quick_check وforeign_key_check وschema version
- [x] تدقيق Workspace → Engagement → Scope → Target hierarchy
- [x] اختبار include/exclude وFQDN/wildcard/IPv4/CIDR/URL matching
- [x] اختبار authorized Scope مع expires_at وExecutionAuthorization
- [x] اختبار Task.create وTaskExecutionEngine وSafeSubprocessRunner وTaskRecord persistence
- [x] تنفيذ CLI walkthrough لـscope/target/task run/list/show
- [x] اختبار JSON/text envelopes وexit codes 0/1/2
- [x] اختبار excluded/out-of-scope وdraft/expired Scope fail-closed
- [x] اختبار cross-target authorization reuse rejection
- [x] اختبار shell injection literal argv
- [x] اختبار optimistic concurrency stale version
- [x] كتابة `tests/e2e/test_full_system_pipeline.py`
- [x] توثيق known limitations/technical debt ونتيجة audit
- [x] تشغيل pytest وRuff وmypy strict وformatting وwheel build
- [x] حفظ checkpoint التراكمي وإغلاق Module 0 رسميًا

### GitHub Repository Setup — Portfolio & Production Grade

- [x] مراجعة حالة Git وREADME والملفات الحالية فوق checkpoint 80001bf3
- [x] كتابة README احترافي: badges وvision وarchitecture وroadmap وquickstart وsecurity policy
- [x] إضافة Mermaid/ASCII architecture يوضح Module 0 إلى Module 14
- [x] إضافة `.github/workflows/ci.yml` لـpytest وRuff وmypy strict وwheel build
- [x] تحديث `.gitignore` لقواعد البيانات والبيئات والكاش والأسرار وartifacts
- [x] إضافة MIT LICENSE
- [x] إضافة SECURITY.md لسياسة الإفصاح والاستخدام المصرح
- [x] مراجعة secrets وgenerated artifacts وعدم تضمين بيانات حساسة
- [x] تشغيل quality checks وCI-equivalent validation
- [x] توثيق أوامر commit وremote وpush دون تنفيذ push فعلي

### GitHub Remote & Push — malhiloo-byte/cyberHub

- [x] فحص الوصول إلى مستودع GitHub وحالة gh/git authentication
- [x] التحقق من local branch وworking tree وcommit c197ea9
- [x] إضافة remote باسم github دون تغيير remote origin المُدار
- [x] التحقق من default branch وremote refs قبل الرفع
- [x] رفع commit c197ea9 إلى GitHub دون force push أو history rewrite
- [x] التحقق من commit والـCI workflow بعد الرفع
- [x] توثيق أي إعدادات يدوية متبقية مثل branch protection وDependabot

### GitHub Push Retry — cyberHub

- [x] إعادة فحص GitHub authentication بعد إعادة المصادقة
- [x] التحقق من working tree وremote refs قبل retry
- [x] إعادة push آمن إلى `github/main` دون force
- [x] التحقق من commit وActions بعد النجاح أو توثيق سبب الفشل

### CyberOS Frontend Premium Redesign & Remaining Work

- [x] تدقيق واجهة React الحالية وتوثيق direction بصري فاخر ومتسق
- [x] إعادة بناء App shell: sidebar، topbar، responsive navigation، tokens
- [x] تصميم Dashboard حقيقي يعرض حالة النظام والـscope/task health
- [x] بناء لوحات Scopes وTargets وTasks وAudit Activity بحالات واضحة
- [ ] إضافة empty/loading/error states وkeyboard/focus accessibility
- [x] اختبار الواجهة بصريًا على desktop وmobile
- [x] إعداد وثيقة Architecture & Contracts لـModule 1 — Recon Orchestrator
- [x] توثيق قرارات GitHub governance المتبقية: branch protection وDependabot وVulnerability Reporting
- [x] تشغيل فحوصات النواة والواجهة
- [x] حفظ checkpoint بعد التسليم

### GitHub Premium Presentation Revision

- [x] إعادة صياغة README كواجهة منتج لا كملف كود فقط
- [x] إصلاح architecture rendering إلى ASCII متوافق مع GitHub
- [x] إضافة روابط مباشرة للـCommand Center وقرارات التصميم والـvisual verification
- [x] رفع revision النهائي إلى cyberHub والتحقق من CI
- [ ] تنفيذ GitHub repository presentation polish جديد ومحسّن — README فقط، دون تعديل React UI أو Python core

### Comprehensive Project Report

- [x] جمع chronology كاملة من checkpoints والقرارات المعمارية
- [x] توثيق كل Module وslice والملفات والواجهات والـschema
- [x] توثيق الأمن والحدود والـfail-closed والـthreat considerations
- [x] توثيق الاختبارات والـquality gates والأرقام الفعلية
- [x] توثيق GitHub commits وCI والواجهة والـdesign system
- [x] فصل المنجز الفعلي عن المخطط والقيود والـtechnical debt
- [x] إنشاء التقرير النهائي بصيغة Markdown وWord/HTML عند الإمكان
- [x] مراجعة التقرير وتسليمه مع الملفات المساندة

## Module 1 — Recon Orchestrator

### 1.0 — Recon Plugin Architecture & Contracts

- [x] اعتماد حدود الشريحة وعدم إعادة فتح Module 0
- [x] إعداد وثيقة التصميم المعماري والعقود قبل التنفيذ
- [x] تعريف Plugin identity وmanifest وversioning وcontract versioning
- [x] تعريف capability model وinput/output contracts وsupported target kinds
- [x] تعريف authorization وresource/timeout/output limits فوق عقود Task الحالية
- [x] تعريف lifecycle وcompatibility وdeterministic ReconResult وtyped error model
- [x] تنفيذ Plugin boundary لا يسمح بتجاوز Scope أو Target أو Authorization أو Task controls
- [x] تنفيذ Offline Fixture Plugin بلا network أو subprocess أو external APIs
- [x] كتابة contract/security tests للتوافق والفشل والـmanifest والـcapabilities
- [x] تشغيل full regression وpytest وRuff وformat وmypy strict وwheel build
- [x] توثيق unresolved architectural decisions قبل الإغلاق
- [x] طلب الموافقة على التصميم قبل تنفيذ العقود والـfixture

## Master Project Specification Compliance Audit

- [x] استخراج المتطلبات والادعاءات القابلة للتحقق من الملف المرفق
- [x] مقارنة الحالة الفعلية مع checkpoints والملفات والاختبارات
- [x] التحقق التشغيلي من quality gates والحدود الأمنية الحالية
- [x] توثيق المطابق والمنجز والفجوات والأولويات دون تعديل المشروع

## Module 1.0 — Synchronization & Cleanup Pass

- [x] إضافة اختبارات unknown manifest fields وunsupported major contract
- [x] توسيع edge-case coverage للـplugin boundary
- [x] توثيق `cyberos/core/plugins.py` كـLegacy Compatibility Layer
- [x] تحديث README إلى إغلاق Module 1.0 وعدد 293+ اختبارًا
- [x] تشغيل pytest وRuff وformat وmypy strict وwheel build
- [x] إنشاء commit نظيف ورفع `main` إلى `github/main`
- [x] التحقق من GitHub Actions ورفع checkpoint بعد النجاح

## Module 1.1 — Recon Data Models & Persistence Architecture Design Review

- [x] تثبيت حدود Module 1.1 ومفردات Recon Assets فوق Module 1.0
- [x] تصميم Domain aggregates وvalue objects وفصلها عن SQLite
- [x] إعداد Draft DDL لـ0005_recon_assets.sql دون تنفيذ
- [x] تحديد القيود والفهارس وFK/RESTRICT وسياسات integrity
- [x] تصميم data flow وER diagram والعلاقات مع Task/Target/Scope
- [x] تصميم deduplication وcorrelation وupsert strategy
- [x] تصميم ReconRepositoryPort وSQLiteReconRepository وUnitOfWork boundaries
- [x] تصميم structured/raw artifact retention strategy
- [x] إعداد test strategy وsecurity boundary protections
- [x] توثيق القرارات المفتوحة وطلب اعتماد التصميم قبل أي كود

## Module 1.1 — Implementation

- [x] تنفيذ migration 0005 عبر MigrationRunner دون تعديل 0001–0004
- [x] تنفيذ Domain models وvalue objects وtyped errors
- [x] تنفيذ mappers وReconRepositoryPort وSQLiteReconRepository
- [x] تنفيذ ReconIngestionService مع authorization/target/scope guards
- [x] إضافة migration/schema/FK/constraint/rollback tests
- [x] إضافة correlation/idempotency/round-trip/concurrency tests
- [x] إضافة security boundary وstatic forbidden-side-effect tests
- [x] تشغيل full regression وpytest وRuff وformat وmypy strict وwheel build
- [ ] حفظ checkpoint فقط بعد نجاح جميع البوابات
- [ ] تسليم تقرير Module 1.1 والتوقف قبل Module 1.2

## Module 1.2 — Recon Execution Orchestration Architecture Design Review

- [x] تثبيت حدود orchestration فوق PluginHost وReconIngestionService وTask
- [x] تصميم pipeline flow وplugin chaining وتمرير assets بأمان
- [x] تصميم orchestrator interfaces وحدود الخدمات
- [x] تصميم Task lifecycle matrix وIngesting state semantics
- [x] تصميم UnitOfWork وatomic ingestion per plugin output
- [x] تصميم partial failure وcancellation وrecovery rules
- [x] تصميم authorization/resource/timeout/max-assets/max-payload enforcement
- [x] إعداد security verification strategy وboundary tests
- [x] توثيق القرارات المفتوحة وطلب اعتماد التصميم قبل أي كود

## Module 1.2 — Implementation

- [x] حسم تعارض Task PENDING/RUNNING واعتماد `invoke_running` additive host extension
- [x] اعتماد ReconTaskResultAdapter كجسر محايد وصادق إلى ExecutionResult دون migration
- [x] تنفيذ ReconTaskResultAdapter مع Pipeline Summary JSON وredacted stderr وexit-code semantics
- [x] تنفيذ PipelineDefinition وPipelineStepDefinition وPipelineContext وExecutionReport
- [x] تنفيذ PipelineBudget وCancellationSignal وephemeral PipelinePhase
- [x] تنفيذ PipelineInputResolver بحدود Scope/Target وasset-kind
- [x] تنفيذ ReconPipelineOrchestrator فوق PluginHost وReconIngestionService
- [x] تنفيذ per-step atomic ingestion وpartial failure isolation
- [x] تنفيذ cancel-before-ingest وcumulative budget enforcement
- [x] إضافة chaining/scope isolation/limits/atomicity/cancellation/audit redaction tests
- [x] تشغيل full regression وpytest وRuff وformat وmypy strict وwheel build
- [x] حماية Modules 0 و1.0 و1.1 وعدم إضافة migration أو network/subprocess
- [x] حفظ checkpoint فقط بعد نجاح جميع البوابات والتوقف قبل Module 1.3

## Module 1.3 — Next Slice Planning (Not Started)

- [x] استخراج نطاق Module 1.3 من roadmap2(1).html وسجل المشروع الحالي
- [x] تحديد purpose وnon-goals والاعتماديات والواجهات مع Module 1.2
- [x] إعداد وثيقة التصميم المعماري والاختبارات الأمنية قبل أي تنفيذ
- [x] الحصول على اعتماد صريح للتصميم والقرارات المعمارية

## Module 1.3 — Recon Evidence & Provenance Ledger Implementation

- [x] تنفيذ Migration 0006 عبر MigrationRunner مع checksum وforward-only checks
- [x] تنفيذ EvidenceId وEvidenceKind وEvidenceStatus وEvidenceRecord
- [x] تنفيذ EvidenceFactory مع authorization/provenance/metadata guards
- [x] تنفيذ ReconEvidenceRepositoryPort وSQLite mapper/repository
- [x] تنفيذ archive-only lifecycle وoptimistic concurrency
- [x] ربط إنشاء Evidence بنتائج ReconIngestion الملتزمة داخل UnitOfWork قصير
- [x] إضافة migration/domain/repository/provenance/idempotency/security tests
- [x] تشغيل full regression وRuff وformat وmypy strict وwheel build وboundary scan
- [x] مراجعة عدم تعديل Modules 0 و1.0 و1.1 و1.2 وعدم إضافة network/subprocess
- [x] رفع commit والتحقق من GitHub Actions
- [x] حفظ checkpoint وتسليم تقرير Module 1.3 والتوقف قبل Module 1.4
