# Slice 2.1.f — Specific Live Tool Binary Specification & Authorized Lab Target Protocol

**Project:** CyberOS — Personal Cybersecurity Engineering OS  
**Phase:** 2 — Controlled Live Adapter Integration  
**Slice:** 2.1.f  
**Status:** Slices 2.1.f.a–d implemented and verified offline; P3 first live execution remains unauthorized  
**Baseline:** Module 2.1.a–e checkpoint `bf0bf4b5`, 380 passing tests, CI run `31817813589`  
**Author:** Manus AI  
**Schema policy:** SQLite schema remains at migration 0006  

> هذه الوثيقة تحدد مواصفة أداة حيّة واحدة وبروتوكول مختبر محلي مصرح به. لا تُعد موافقة على تشغيل binary أو إجراء network scan. لا يبدأ التنفيذ أو أول تشغيل إلا بعد اعتماد صريح منفصل لهذا التصميم وبوابات التشغيل المحددة هنا.

## 1. Purpose and decision boundary

تنتقل هذه الشريحة من العقود والـparsers والـfixtures offline إلى تعريف binary حي محدد يمكن لاحقًا تشغيله عبر حدود Module 2.0. القيمة المطلوبة ليست إضافة scanner عام إلى CyberOS، بل تثبيت هوية أداة واحدة، وربطها بعقد `NetworkPortScanAdapterManifest`، وإثبات أن كل تشغيل محتمل سيكون محكومًا بـ`CommandSandbox` و`LiveSubprocessAdapter` و`ExecutionAuthorization` الحالية.

النطاق المقترح هو **Nmap فقط**، وبوضع TCP SYN machine-readable XML محدود. لا يشمل هذا التصميم UDP، NSE/scripts، OS detection، service/version probing، IPv6 discovery غير المطلوب، timing profiles غير `T3`، أو أي أداة ثانية مثل Masscan. اختيار Nmap هنا هو قرار adapter boundary وليس اعتمادًا لتشغيله على شبكة خارجية.

| البند | داخل Slice 2.1.f | خارج النطاق |
|---|---|---|
| Binary | Nmap واحد مثبت محليًا ومساره absolute ومحدد بالـmanifest | Masscan، RustScan، cloud scanners، package installation التلقائي |
| Scan | TCP SYN على هدف مختبر محلي واحد وبـports صريحة | UDP، ping sweep، CIDR واسع، target lists، OS/service scripts |
| Output | XML machine-readable إلى stdout فقط | ملفات XML على القرص، XML غير محدود، terminal renderer |
| Execution | `CommandSandbox` ثم `LiveSubprocessAdapter` | `subprocess` مباشر، `shell=True`، PATH lookup، daemon/background |
| Persistence | ReconIngestionService وReconEvidenceService الحاليان | migrations جديدة، raw output/BLOB، raw command persistence |
| Verification | neutral doubles ثم controlled localhost trial بعد approval | scan لشبكة المنزل أو الإنترنت أو أجهزة الغير |

## 2. Non-negotiable safety principles

كل قرار في التنفيذ اللاحق يجب أن يجيب عن السؤال: هل يثبت أن الأداة تعمل داخل boundary مصرح به، أم يوسع قدرتها التشغيلية؟ أي سلوك يوسع الهدف، يضيف flags غير معتمدة، يقرأ environment موروثًا، أو يحفظ raw output يُرفض بدل محاولة إصلاحه تلقائيًا.

المبادئ غير القابلة للتفاوض هي: **deny by default**، target واحد لكل invocation، authorization active ومطابق قبل spawn، expiry enforced عند لحظة التحقق، argv tuple فقط، `shell=False`، stdout/stderr bounded، XML parser closed-schema، redaction قبل أي projection، no retry، no background process، no authorization renewal، وno silent clamping.

## 3. Binary identity and installation policy

