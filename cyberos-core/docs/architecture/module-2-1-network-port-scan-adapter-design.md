# Module 2.1 — Network & Port Scanning Adapter Boundary

**الحالة:** Approved and implemented — offline slices 2.1.a–2.1.e closed; Slice 2.1.f live tool integration not authorized  
**Baseline:** Module 2.0 مغلق ومعتمد عند checkpoint `bb43eb53`، بإجمالي 370 اختبارًا وCI أخضر  
**النطاق:** adapter واحد لفحص الشبكات/المنافذ، مع parser offline حتمي فقط  
**قاعدة الهجرة:** لا توجد Migration جديدة؛ يبقى المخطط عند 0006  
**قاعدة التنفيذ في هذه الشريحة:** لا تشغيل Nmap أو أي port scanner، لا network sockets، لا DNS/HTTP، لا subprocess execution، ولا external API

> هذه الوثيقة تصمم حدود adapter متخصص لفحص الشبكات والمنافذ فوق Module 2.0. وهي لا تمنح صلاحية تشغيل أداة حقيقية، ولا تعتمد اسم أداة أو نسخة تنفيذية قبل مراجعة manifest واختبارات parser وطلب اعتماد مستقل.

## 1. الهدف والحدود

يهدف Module 2.1 إلى تعريف طبقة آمنة ومحدودة لأداة واحدة فقط من فئة Network/Port Scanning. القيمة المطلوبة ليست إعادة بناء scanner؛ بل ربط أداة ناضجة مستقبلًا بمنظومة CyberOS بطريقة تحفظ Scope وTarget وTask وExecutionAuthorization وObservations وEvidence، وتمنع أن يتحول adapter إلى قناة تنفيذ عامة أو مصدر غير موثوق لتوسيع نطاق الفحص.

المسار المقترح هو بناء **Network Port Scan Adapter Contract** مع دعم parser offline لمخرجات machine-readable. التنفيذ الحي، اختيار الأداة الفعلية، وتثبيت binary على الجهاز ليست جزءًا من هذه الخطوة. إذا اختير Nmap لاحقًا، فسيكون ذلك تنفيذًا لmanifest معتمد، وليس افتراضًا ضمن هذه الوثيقة.

| داخل النطاق | خارج النطاق |
|---|---|
| AdapterManifest immutable ومحدد لأداة واحدة | تشغيل Nmap أو Masscan أو أي scanner حقيقي |
| executable identity وcontract version | تثبيت binaries أو اكتشافها عبر PATH |
| allowlist صارمة للـflags | flags عامة أو arbitrary command options |
| target grammar لـIPv4 وIPv6 وCIDR وFQDN وفق TargetKind | wildcard targets أو target lists غير المصرح بها |
| context alignment مع Scope/Target/Task/Authorization | إنشاء أو تجديد authorization |
| XML/JSON offline parser contract | live XML/JSON stream من شبكة حقيقية |
| deterministic positive/negative fixtures | network sockets أو DNS أو HTTP |
| redaction وbounded parsing وtyped failures | raw artifact persistence أو filesystem exporter |
| mapping design إلى ReconObservation/Evidence | تعديل migrations أو schema 0006 |
| test matrix وthreat model | retries أو background daemon أو scan scheduling |

## 2. العلاقة مع Module 2.0

Module 2.1 لا ينشئ execution model جديدًا. فهو يضيف تعريفًا متخصصًا فوق `CommandSandbox` و`LiveSubprocessAdapter` الموجودين في Module 2.0، ويجعل command construction وoutput parsing أكثر صرامة بالنسبة لأداة port scanning.

```text
Task + ExecutionAuthorization + Scope/Target
                    │
                    ▼
          NetworkScanInvocation
                    │
                    ▼
          AdapterManifest validation
                    │
                    ▼
 CommandSandbox: argv/target/flag/limit checks
                    │
         [future approved live execution]
                    ▼
       LiveSubprocessAdapter (Module 2.0)
                    │
                    ▼
       bounded machine-readable receipt
                    │
                    ▼
    redaction → offline-compatible parser
                    │
                    ▼
     context validation + normalized records
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
   ReconObservation       Evidence service
   / asset ingestion      / provenance ledger
```