لا يكفي وجود اسم `nmap` في PATH. يجب أن يمثل الـmanifest binary identity مراجعة صريحة للملف التنفيذي. التنفيذ المقترح يضيف طبقة تحقق pure قبل spawn، ولا يقوم بتثبيت الأداة أو اختيارها تلقائيًا.

### 3.1 Required identity fields

```text
logical_id              = "nmap.tcp-syn.xml.localhost"
executable_absolute_path = host-provided absolute path, e.g. /usr/bin/nmap
expected_binary_name     = "nmap"
binary_version_policy    = exact or approved-semver-range, selected explicitly
binary_digest_policy     = sha256 required for approved lab profile
manifest_version         = "2.1.f"
command_contract_version = "1.0"
output_contract_version  = "1.0"
```

قبل قبول manifest، يجب أن يثبت host-side verifier أن المسار absolute، regular file، executable، غير directory أو symlink غير معتمد، وأن basename يطابق `nmap`. يجب عدم استخدام `shutil.which` أو أي PATH search كآلية اختيار. إذا كان المسار غير موجود أو لا يمكن فحصه، تكون النتيجة `LIVE_TOOL_BINARY_INVALID` أو `LIVE_TOOL_BINARY_UNAVAILABLE` typed error ولا يحدث spawn.

### 3.2 Digest and version verification

الـdigest ليس تفصيلًا تجميليًا. ملف Nmap الموجود في المختبر يجب أن يطابق digest مسجلًا في lab profile، أو يجب أن يتوقف التشغيل ويتطلب مراجعة manifest. لا يُسمح بتحديث digest تلقائيًا عند اكتشاف اختلاف. كما يجب فصل فحص version عن فحص digest؛ نجاح أحدهما لا يعوض فشل الآخر.

التحقق من version لا يشغل Nmap في مرحلة تصميم أو test collection. في implementation اللاحق، إن لزم فحص version، يجب أن يكون command مستقلًا ومسموحًا صراحة في manifest، bounded، بلا target، ولا يُعتبر scan. لكن الخيار الأكثر أمانًا لأول trial هو توفير version/digest من host verification موثوق قبل إنشاء `ApprovedExecutable`.

## 4. Approved Nmap manifest

يُبنى manifest immutable ويرتبط مباشرة بـ`ApprovedExecutable` من Module 2.0. لا ينشئ الـadapter executable جديدًا ولا يملك صلاحية تجاوز `CommandSandbox`.

```python
NetworkPortScanAdapterManifest(
    adapter_id="nmap.tcp-syn.xml.localhost",
    executable_id="nmap.binary.approved",
    executable_absolute_path="/usr/bin/nmap",
    binary_name="nmap",
    verified_binary_sha256="<approved-lab-digest>",
    verified_version="<approved-version>",
    adapter_version="2.1.0",
    command_contract_version="1.0",
    output_format="xml",
    output_contract_version="1.0",
    supported_target_kinds=("ipv4",),
    require_target_argument=True,
    allowlisted_flags=("-sS", "-p", "-T3", "-oX -"),
    fixed_flags=("-sS", "-T3", "-oX -"),
    allow_scripts=False,
    allow_file_output=False,
    allow_background=False,
    max_ports=16,
    max_timeout_seconds=30,
    max_output_bytes=262144,
)
```

الأسماء أعلاه تمثل design contract؛ لا يعني ذلك أن التنفيذ يجب أن يغير `NetworkPortScanAdapterManifest` الحالي مباشرة قبل مراجعة additive compatibility. إذا كانت الحقول الحالية غير كافية لهوية digest/version، فالخيار الصحيح هو إضافة `VerifiedBinaryIdentity` immutable في application boundary، لا كسر Module 2.1.a–e أو إدخال identity غير typed.

## 5. Exact argv contract

أول trial يستخدم argv ثابتًا بالشكل الآتي، مع استبدال target وport list بعد تحقق policy فقط:

```text
(
  "/usr/bin/nmap",
  "-sS",
  "-T3",
  "-n",
  "-Pn",
  "-p", "22,80,443",
  "-oX", "-",
  "127.0.0.1",
)
```

`-n` يمنع DNS resolution، و`-Pn` يمنع الاعتماد على discovery/ping كقرار منفصل. إدخالهما يجب أن يكون جزءًا من manifest fixed flags، وليس arbitrary user input. استخدام `-oX -` يعني XML إلى stdout؛ لا يُقبل output filename أو `-oA` أو `-oN` أو `-oG` أو أي output path.

### 5.1 Allowlist

| Flag | Policy | سبب القبول |
|---|---|---|
| `-sS` | fixed, required | TCP SYN mode المحدد فقط |
| `-T3` | fixed, required | timing محافظ ومحدود |
| `-n` | fixed, required | منع DNS side effect |
| `-Pn` | fixed, required للـlocalhost profile | منع discovery branch غير المقصود |
| `-p` | typed value فقط | port set صغير ومفحوص |
| `-oX -` | fixed, required | XML stdout دون file output |
| target | host-created validated scalar | آخر argv ومطابق للتفويض |

كل flag آخر مرفوض، بما في ذلك `--script`، `--script-args`، `-A`، `-O`، `-sV`، `-sU`، `-iL`، `-oA`، `-oN`، `--resume`، `--datadir`، `--proxies`، و`--stylesheet`. لا توجد passthrough escape hatch.

### 5.2 Port policy

الـport selector typed immutable tuple، لا string حر. لأول localhost trial الحد الأقصى هو 3 ports، والقيم المسموحة تُحدد مسبقًا في lab profile. لا ranges مثل `1-65535`، ولا comma string غير محلل، ولا duplicate، ولا port 0. أي تجاوز يؤدي إلى `PORT_SCAN_LIMIT_EXCEEDED` قبل spawn.

## 6. Authorized lab target protocol

يجب ألا يتحول تصريح المستخدم العام عن “شبكتي البيت” إلى target authorization ضمني. أول live trial يجب أن يكون **127.0.0.1 فقط** داخل WSL، لأن هذا يثبت binary/stream/parser/provenance pipeline دون لمس أجهزة الشبكة المنزلية.

### 6.1 Localhost profile

```text
profile_id             = "lab.localhost.tcp-syn.v1"
target_kind            = ipv4
canonical_target       = "127.0.0.1"
allowed_targets        = { "127.0.0.1" }
allowed_ports          = { 22, 80, 443 }
max_ports              = 3
max_timeout_seconds    = 30
max_output_bytes       = 262144
network_scope          = loopback-only
requires_dns_disabled  = true
requires_single_target = true
```

أي قيمة غير `127.0.0.1` مرفوضة في هذا profile، بما فيها `localhost` إذا لم تُحوّل host-created إلى IPv4 وتُطابق allowlist صراحة، و`127.0.0.0/8`، و`0.0.0.0`، و`::1`، وprivate RFC1918 ranges. لا يُسمح بتوسيع profile إلى `192.168.0.0/16` أو `/24` في نفس الشريحة.

### 6.2 Authorization equality sequence

قبل بناء argv وقبل spawn يجب تنفيذ الترتيب التالي، مع fail-closed عند أول اختلاف:

1. التحقق من أن Task في الحالة المطلوبة للتنفيذ وأن `task.scope_id` و`task.target_id` موجودان.
2. التحقق من أن `authorization.scope_id == task.scope_id`.
3. التحقق من أن `authorization.matched_target_id == task.target_id`.
4. التحقق من أن `authorization.matching_rule == INCLUDE` وأن scope/target active.
5. التحقق من `expires_at` باستخدام UTC time عند لحظة preflight، وعدم تجديده.
6. التحقق من أن target record canonical value يساوي `127.0.0.1` وtarget kind هو IPv4.
7. التحقق من أن `lab_profile_id` يطابق manifest/profile، لا قيمة يرسلها plugin.
8. التحقق من أن كل argv مشتق من typed fields ولا يحتوي targetًا ثانيًا.
9. تسجيل preflight receipt redacted فقط، ثم تمرير الطلب إلى `CommandSandbox`.
10. لا يحدث spawn إذا فشل أي تحقق، ولا تُنشأ Evidence من محاولة مرفوضة.