الـadapter المتخصص لا يستدعي repository أو Evidence مباشرة أثناء process execution. وظيفته إنتاج invocation plan وparser result. أما orchestration والمعاملات وحفظ الأصول والأدلة فتظل في Application services المعتمدة.

## 3. AdapterManifest

### 3.1 العقد المقترح

`NetworkPortScanAdapterManifest` هو projection immutable يصف هوية الأداة، النسخة، output contract، target grammar، flags، limits، وسياسة child process. لا يُسمح بتحويل manifest من JSON غير موثوق إلى executable policy دون validation صريح.

```text
NetworkPortScanAdapterManifest(
  adapter_id: str,
  display_name: str,
  adapter_version: SemVer,
  contract_version: ContractVersion,
  executable_id: str,
  executable_absolute_path: str,
  supported_target_kinds: tuple[TargetKind, ...],
  output_format: MachineOutputFormat,
  output_contract_version: str,
  fixed_flags: tuple[str, ...],
  allowed_flags: tuple[FlagRule, ...],
  required_flags: tuple[str, ...],
  forbidden_flags: tuple[str, ...],
  max_targets_per_invocation: int,
  max_ports_per_invocation: int,
  max_timeout_seconds: int,
  max_output_bytes: int,
  max_observations: int,
  supports_child_processes: bool,
  supports_background_mode: bool,
)
```

الـmanifest لا يحمل `ExecutionAuthorization` ولا يملك صلاحية تنفيذ. كما أن `executable_absolute_path` تعريف reviewed identity فقط؛ لا يعني أن binary موجود أو صالح للتشغيل قبل وصول Module 2.0 إلى مرحلة spawn المصرح بها.

### 3.2 القواعد الإلزامية للهوية

| الحقل | القاعدة |
|---|---|
| `adapter_id` | معرف lowercase محدود، ثابت، غير قابل لتضمين path أو command syntax |
| `adapter_version` | Semantic Versioning؛ تغيير behavior الأمني أو parser major يتطلب contract review |
| `contract_version` | Major/minor؛ اختلاف major مرفوض، وminor المستقبلية غير مقبولة تلقائيًا |
| `executable_id` | logical identity منفصلة عن path، ولا تعتمد على PATH |
| `executable_absolute_path` | absolute reviewed path؛ لا يقبل shell syntax أو path يحدده plugin |
| `output_format` | قيمة مغلقة: XML أو JSON، ولا يسمح plain text في هذا module |
| `output_contract_version` | نسخة parser مستقلة عن نسخة binary |
| `supported_target_kinds` | subset معلن من `FQDN`, `IPV4`, `IPV6`, `CIDR` فقط في البداية |
| `supports_child_processes` | يجب أن تكون False في أول contract slice |
| `supports_background_mode` | يجب أن تكون False دائمًا في Module 2.1 |

### 3.3 اختيار format

يقترح التصميم دعم **format واحد لكل manifest**، لا تفاوض runtime بين XML وJSON. يمكن تعريف manifestين منفصلين لنفس الأداة في المستقبل، لكن كل invocation يملك format واحدًا ثابتًا يعرفه parser مسبقًا. إذا خرجت الأداة بصيغة مختلفة، فالنتيجة `PORT_SCAN_OUTPUT_CONTRACT_INVALID` ولا يحدث ingestion.

## 4. Strict flag allowlist

### 4.1 المبدأ

لا يبني adapter command من نص shell. كل flag وقيمة هو عنصر argv مستقل، وكل option يجب أن يكون معروفًا في manifest. لا يسمح Module 2.1 بتمرير flags من المستخدم مباشرة إلا بعد تحويلها إلى typed request fields ومطابقتها مع قواعد manifest.

### 4.2 المجموعة الأولية المقترحة

الأسماء التالية **تصميمية** وليست authorization لتشغيل Nmap أو أي أداة. إذا استُخدم Nmap لاحقًا، يجب ربط هذه المعاني بصيغة tool-specific موثقة واختبارها ضد binary معتمد.