## 7. WSL and host assumptions

WSL ليس ضمانًا بأن `127.0.0.1` يعني نفس namespace أو نفس services في Windows. لذلك لا يفترض CyberOS وجود خدمة listening. هدف trial هو اختبار scanner/process/parser boundary، وقد تكون النتيجة صفر ports مفتوحة، وهذا نجاح صالح إذا كان XML سليمًا وسياقه صحيحًا.

لا يُسمح للمنظومة بتعديل Windows Firewall، أو تشغيل خدمة test تلقائيًا، أو فتح listener، أو استخدام Windows host address، أو scan WSL gateway. إذا احتاجت تجربة لاحقة إلى service محلي، ينشئ المستخدم service محايدًا يدويًا وبشكل منفصل ويصرح به قبل trial جديد.

## 8. Controlled live trial phases

لا يُنفذ trial كاختبار واحد غير قابل للتفسير. يجب أن يمر بالمراحل التالية:

| المرحلة | التنفيذ | شرط النجاح | شرط الإيقاف |
|---|---|---|---|
| P0 | manifest static verification | path/name/version/digest policy valid | أي mismatch |
| P1 | sandbox dry-run | exact argv/environment/context receipt | أي flag أو context drift |
| P2 | binary availability preflight | approved file executable | missing/non-regular/unverified binary |
| P3 | single live invocation | one bounded process، localhost only | timeout، unexpected target، output overflow |
| P4 | redaction/parser | XML 1.0 parsed، no secrets/paths | malformed XML، external entity، schema mismatch |
| P5 | observation projection | service observations bounded/context-bound | unknown record أو count overflow |
| P6 | atomic ingestion | assets/observations committed | partial transaction أو provenance mismatch |
| P7 | Evidence creation | only committed provenance creates evidence | evidence without observation |
| P8 | post-trial audit | receipt contains digest/counts/status فقط | raw output/command/path leakage |

P0–P2 يمكن اختبارها دون تشغيل scanner. أول تشغيل حي هو P3، ولا يُسمح به قبل اعتماد هذه الوثيقة وتنفيذ الاختبارات offline المكافئة.

## 9. Output and redaction pipeline

الـraw stdout/stderr يبقى في الذاكرة داخل process receipt فقط وبحدود bytes. لا يُكتب إلى file، log، SQLite، Evidence metadata، أو error message. قبل parser يجب تطبيق redaction للـcredentials، absolute paths، control bytes، وtraceback-like content. يُحتفظ فقط بـdigest، byte counts، truncation flag، parser schema، وعدد observations.

الـparser يرفض output إذا كان truncated أو malformed، أو يحتوي internal subset أو `PUBLIC` identifier أو entity declaration أو external reference أو schema version غير `1.0`. يقبل فقط ترويسة Nmap القياسية benign من الشكل `<!DOCTYPE nmaprun SYSTEM "...">` كصيغة، لكنه يتجاهل URI ولا يحمّل أو يجلب DTD. لا توجد best-effort parsing ولا field guessing. إذا كان stderr يحوي warning غير حساس، لا يُخزن raw؛ يمكن حفظ `stderr_present=true` أو typed category فقط.

## 10. ReconObservation and Evidence handoff

يُحول XML port record المقبول إلى `ReconObservation` من النوع `service` مع scalar value محدود وmetadata allowlist: `port`, `protocol`, `state`, `service_name`, `product`, `service_version`, `transport`. لا يدخل XML body أو command line أو binary path في observation.

يُبنى `ReconResult.success` فقط إذا كان output contract مكتملًا ومطابقًا للسياق. ثم يستدعي التطبيق `ReconIngestionService` ضمن حدود `ExecutionLimits`. بعد commit وقراءة provenance الملتزم، يمكن لـ`ReconEvidenceService` إنشاء Evidence من observation. أي فشل في parser أو context أو provenance يمنع ingestion وEvidence معًا، بينما يظل raw payload خارج persistence.

## 11. Error model and fail-closed matrix

| الحالة | ErrorCode المقترح | هل يحدث spawn؟ | هل تُحفظ Evidence؟ |
|---|---|---:|---:|
| Binary missing/not executable | `LIVE_TOOL_BINARY_UNAVAILABLE` | لا | لا |
| Digest/version mismatch | `LIVE_TOOL_BINARY_INVALID` | لا | لا |
| Manifest identity mismatch | `PORT_SCAN_MANIFEST_INVALID` | لا | لا |
| Target خارج localhost profile | `PORT_SCAN_TARGET_UNAUTHORIZED` | لا | لا |
| Expired authorization | `LIVE_ADAPTER_UNAUTHORIZED` | لا | لا |
| Flag أو target drift | `COMMAND_SANITIZATION_FAILED` | لا | لا |
| Timeout | `SUBPROCESS_TIMEOUT` | نعم، مرة واحدة | لا للنتيجة غير المكتملة |
| Output byte cap | `LIVE_ADAPTER_LIMIT_EXCEEDED` أو `PORT_SCAN_TRUNCATED_OUTPUT` | نعم، مرة واحدة | لا |
| XML malformed/schema mismatch | `PORT_SCAN_PARSE_FAILED` أو `PORT_SCAN_SCHEMA_UNSUPPORTED` | نعم، مرة واحدة | لا |
| Provenance mismatch | `PORT_SCAN_CONTEXT_MISMATCH` أو `PORT_SCAN_INGESTION_REJECTED` | نعم، مرة واحدة | لا |

رسائل الأخطاء redacted، bounded، ولا تحتوي command line، target raw غير المصرح، path، stderr، traceback، أو credential. لا retry لأي حالة، ولا retry للtimeout، ولا fallback إلى output format آخر.

## 12. Test strategy before first live execution

قبل السماح بـP3، يجب أن تنجح الاختبارات التالية فوق baseline 380:

### 12.1 Static and manifest tests

يجب اختبار absolute path، basename، regular/executable policy، digest mismatch، version mismatch، duplicate manifest identity، unsupported target kind، fixed flags، forbidden flags، file-output flags، scripts، child/background policy، وعدم PATH lookup.

### 12.2 Authorization and lab tests

يجب اختبار `127.0.0.1` success، `localhost` policy decision، `127.0.0.2` rejection، `192.168.1.1` rejection، CIDR rejection، target list rejection، cross-scope، cross-target، expired authorization، archived target، non-Include authorization، وTask command mismatch. يجب التأكد أن كل الرفض يحدث قبل runner invocation باستخدام a spy/double.

### 12.3 Controlled runner double tests

يُستخدم neutral process double أو injected runner في الاختبارات العادية لإرجاع XML fixture، malformed XML، XML with DTD، oversized stream، timeout receipt، stderr secret، وunexpected exit code. هذه الاختبارات لا تحتاج Nmap ولا socket.

### 12.4 Pipeline tests

يجب إثبات أن output المقبول ينتج Observations متطابقة deterministic digest، وأن ingestion يستخدم `ReconIngestionService`، وأن Evidence لا تُنشأ إلا من asset/observation committed. يجب إثبات atomic rollback عند parser/provenance failure، وعدم وجود raw XML في SQLite أو error strings أو audit records.

### 12.5 First live integration test

بعد اعتماد المستخدم وتنفيذ كل الاختبارات السابقة، يُسمح باختبار واحد explicit وموسوم `live_localhost_only`. يجب أن:

1. يفحص `127.0.0.1` فقط.
2. يستخدم manifest digest/version المعتمدين.
3. يستخدم argv الذي ينتجه sandbox دون تعديل يدوي.
4. يمرر process عبر `LiveSubprocessAdapter` فقط.
5. يثبت أن target لم يتغير قبل وبعد spawn.
6. يتحقق من XML bounded/redacted/schema-valid.
7. يتحقق من عدم تسريب raw output أو paths أو credentials.
8. يتحقق من ReconObservation وEvidence counts وprovenance tuples.
9. يقبل نتيجة صفر ports كحالة صحيحة إذا كانت بقية الشروط سليمة.
10. يفشل closed إذا كان Nmap غير موجود أو غير مطابق، دون تثبيت أو تنزيل أو fallback.

## 13. First-run confirmation gate

قبل أول تشغيل حي، يجب أن تظهر confirmation record للمستخدم تتضمن فقط: profile id، canonical target `127.0.0.1`، typed ports، executable logical id، binary path basename، timeout، output cap، وauthorization expiry. لا تعرض raw command أو secrets، ولا تُنفذ العملية في نفس خطوة بناء confirmation.

يتطلب الانتقال من P2 إلى P3 اعتمادًا صريحًا منفصلًا بعد مراجعة نتائج الاختبارات. لا يكفي اعتماد التصميم. إذا لم يرد اعتماد التشغيل، يبقى Slice 2.1.f في وضع design/verification ولا يحدث live invocation.

## 14. Rollback and abort protocol

لا توجد migration في Slice 2.1.f، لذلك rollback البرمجي هو العودة إلى checkpoint `bf0bf4b5` إذا فشل implementation. لا يُستخدم `git reset --hard`؛ يُستخدم checkpoint rollback المعتمد.

أثناء trial، abort فوري عند ظهور target غير `127.0.0.1`، أكثر من process، child process، output truncation، timeout، DNS activity، unexpected flag، path/credential leak، schema mismatch، أو Evidence دون committed provenance. لا retry بعد abort. تُحفظ فقط typed receipt redacted، ولا يُعاد تشغيل نفس trial تلقائيًا.

## 15. Data and privacy boundary

| Data | In-memory | SQLite | Logs/errors |
|---|---:|---:|---:|
| Raw XML stdout | مؤقت bounded | لا | لا |
| Raw stderr | مؤقت bounded | لا | لا |
| Output digest | نعم | metadata/digest only عند الحاجة | نعم، redacted |
| Binary full path | preflight only | لا | basename/logical id فقط |
| Target | typed context | existing target/evidence contracts | canonical authorized form فقط |
| Credentials/secrets | مرفوضة | لا | لا |
| Observations | normalized | نعم عبر existing ingestion | counts/types فقط |
| Evidence | بعد provenance commit | نعم عبر existing service | id/count/status فقط |

## 16. Proposed implementation slices after approval

التنفيذ اللاحق يجب أن يبقى additive ومجزأ:

| Slice | Deliverable | Live execution؟ |
|---|---|---:|
| 2.1.f.a | `VerifiedBinaryIdentity` وmanifest binding وtyped errors | لا |
| 2.1.f.b | localhost lab profile وpreflight policy وdry-run tests | لا |
| 2.1.f.c | Nmap XML stdout parser bridge فوق existing parser contracts | لا |
| 2.1.f.d | injected runner integration وatomic provenance tests | لا |
| 2.1.f.e | first explicit `live_localhost_only` trial | نعم، مرة واحدة |

لا تُجمع هذه الشرائح في commit واحد إذا ظهر قرار معماري جديد. لا تُضاف migration، ولا tool-specific adapter ثانٍ، ولا network target غير loopback.

## 17. Decisions requiring explicit approval

يتطلب البدء بالمواصفة التنفيذية اعتماد القرارات الآتية: اختيار Nmap دون غيره؛ حصر أول trial في `127.0.0.1` دون home subnet؛ اعتماد TCP SYN XML stdout فقط؛ اعتماد fixed flags `-sS -T3 -n -Pn -oX -` وtyped ports؛ إلزام binary absolute path وdigest/version verification؛ منع package installation وPATH lookup؛ إعادة استخدام Module 2.0 runner وModule 2.1 parser/provenance services؛ وعدم إضافة migration أو raw artifact storage.