| الفئة | القاعدة المقترحة | القرار |
|---|---|---|
| Scan mode | `-sS` فقط إذا كانت بيئة التنفيذ والتفويض تسمح به صراحة | allowlist مشروطة، لا default implicit |
| Port selection | `-p` مع typed port expression محدودة | allowlist؛ لا raw string |
| Timing | `-T4` أو قيمة زمنية مغلقة أدنى/أعلى | لا يقبل timing حرًا |
| Output mode | machine-readable XML/JSON flag ثابت من manifest | required؛ لا stdout human text |
| Output destination | stdout stream فقط في هذا module | أي `-o*` إلى ملف مرفوض |
| Input target | positional target واحد أو field موحد يساوي canonical target | لا target list |
| Script/plugin loading | أي NSE/plugin/script flag مرفوض | لا arbitrary extension code |
| Interface/source | flags التي تغيّر interface أو source address مرفوضة أوليًا | تحتاج design مستقل |
| Host discovery | لا `-Pn` أو ما شابه إلا إذا أُضيفت قاعدة منفصلة | default deny |
| Privilege/prefix | لا `sudo`, `doas`, shell wrapper أو privilege escalation | مرفوض بنيويًا |
| Randomization | أي randomization flag مرفوض في deterministic contract | مرفوض |

### 4.3 منع التوسيع الضمني

القواعد التالية حاسمة:

1. لا يسمح parser أو user input بإضافة flag غير موجودة في manifest.
2. لا يتم حذف flag خطرة silently؛ بل يفشل الطلب بـ`PORT_SCAN_FLAG_NOT_ALLOWED`.
3. لا يتم استبدال target بآخر “أكثر أمانًا” تلقائيًا.
4. لا يتم رفع port/timeout/output budgets إلى الحد الأعلى بصمت.
5. لا يتولد shell command string لأغراض logging أو execution.
6. لا يسمح argument grammar بالـ`;`, `|`, `&`, `>`, `<`, `$()`, backticks، newline، أو null bytes.
7. لا يعتبر `--` وحده boundary كافيًا إذا كانت القيمة بعده غير مرتبطة بالtarget authorized.

## 5. Target grammar وScope alignment

### 5.1 target kinds المسموحة

تبدأ الصيغة الأولى بالأنواع التي يمكن ربطها مباشرة بـTarget domain:

| TargetKind | الحالة في Module 2.1 | قيود أولية |
|---|---|---|
| `IPV4` | مدعوم | عنوان واحد؛ canonical parser؛ لا broadcast/reserved policy غير موثقة |
| `IPV6` | مدعوم بعد parser validation | عنوان واحد؛ canonical bracket/zone rules محددة مسبقًا |
| `CIDR` | مدعوم بحدود صارمة | prefix ضمن حد host-count؛ لا ranges ضخمة |
| `FQDN` | مدعوم | DNS label grammar؛ لا wildcard أو trailing ambiguity |
| `WILDCARD` | مرفوض | لا يفوض scanner باكتشاف نطاق غير محدد |
| `URL` | مرفوض | Module 2.1 ليس HTTP adapter |

### 5.2 canonical grammar

يجب أن يقوم target domain الحالي بإنتاج canonical target. Adapter parser لا يخترع canonicalization مستقلة قد تؤدي إلى اختلاف بين authorization وcommand. قبل spawn، تُراجع القواعد التالية:

```text
TargetContext.scope_id == Task.scope_id == ExecutionAuthorization.scope_id
TargetContext.target_id == Task.target_id == ExecutionAuthorization.matched_target_id
TargetContext.kind ∈ manifest.supported_target_kinds
TargetContext.canonical_value == authorized candidate value
TargetContext.rule == INCLUDE
TargetContext.status == ACTIVE
Scope.status == AUTHORIZED
authorization.expires_at is absent or > current UTC instant
```

ويُرفض ما يلي قبل CommandSandbox أو spawn:

| الحالة | النتيجة |
|---|---|
| wildcard target | `PORT_SCAN_TARGET_INVALID` |
| malformed IPv4/IPv6/CIDR/FQDN | `PORT_SCAN_TARGET_INVALID` |
| CIDR يتجاوز host/asset budget | `PORT_SCAN_LIMIT_EXCEEDED` |
| target على Exclude list | `LIVE_ADAPTER_UNAUTHORIZED` أو error typed مكافئ |
| target لا يساوي candidate authorized | `LIVE_ADAPTER_CONTEXT_MISMATCH` |
| target ID مختلف مع نفس القيمة | `LIVE_ADAPTER_UNAUTHORIZED` |
| Scope/Target archived | رفض قبل spawn |
| authorization expired | `LIVE_ADAPTER_UNAUTHORIZED` |
| target list أو comma-separated targets | رفض؛ invocation واحد لكل target |
| hostname غير FQDN أو يحمل shell syntax | رفض grammar |

### 5.3 CIDR limits

CIDR ليس تصريحًا لفحص كل المساحة الممكنة. قبل إنشاء invocation يجب حساب host cardinality أو equivalent bounded estimate. إذا تجاوز الناتج الحد، يفشل الطلب دون split تلقائي أو queue خلفية أو retry. أي سياسة لتقسيم CIDR إلى Tasks منفصلة تحتاج approval وتصميمًا مستقلًا لأنها تغيّر audit/provenance semantics.

## 6. Invocation contract

### 6.1 NetworkScanInvocation

العقد المقترح additive فوق `LiveSubprocessRequest` هو:

```text
NetworkScanInvocation(
  task: Task,
  authorization: ExecutionAuthorization,
  scope_id: ScopeId,
  target_id: TargetId,
  target_kind: TargetKind,
  canonical_target: str,
  manifest_id: str,
  ports: tuple[int, ...],
  scan_mode: ScanMode,
  timing_profile: TimingProfile,
  output_format: MachineOutputFormat,
  timeout_seconds: int,
  max_output_bytes: int,
)
```

الـcaller لا يمرر `flags: str` ولا `raw_command`. يقوم adapter builder بتحويل الحقول typed إلى argv وفق manifest. وبعد البناء، يجب أن يثبت equality بين command produced وTask execution spec إذا كان Task قد تم إنشاؤه بهذا الأمر، أو يرفض invocation بدل تعديل Task لاحقًا.

### 6.2 Port grammar

`ports` typed tuple من أعداد صحيحة unique ومرتبة، ضمن 1–65535، مع حد أقصى manifest/Task. لا يقبل هذا العقد ranges نصية، commas، `-`, `*`, أو expressions. إذا احتاجت أداة لاحقًا port range، فتنشئ طبقة parser typed تحولها إلى مجموعة bounded ports قبل بناء command، ولا تمرر النص الخام للأداة.

## 7. Offline parser contract

### 7.1 مبدأ parser

الـparser يجب أن يكون pure/read-only/deterministic. يأخذ bounded redacted bytes وmetadata contract، ويعيد normalized result أو typed failure. لا ينفذ subprocess، لا يتصل بالشبكة، لا يكتب filesystem، ولا يستدعي parser extensions ديناميكية.

```text
parse(
  payload: bytes,
  *,
  expected_format: MachineOutputFormat,
  expected_contract_version: str,
  scope_id: ScopeId,
  target_id: TargetId,
  canonical_target: str,
  limits: ParserLimits,
) -> NetworkScanParseResult
```

### 7.2 NetworkScanParseResult

```text
NetworkScanParseResult(
  schema_version: str,
  adapter_id: str,
  target: ParsedTarget,
  hosts: tuple[ParsedHost, ...],
  services: tuple[ParsedPortService, ...],
  observations: tuple[ReconObservationCandidate, ...],
  source_digest: str,
  redaction_applied: bool,
  synthetic: bool,
  offline_fixture: bool,
  complete: bool,
)
```

في production live path تكون `synthetic=False` و`offline_fixture=False` بعد تشغيل حقيقي معتمد. أما fixtures في Module 2.1 design/test stage فيجب أن تحمل `synthetic=True` و`offline_fixture=True`، ويجب ألا تُخلط مع Evidence live دون marker واضح.

### 7.3 XML contract

إذا كان format XML، يجب قبول envelope root محدد، namespace/version محدد، وعناصر allowlisted فقط. القواعد المقترحة:

| العنصر | policy |
|---|---|
| root | اسم/نسخة متوقعة؛ mismatch يرفض |
| host/address | عنوان واحد مرتبط بـauthorized target؛ لا inference لهدف جديد |
| ports/port | port number typed، protocol من closed enum |
| state | closed enum مثل open/closed/filtered إذا اعتمدها manifest |
| service | name/product/version bounded text؛ لا raw banners غير محدودة |
| script/plugin output | مرفوض في أول slice |
| comments/processing instructions | مرفوضة أو متجاهلة فقط بسياسة موثقة؛ لا external entity resolution |
| unknown required structure | fail-closed |