ويتطلب **أول تشغيل حي** اعتمادًا ثانيًا مستقلًا بعد تنفيذ `2.1.f.a–d` واجتياز كل الاختبارات. اعتماد هذه الوثيقة وحده لا يخول P3.

## 18. Approval gate and stop condition

لا يبدأ implementation حتى يوافق المستخدم صراحة على Section 17. وبعد implementation، لا يبدأ أول live execution حتى يوافق المستخدم صراحة على نتائج الاختبارات وعلى الانتقال من P2 إلى P3. بعد trial الأول، يتوقف العمل للمراجعة ولا يبدأ adapter جديد أو home-network scanning تلقائيًا.

## 19. Implementation record for Slices 2.1.f.a–d

تم تنفيذ الشرائح المصرح بها فقط. أُضيف `VerifiedBinaryIdentity` مع absolute-path، regular-file، executable، SHA-256، وversion contracts دون PATH lookup أو package installation. أُضيف `NmapLocalhostManifest` و`NmapLocalhostLabPolicy` لبناء dry-run request مقيد بالـ`lab.localhost.tcp-syn.v1`، وبالهدف `127.0.0.1`، والـports `{22, 80, 443}`، والـargv الثابت `-sS -T3 -n -Pn -p <ports> -oX -`.

أُضيف `NmapXmlParserBridge` كـpure Expat bridge يقبل benign `nmaprun` DOCTYPE فقط ويرفض internal subsets/entities/external references، ويحول subset مغلقًا من Nmap XML إلى parser contracts الموجودة في Module 2.1.e. أُضيفت injected runner doubles تختبر redaction، timeout/error boundaries، وعدم تشغيل `SafeSubprocessRunner` الحقيقي. كما أُثبت تدفق XML fixture إلى `ReconObservation` ثم `ReconIngestionService` و`ReconEvidenceService` مع atomic provenance، دون حفظ raw XML.

أُضيفت 10 اختبارات جديدة، وأصبح الإجمالي **390 اختبارًا ناجحًا**. نجحت Ruff، format، `mypy --strict`، wheel build، وboundary scan. لم يُشغّل Nmap أو أي binary حي، ولم تُفتح sockets، ولم تُضف migrations، ولم يحدث P3. تبقى confirmation gate ذات المستويين مفتوحة: اعتماد نتائج a–d أولًا، ثم طلب منفصل قبل P3.

## 20. DOCTYPE compatibility patch record

The parser now accepts a standard Nmap `nmaprun` DOCTYPE declaration only when it has no public identifier and no internal subset. Expat parameter-entity parsing remains disabled, entity declarations remain rejected, and external entity callbacks remain hard-fail handlers. The referenced SYSTEM URI is ignored rather than opened or fetched. Offline tests cover the standard Nmap header and an XXE/internal-subset rejection fixture. The patch does not add a migration and does not authorize or execute a new live trial.

The TCP Connect profile is additive: `ScanMode.CONNECT` produces `-sT`, and the localhost manifest exposes `lab.localhost.tcp-connect.v1`. The default SYN profile remains available for privileged environments, while the unprivileged first-run guide should use TCP Connect.

**Current state:** Slices 2.1.f.a–d plus the offline DOCTYPE compatibility patch pass 390 tests and all quality gates. No new live trial has been executed after this patch, no home-subnet scan has been performed, and a new explicit P3 authorization is required before any localhost invocation.

## 21. Module 2.1.g application boundary record

Module 2.1.g adds `NmapLocalhostScanService` and the official `cyberos recon nmap-localhost` command. The service owns creation of a pending Task only after loading the explicit Target, verifying that it is ACTIVE IPv4 `127.0.0.1`, obtaining fresh `ExecutionAuthorization`, and validating the approved binary identity. It then persists the Task lifecycle through PENDING → RUNNING → COMPLETED/FAILED, delegates process execution to `LiveSubprocessAdapter`, parses only bounded redacted XML, and reuses `NetworkPortScanProvenanceBridge` for atomic Recon/Evidence persistence.