يجب تعطيل external entity resolution، وعدم قبول include/import خارجي، وعدم تحميل paths أو URLs من XML. الحجم، العمق، عدد العناصر، طول النصوص، وعدد الخدمات لها budgets صريحة.

### 7.4 JSON contract

إذا كان format JSON، يجب قبول object envelope محدد مع `schema_version`, `target`, و`hosts`/`ports` allowlisted. `additionalProperties` policy تكون مغلقة للحقول الجوهرية. Unknown enum، wrong type، duplicate semantic records، أو target mismatch يؤدي إلى `PORT_SCAN_PARSE_FAILED` أو `PORT_SCAN_SCHEMA_UNSUPPORTED`.

لا يقبل parser JSON يحتوي nested arbitrary payloads أو raw response bodies أو command/authorization fields. لا يسمح بتحويل arbitrary JSON keys إلى Observation types.

## 8. Offline fixtures

### 8.1 fixture families

قبل أي live execution، يجب توفير fixtures deterministic في الاختبارات دون كتابة raw fixtures إلى runtime storage:

| Fixture | الغرض | النتيجة المتوقعة |
|---|---|---|
| valid IPv4 XML | host واحد ومنافذ open/closed | normalized services وobservations |
| valid FQDN JSON | target مطابق وservice metadata bounded | نجاح parsing |
| valid bounded CIDR result | مجموعة hosts ضمن حد صغير | نجاح مع counters دقيقة |
| target mismatch | output يذكر target مختلفًا | رفض context وعدم ingestion |
| excluded target marker | invocation context غير مصرح | رفض قبل parser أو قبل ingestion |
| malformed XML | root/namespace أو structure invalid | typed parse failure |
| malformed JSON | wrong types أو missing required fields | typed parse failure |
| schema version mismatch | major version مختلف | reject دون downgrade |
| oversized envelope | payload/hosts/ports يتجاوز limits | `PORT_SCAN_LIMIT_EXCEEDED` |
| truncated stream | receipt يحمل truncation | no successful Observation/Evidence |
| secret/path leakage | synthetic banner أو metadata فيها secret/path | redaction ثم assertion عدم التسريب |
| duplicate services | نفس identity مكررة | deterministic dedup أو typed rejection وفق contract |
| unsupported flags metadata | fixture لا يغير command لكن يثبت policy | رفض command construction |

### 8.2 fixture non-pollution

Fixtures لا تنشئ migrations ولا تكتب filesystem ولا تملأ live Evidence repository افتراضيًا. إذا احتاجت الاختبارات إثبات ingestion، يجب أن تستخدم قاعدة test SQLite موجودة ضمن الاختبار، وتثبت marker `synthetic/offline_fixture`، وتتحقق من context/provenance. لا يجوز أن تُفسر fixture كدليل على أن live network execution تم.

## 9. Redaction وbounded parsing

يُطبق redaction قبل error message أو audit metadata أو parser diagnostics. يمنع على parser الاحتفاظ بـraw banner أو raw output غير محدود. الحقول المسموحة هي normalized scalar values ذات أطوال محددة.

| البيانات | policy |
|---|---|
| credentials/tokens/cookies/headers | `[REDACTED]`؛ لا تُحفظ raw |
| local paths | `[PATH_REDACTED]` |
| raw service banners | مرفوضة أو تختزل إلى bounded normalized field |
| command line | لا تظهر في errors أو Evidence |
| XML/JSON raw body | ephemeral bounded bytes فقط؛ لا filesystem persistence |
| unknown fields | لا تُنسخ تلقائيًا إلى metadata |
| target identity | تحفظ فقط بصيغة authorized canonical value/ID المطلوبة للسياق |

إذا فشل redaction أو decoding أو حدود payload، فلا ينشئ parser Observation. ولا يجوز اعتبار output truncated صالحًا لمجرد أن جزءًا منه قابل للقراءة.

## 10. Mapping إلى ReconObservation وEvidence

### 10.1 Observation candidates

يقترح mapping closed vocabulary، مثل:

| Observation type | الحقول المسموحة |
|---|---|
| `network.host` | authorized target/host identity، address kind، bounded status |
| `network.port` | port number، protocol enum، state enum |
| `network.service` | port reference، service name، bounded product/version |
| `network.scan_summary` | counts، format/version، digest، completion flags |

لا يسمح output parser بإنشاء `network.target_discovered` من host غير موجود في authorized context. أي host إضافي يظهر في CIDR result يجب أن يكون ضمن CIDR المحقق مسبقًا وبحدود invocation؛ وإلا يُرفض كامل output أو يعزل حسب policy صريحة، والافتراضي هو الرفض الكامل.

### 10.2 Provenance invariants

كل Observation مرشح يحمل نفس `task_id`, `scope_id`, و`target_id` للـinvocation. ثم تمر النتائج عبر `ReconIngestionService` وEvidence service الحالية، دون إدخال repository مباشرة من parser. يجب أن تتحقق الطبقة التالية من:

```text
observation.scope_id == task.scope_id == authorization.scope_id
observation.target_id == task.target_id == authorization.matched_target_id
observation.task_id == current Task.id
source_digest is present and deterministic
raw payload is not persisted
```

إن فشل أي invariant، لا يحدث partial Evidence. المعاملة atomic لكل accepted adapter result، وتبقى النتائج السابقة الملتزمة محفوظة كما هو مقرر في Module 1.2.

### 10.3 Evidence policy

Evidence يحمل digest وmetadata محدودة وprovenance tuple، وليس XML/JSON raw. `synthetic` و`offline_fixture` markers مطلوبة في fixtures، ولا تُستخدم لادعاء live observation. أي error أو malformed output ينتج receipt typed مؤقتًا ولا ينشئ Evidence.

## 11. Limits وlifecycle

Effective limits هي تقاطع Task policy وModule 2.0 adapter policy وModule 2.1 manifest policy وrequest policy. طلب value أعلى من hard limit يفشل؛ لا يوجد silent clamping.

| الحد | policy أولية |
|---|---|
| targets | target واحد لكل invocation |
| CIDR cardinality | حد manifest صغير ومعلن؛ لا split تلقائي |
| ports | tuple typed unique bounded |
| timeout | ≤ Task وModule 2.0 وmanifest |
| stdout/stderr | bounded bytes مستقلان |
| XML/JSON depth | حد parser ثابت |
| hosts/services/observations | bounded counters |
| field length | bounded UTF-8 text |
| concurrency | invocation واحد؛ لا background daemon |
| retries | صفر |
| backoff/sleep | صفر خارج timeout termination primitive |

عند timeout أو output truncation أو malformed parser result، يعود adapter بفشل typed. لا retry، لا downgrade للـoutput version، لا تغيير للـscan mode، ولا auto-auth renewal.

## 12. Error model المقترح

إضافة الأكواد التالية إلى `ErrorCode` ليست جزءًا من هذه الوثيقة design-only، لكنها تحتاج approval قبل implementation:

| ErrorCode | trigger |
|---|---|
| `PORT_SCAN_MANIFEST_INVALID` | manifest أو version أو executable policy غير صالح |
| `PORT_SCAN_FLAG_NOT_ALLOWED` | flag غير موجودة في allowlist |
| `PORT_SCAN_TARGET_INVALID` | target grammar أو canonicalization failure |
| `PORT_SCAN_TARGET_UNAUTHORIZED` | Scope/Target/Authorization mismatch أو exclusion |
| `PORT_SCAN_LIMIT_EXCEEDED` | CIDR/ports/timeout/output/parser budget تجاوز |
| `PORT_SCAN_OUTPUT_CONTRACT_INVALID` | format/envelope/contract mismatch |
| `PORT_SCAN_PARSE_FAILED` | XML/JSON malformed أو type/field validation failure |
| `PORT_SCAN_SCHEMA_UNSUPPORTED` | major output contract unsupported؛ لا downgrade |
| `PORT_SCAN_CONTEXT_MISMATCH` | output target أو observation context لا يطابق authorization |
| `PORT_SCAN_REDACTION_FAILED` | فشل privacy boundary |
| `PORT_SCAN_INGESTION_REJECTED` | ReconIngestion/Evidence parent invariant رفض النتيجة |
| `PORT_SCAN_TRUNCATED_OUTPUT` | receipt incomplete؛ لا successful ingestion |

رسائل الخطأ redacted ولا تكشف raw target payload، command line، path، environment، raw XML/JSON، traceback، أو SQL.

## 13. Threat model

يغطي التصميم المخاطر التالية:

| التهديد | الضابط |
|---|---|
| فحص target خارج Scope | mandatory context equality + Include-only + expiry check |
| wildcard/CIDR expansion غير المقصود | target grammar وcardinality limits وone target per invocation |
| command injection | typed fields، argv-only، flag allowlist، shell syntax rejection |
| arbitrary scanner mode | closed scan/timing/output vocabulary |
| output-based target widening | parser لا ينشئ target/authorization؛ context validation قبل ingestion |
| XML entity/path/network fetch | no external entity resolution أو include/import |
| JSON schema confusion | closed envelope/version/field/type validation |
| memory exhaustion | bounded bytes/depth/counts/field sizes |
| secret leakage | redaction قبل logging/Evidence وعدم raw persistence |
| false Evidence من truncated data | truncation fail-closed |
| hidden persistence | parser pure؛ لا filesystem ولا raw artifact store |
| background scanning | manifest `supports_background_mode=False` وno daemon |
| retry-based scope drift | no retry/negotiation/auth renewal |

## 14. Test strategy بعد اعتماد التصميم

التنفيذ اللاحق يجب أن يضيف tests قبل أي live binary integration. كل الاختبارات الأولى تستخدم bytes fixtures وin-process parser، ويمكن أن تستخدم neutral local process double فقط إذا أُعيد اعتماد ذلك ضمن implementation plan.

| Test family | الحالات الإلزامية |
|---|---|
| Manifest | unknown fields، duplicate flags، unsupported format، version mismatch، relative executable path |
| Flags | allowed `-p` grammar، forbidden scan mode، output-to-file flag، script/plugin flag، shell syntax |
| Targets | valid IPv4/IPv6/CIDR/FQDN، wildcard، malformed values، target list، CIDR over-budget |
| Authorization | cross-Scope، cross-Target، expiry، Exclude، archived Scope/Target، mismatched canonical target |
| Command construction | deterministic argv، no shell string، target exactly once، no unreviewed PATH |
| XML parser | valid fixture، malformed root، external entity attempt، unknown required field، duplicate records |
| JSON parser | valid fixture، wrong type، unknown version، missing field، extra raw payload |
| Bounded parsing | oversized bytes، deep nesting، too many hosts/ports/services، truncated receipt |
| Redaction | credentials، paths، raw banners، control bytes، no leakage in typed errors |
| Normalization | deterministic output digest، stable ordering، dedup identity، closed enums |
| Provenance | Observation context، Evidence parent tuple، no raw payload persistence |
| Atomicity | accepted step commits; failed parser/context step does not ingest; previous commits remain |
| Policy | no retry/sleep/backoff/negotiation/daemon/auth renewal |
| Boundary scan | no network/socket/subprocess in parser; no file writes; no dynamic plugin loading |
| Regression | جميع اختبارات Modules 0–2.0، baseline 370 tests، تبقى ناجحة |

## 15. Implementation slices المقترحة بعد approval

لمنع توسع النطاق، يقسم التنفيذ التالي إلى شرائح مستقلة:

1. **2.1.a — Manifest and typed request contracts:** لا process ولا parser persistence.
2. **2.1.b — Target and flag policy:** pure validation مع tests شاملة.
3. **2.1.c — Offline XML/JSON parser:** fixtures deterministic، لا live execution.
4. **2.1.d — Observation/Evidence bridge:** ingestion atomicity وprovenance tests.
5. **2.1.e — Neutral adapter harness:** process double فقط، دون scanner binary.
6. **2.1.f — Separate live tool approval:** تصميم مستقل للأداة الفعلية، manifest النهائي، binary identity، وauthorized lab test.

لا يجوز الانتقال إلى 2.1.f بمجرد نجاح parser fixtures؛ نجاح offline parser لا يثبت سلامة live scan أو صلاحية الأداة على أهداف حقيقية.

## 16. قرارات تتطلب اعتمادًا صريحًا