The CLI requires an explicit Scope ID, Target ID, Nmap SHA-256, and Nmap version. Ports default to `22,80,443` and are fail-closed to that allowlist. No live invocation is performed by the test suite; injected runner tests prove exact argv, parser/provenance wiring, output redaction, CLI discovery, and invalid-port rejection. Schema remains at 0006. The implementation is complete at **393 passing tests**, and a separate explicit authorization remains required before the first localhost live trial.

## 22. P3 hardening and parser-compatibility remediation record

One separately authorized localhost TCP Connect P3 invocation was made through the official application service. It passed authorization, binary identity, exact argv, process bounds, and SQLite integrity checks, but its standard Nmap XML was rejected before ingestion by the closed parser allowlist. No assets, observations, or evidence were created; the trial was not retried.

The offline remediation adds a minimal structural compatibility set for standard Nmap 7.94 XML: `verbose`, `debugging`, `hostnames`, `hostname`, and `hosts` under `runstats`, alongside the already accepted `scaninfo`, `status`, `ports`, `times`, `runstats`, and `finished`. These elements are ignored structurally and do not persist their attributes or textual payload. The benign `nmaprun` DOCTYPE policy is unchanged: public identifiers, internal subsets, entity declarations, parameter entities, and external references remain rejected.

`NmapLocalhostScanService` now catches typed parser, provenance, and ingestion failures after the Task enters `RUNNING`, persists a redacted terminal `FAILED` result with optimistic version control, and re-raises the original typed error. Offline fixtures prove standard XML success, malformed/unallowlisted XML failure finalization, provenance failure finalization, zero Evidence on failure, and existing XXE rejection. The suite is now **397 passing tests** with Ruff, formatting, mypy strict, wheel build, and boundary checks passing. Schema remains at 0006. No additional live invocation is authorized or performed by this remediation.

## 23. Closed and filtered port XML preflight compatibility record

Before consuming a separately authorized retry, the locally installed Nmap DTD was inspected offline. Its `ports` structure permits `extraports` and nested `extrareasons` for summarized closed or filtered ports. These elements are now included in the parser's structural allowlist and are deliberately ignored: their attributes and content are neither normalized nor persisted. A standard offline Nmap 7.94 fixture with no open ports, `extraports state="closed"`, `extrareasons`, and `runstats/hosts` parses to zero services and zero observations.

The security boundary remains unchanged: benign outer `nmaprun` DOCTYPE acceptance is restricted as documented, parameter/entity parsing is disabled, internal subsets and entity declarations are rejected, and external entity resolution is a hard failure. The patch adds no migration, no socket, no subprocess, and no new live invocation. Full quality gates pass at **398 tests**. P3 remains paused until the patch is reported and a separate run authorization is actioned.

## 24. State metadata preflight compatibility record

A separately authorized P3 invocation reached the Nmap `state` element and correctly finalized its Task as `FAILED` when the parser rejected standard state metadata. The offline contract now accepts a state element only if it has a non-empty `state` attribute and, optionally, the standard `reason` and `reason_ttl` attributes. `reason`, when present, must be non-empty and bounded by the parser field limit; `reason_ttl`, when present, must be a decimal value from 0 to 255. Any missing `state` value, malformed allowed metadata, or unallowlisted state attribute remains a typed `NMAP_XML_INVALID` failure.

Only the `state` value is carried into normalized service metadata. Reason and TTL are deliberately discarded, so parser output remains minimal and does not broaden Recon/Evidence retention. Offline fixtures prove a standard `state="open" reason="syn-ack" reason_ttl="0"` path, reject missing `state`, an unknown attribute, an empty reason, and non-decimal TTL, while preserving DTD/XXE/entity protection. The patch has **402 passing tests**, zero migrations, zero new side effects, and no live invocation. A new explicit P3 authorization remains required before retrying localhost execution.