| القرار | الاختيار المقترح |
|---|---|
| عدد الأدوات | أداة port scanning واحدة فقط في Module 2.1 |
| التنفيذ الحي | غير مصرح في هذه الشريحة؛ offline parser أولًا |
| output format | XML أو JSON لكل manifest، دون runtime negotiation |
| target scope | IP/CIDR/FQDN المصرح بها؛ wildcard وURL مرفوضان |
| target invocation | target واحد لكل Task/invocation؛ لا target list |
| flags | closed typed allowlist؛ no raw flags أو arbitrary scripts |
| output destination | bounded stdout فقط؛ لا file exporter |
| parser | pure deterministic parser مع closed schema/version |
| redaction | قبل logs/errors/Evidence؛ raw payload لا يُحفظ |
| provenance | إعادة استخدام ReconIngestionService وEvidence contracts الحالية |
| limits | fail-closed؛ لا silent clamp أو CIDR split |
| lifecycle | no retry، no daemon، no background، no auth renewal |
| database | zero migrations؛ schema remains 0006 |
| approval boundary | لا live tool integration قبل design مستقل وexplicit approval |

## 17. Approval gate وstop condition

تم اعتماد هذا التصميم صراحة، ثم نُفذت الشرائح 2.1.a–2.1.e فقط: العقود immutable، target/flag validation، parsers XML/JSON pure، fixtures offline، redaction/bounded parsing، وprovenance bridge إلى ReconIngestionService وReconEvidenceService. لم يُنفذ Slice 2.1.f ولم تُشغل أي أداة live.

بعد الاعتماد، يتوقف العمل عند كل slice إذا ظهر تعارض معماري مع Modules 0–2.0. لا يبدأ Nmap أو أي port scanner حقيقي تلقائيًا، ولا يُفهم اعتماد Module 2.1 design على أنه اعتماد للتشغيل الشبكي.

## 19. Implementation record

أضافت الشرائح المعتمدة `src/cyberos/domain/recon/network_scan.py` لعقود `NetworkPortScanAdapterManifest` و`NetworkScanInvocation` وtyped target/flag policy، و`src/cyberos/domain/recon/network_scan_parser.py` لـpure XML/JSON parsing باستخدام Expat مع منع DTD/entities الخارجية، closed schema version `1.0`، redaction، digests، وحدود payload/host/service/depth/field. أضيف `src/cyberos/application/network_port_scan.py` كـoffline harness وprovenance bridge يعيد استخدام `ReconIngestionService` و`ReconEvidenceService` دون raw payload persistence أو migration.

أُضيفت 10 اختبارات تكامل تغطي manifest، target/CIDR/port policy، deterministic flags، XML/JSON parsing، external entity rejection، context/schema/truncation/budget failures، redaction، synthetic/offline markers، atomic ingestion، Evidence provenance، وعدم ingestion عند mismatch. أثناء اختبار bridge كُشف خلل concrete في `port_service_records` داخل `SQLiteReconRepository` (18 placeholders مقابل 17 columns)، وتم إصلاحه إصلاحًا محدودًا وموثقًا؛ لم يتغير schema أو أي migration.

النتيجة النهائية: **380 اختبارًا ناجحًا**، Ruff وformat، `mypy --strict`، wheel build، وboundary scan دقيق. لم تُستخدم network sockets أو DNS/HTTP أو subprocess أو Nmap/Masscan أو background daemon أو retry أو auth renewal. يتوقف العمل عند Slice 2.1.e بانتظار اعتماد منفصل لأي live tool integration.

## 18. المراجع الداخلية

1. Module 2.0 live boundary: `cyberos-core/docs/architecture/phase-2-overview-and-module-2-0-live-adapter-boundary-design.md`.
2. Module 2.0 implementation boundary: `cyberos-core/src/cyberos/execution/live_adapter.py`.
3. Recon plugin contracts: `cyberos-core/src/cyberos/recon/contracts.py`.
4. Scope/authorization boundary: `cyberos-core/src/cyberos/application/scope_validation.py`.
5. Recon orchestration design: `cyberos-core/docs/architecture/module-1-2-recon-orchestration-design.md`.
6. Evidence/provenance design: `cyberos-core/docs/architecture/module-1-3-recon-evidence-provenance-design.md`.
