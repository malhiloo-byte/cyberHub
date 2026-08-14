# تقرير تجربة P3 — Localhost Nmap TCP Connect

**الحالة:** مكتملة كمحاولة واحدة مصرح بها، لكنها انتهت بفشل parser قبل ingestion.  
**تاريخ التنفيذ:** 14 أغسطس 2026.  
**النطاق:** `127.0.0.1` فقط.  
**الأداة:** `/usr/bin/nmap`، الإصدار المعلن `7.94SVN`.  
**عدد الاستدعاءات الحية:** استدعاء واحد فقط؛ لم تُنفّذ أي إعادة محاولة أو fallback أو نطاق بديل.

## 1. التفويض والـpreflight

تم تنفيذ التجربة بعد التفويض الصريح باستخدام profile TCP Connect غير المحتاج إلى raw sockets. تم إنشاء قاعدة SQLite مؤقتة مستقلة، ثم إنشاء Workspace وEngagement وScope وTarget محليين، وإضافة Target من النوع IPv4 والقيمة `127.0.0.1` بقاعدة `include`، ثم تحويل الـScope إلى `authorized` قبل التنفيذ.

| العنصر | القيمة المتحققة |
|---|---|
| Scope ID | `f861fa02-b83d-4807-946a-5ade2e963954` |
| Target ID | `e069074a-0829-4138-a85f-6cd47fc129de` |
| Task ID | `b4093e60-15c9-4f13-bdd3-70d1a05b13f5` |
| Target | `127.0.0.1` |
| Target kind | `ipv4` |
| Binary path | `/usr/bin/nmap` |
| Nmap version | `7.94SVN` |
| SHA-256 | `681a4b25588d9bbc2319009ed917f2b4dd9620bafa58f23415fbb0b18f006ef0` |
| Database | `/tmp/cyberos-p3-1786731648/cyberos.sqlite3` |

تم اجتياز binary identity وtarget/authorization preflight. لا يوجد في العملية أي PATH lookup أو target inference أو توسيع للنطاق.

## 2. الأمر المنفذ

نفّذ المسار الرسمي الأمر التالي مرة واحدة فقط:

```bash
cyberos recon nmap-localhost \
  f861fa02-b83d-4807-946a-5ade2e963954 \
  e069074a-0829-4138-a85f-6cd47fc129de \
  --nmap-sha256 681a4b25588d9bbc2319009ed917f2b4dd9620bafa58f23415fbb0b18f006ef0 \
  --nmap-version 7.94SVN \
  --ports 22,80,443 \
  --nmap-path /usr/bin/nmap \
  --json \
  --file /tmp/cyberos-p3-1786731648/cyberos.toml
```

وبحسب عقد الخدمة، كان الـargv الداخلي المعتمد:

```text
(/usr/bin/nmap, -sT, -T3, -n, -Pn, -p, 22,80,443, -oX, -, 127.0.0.1)
```

## 3. النتيجة التشغيلية

خرج Nmap بنتيجة XML، ووصلت البيانات إلى طبقة bounded/redacted process receipt، لكن `NmapXmlParserBridge` رفض عنصرًا من XML باعتباره غير موجود في الـallowlist المغلق. النتيجة التي ظهرت للمستخدم كانت typed وredacted:

```json
{
  "ok": false,
  "error": {
    "code": "NMAP_XML_INVALID",
    "message": "Nmap XML element is not allowlisted."
  }
}
```

كان exit code الخاص بأمر CLI هو `1`. لم يتم حفظ stdout أو stderr الخام، ولم يظهر في التقرير أو log أي credential أو path leakage أو XML payload. كما أن stderr الخارجي كان فارغًا.

من المهم عدم الادعاء بأن عنصرًا بعينه هو السبب، لأن raw XML لم يُخزّن وفقًا لسياسة الخصوصية. المراجعة offline للـallowlist تشير إلى أن parser يدعم subset مغلقًا من Nmap XML، بينما قد تحتوي مخرجات Nmap القياسية على عناصر وصفية إضافية مثل `verbose` أو `debugging` أو `hosts` داخل `runstats`. يجب إثبات العنصر المحدد بfixture offline مطابق قبل تعديل parser.

## 4. تحقق قاعدة البيانات وProvenance

تم تنفيذ تدقيق read-only بعد المحاولة على قاعدة SQLite المؤقتة:

| الفحص | النتيجة |
|---|---|
| `PRAGMA quick_check` | `ok` |
| `PRAGMA foreign_key_check` | لا توجد صفوف مخالفة |
| Schema migrations | من 0001 إلى 0006 فقط |
| Assets | `0` |
| Asset observations | `0` |
| Evidence records | `0` |
| Task status | `RUNNING`، version `2` |
| Task result | `null` |

النتيجة تعني أن parser رفض XML قبل `ReconIngestionService` وEvidence persistence؛ لذلك لم تُنشأ Observations أو Assets أو Evidence. قاعدة البيانات سليمة ولم تُضف أي migration.

## 5. العيب المكتشف وإجراء الإيقاف

يوجد عيبان يجب عدم إخفائهما:

أولًا، parser يحتاج إلى fixture offline يطابق XML القياسي الكامل الذي يعيده Nmap، ثم توسيع allowlist بأقل مجموعة آمنة ممكنة، مع إبقاء DTD/entity/XXE مرفوضة. ثانيًا، `NmapLocalhostScanService` لا يحول فشل parser/provenance إلى Task نهائي `FAILED`؛ لذلك بقي الـTask في حالة `RUNNING` بعد الفشل. يجب إصلاح finalization هذا offline وإضافة اختبار regression يمنع بقاء Tasks عالقة.

بسبب التفويض المحدد بتجربة واحدة، **لن تُعاد التجربة الآن**. لا يجوز إعلان P3 ناجحًا، ولا الانتقال إلى توسعة subnet أو multi-host قبل إصلاح هذين العيبين ومراجعتهما واعتمادهما.

## 6. أمر WSL القابل لإعادة الاستخدام بعد الإصلاح والتفويض الجديد

الأمر التالي هو القالب المحلي المطلوب بعد إصلاح parser وTask failure finalization، وإنشاء Scope/Target مصرحين جديدين أو استخدام سياق معتمد غير منتهٍ. لا ينبغي تشغيله مرة أخرى اعتمادًا على هذا التقرير وحده:

```bash
cd ~/cyberHub/cyberos-core
source .venv/bin/activate
SHA=$(sha256sum /usr/bin/nmap | awk '{print $1}')
cyberos recon nmap-localhost SCOPE_ID TARGET_ID \
  --nmap-sha256 "$SHA" \
  --nmap-version 7.94SVN \
  --ports 22,80,443 \
  --nmap-path /usr/bin/nmap \
  --file /path/to/cyberos.toml \
  --json
```

هذا الأمر يبقى localhost-only؛ لا تغيّر `SCOPE_ID` أو `TARGET_ID` إلى شبكة منزلية أو CIDR، ولا تضف flags غير موجودة في الخدمة.

## 7. Architecture Outline مقترح لـModule 2.2

لا أوصي ببدء تنفيذ Module 2.2 مباشرة. التصميم المقترح بعد إغلاق blocker هو Module 2.2 بعنوان **Explicit Scope Expansion & Bounded Multi-Host Recon**، وليس scanner عامًا.

| Boundary | التصميم المقترح |
|---|---|
| Scope expansion | تحويل CIDR أو مجموعة أهداف إلى candidates صريحة bounded، مع اشتراط authorization جديد ومراجعة exclude precedence؛ لا يتم توسيع Scope ضمنيًا من Target واحد. |
| Target registry | canonicalization وdeduplication لكل host، مع ربط كل Target بالـScope والـEngagement، ورفض wildcard/route/broadcast/targets غير المصرح بها. |
| Scheduler | تنفيذ sequential bounded في البداية، Task مستقل لكل Target، وبدون daemon أو retry تلقائي؛ يمكن دراسة concurrency لاحقًا بعد قياس الموارد. |
| Authorization | تحقق Scope/Target/Task/ExecutionAuthorization قبل كل host invocation، مع expiry وbudget متبقي لكل pipeline. |
| Tool adapter | إعادة استخدام Nmap manifest وCommandSandbox وLiveSubprocessAdapter؛ Module 2.2 لا يملك execution engine ثانيًا. |
| Budgets | حد أقصى لعدد hosts، إجمالي ports، timeout، output bytes، وعدد observations؛ الزيادة تؤدي إلى رفض fail-closed لا إلى silent clamping. |
| Persistence | atomic ingestion لكل host، وربط provenance بـTask/Target، مع عزل فشل host عن النتائج الملتزمة سابقًا. |
| Cancellation | cancel-before-ingest للنتائج غير الملتزمة، والحفاظ على host results الملتزمة، مع receipt واضح للحالة الجزئية. |
| Reporting | استخدام Evidence Query/Reporting الحالية بدل إضافة raw artifact store أو renderer جديد. |

الـslice السابق منطقيًا لـModule 2.2 هو **P3 Hardening & Parser Compatibility**: إصلاح allowlist وفق fixture قياسي offline، إصلاح Task failure finalization، إضافة اختبار end-to-end يحاكي parser failure، ثم quality gates وcheckpoint مستقل. بعد اعتماده فقط نعود لتصميم Module 2.2 التفصيلي.

## 8. الخلاصة

نجحت طبقات التفويض، binary identity، target binding، exact argv، bounded execution، redacted typed error، وSQLite integrity. لم تنجح مرحلة parser، وبالتالي لم تكتمل Recon/Evidence pipeline. التجربة الوحيدة استُهلكت كما تم تفويضها، ولم يتم تنفيذ أي retry أو fallback أو scan خارج `127.0.0.1`.

## 9. سجل remediation offline اللاحق

بعد التجربة، تم تنفيذ remediation offline فقط دون إعادة تشغيل Nmap أو أي اتصال شبكي. أضيف fixture قياسي من Nmap 7.94 يشمل `verbose` و`debugging` و`hostnames` و`runstats/hosts`، ثم أضيفت هذه العناصر البنيوية فقط إلى allowlist. لا تحفظ خصائصها أو محتواها، ولم تتغير سياسة رفض DTD الداخلي أو entities أو XXE أو external references.

تم أيضًا تعديل `NmapLocalhostScanService` بحيث يحوّل أي typed failure صادر عن parser أو provenance أو ingestion بعد دخول Task إلى `RUNNING` إلى Task نهائي `FAILED` مع `error_message` redacted يتكون من ErrorCode فقط. تغطي الاختبارات الآن parser القياسي الناجح، XML غير مسموح به، وفشل provenance؛ وتثبت عدم إنشاء Evidence عند الفشل. نجحت بوابات الجودة كاملة عند **397 اختبارًا**. لا يغيّر هذا remediation نتيجة التجربة الأصلية ولا يخول إعادة P3؛ يلزم تفويض جديد منفصل لأي invocation حي لاحق.

## 10. توافق ملخصات المنافذ المغلقة أو المفلترة

أظهر فحص offline لملف Nmap DTD المحلي أن النتائج القياسية قد تستخدم `extraports` و`extrareasons` لتلخيص المنافذ المغلقة أو المفلترة بدل إدراج عنصر `port` منفصل لكل منفذ. لذلك أضيفت هاتان العقدتان إلى allowlist البنيوي فقط. لا تُفسر خصائصهما، ولا تُضاف إلى `ReconObservation`، ولا تُخزّن في SQLite؛ فالنتيجة الصحيحة لفحص لا يحتوي منافذ مفتوحة هي **صفر observations** وليست error.

أضيف fixture مستقل لهذه الحالة مع `runstats/hosts`، ونجحت بوابات الجودة عند **398 اختبارًا**. لم يُنفذ Nmap حي في هذا patch. يظل تنفيذ P3 الحي التالي مشروطًا بتفويض منفصل واحد فقط.

## 11. محاولة P3 الثانية بعد إصلاح ملخصات المنافذ المغلقة

نُفذت محاولة حيّة واحدة جديدة ومصرح بها على `127.0.0.1` فقط، باستخدام المسار الرسمي وargv المقيد:

```text
(/usr/bin/nmap, -sT, -T3, -n, -Pn, -p, 22,80,443, -oX, -, 127.0.0.1)
```

نجح preflight للـScope والـTarget وbinary SHA-256، ووصل التنفيذ إلى parser، إلا أن `NmapXmlParserBridge` أعاد `NMAP_XML_INVALID` بالرسالة redacted: `Nmap state element is invalid.` انتهى Task بشكل صحيح إلى `FAILED` (version 3، `exit_code=0`، و`error_message=NMAP_XML_INVALID`)؛ وهذا يثبت أن إصلاح failure finalization يعمل كما صُمم.

لم تنشأ Assets أو Asset Observations أو Evidence لأن الفشل وقع قبل ingestion. بقيت قاعدة SQLite سليمة: `quick_check=ok`، و`foreign_key_check` بلا مخالفات، والـschema عند 0006. كان stderr الخارجي فارغًا ولم يُحفظ XML الخام. لا توجد retry أو fallback أو محاولة إضافية.

الخطوة الصحيحة التالية ليست إعادة P3 فورًا: يلزم patch offline إضافي ومحدد لعقدة Nmap القياسية `state` التي قد تحمل metadata مثل reason/TTL؛ يجب قبول allowlist محدودة لهذه الخصائص مع استخدام `state` فقط في normalization، ثم اختبارها offline وطلب تفويض جديد منفصل قبل أي invocation حي لاحق.

## 12. Patch offline لعقدة state metadata

اكتمل patch offline المحدد لعقدة Nmap `state`. يقبل parser الآن `state` بشرط وجود القيمة الإلزامية غير الفارغة `state`، ويسمح فقط بالخصائص الاختيارية القياسية `reason` و`reason_ttl`. يجب أن تكون `reason` غير فارغة ومحدودة بالحجم، وأن تكون `reason_ttl` قيمة عشرية بين 0 و255. أي خاصية إضافية أو غياب `state` أو metadata غير صالحة يُرفض بالرمز typed `NMAP_XML_INVALID`.

يحفظ normalization قيمة `state` فقط؛ ولا يحتفظ بـreason أو TTL ضمن Observations أو Evidence. أضيفت fixtures للقبول والرفض، ونجحت البوابات الرسمية عند **402 اختبارًا**. لم يُنفذ أي scan حي ضمن هذا patch، لذلك يتطلب أي P3 جديد تفويضًا صريحًا منفصلًا.

## 13. محاولة P3 المحلية: service metadata

نفذت بيئة WSL invocation حيًا واحدًا مصرحًا به بعد نجاح preflight الكامل. أثبت receipt أن Scope وTarget `127.0.0.1` وSHA-256 للـbinary وquality gates كانت سليمة، ووصل التنفيذ إلى Nmap خلال 3144ms. توقفت النتيجة عند parser بالخطأ redacted `NMAP_XML_INVALID: Nmap service element is invalid.` ولم يحدث retry أو توسع نطاق.

سبب التوقف هو أن XML القياسي لـNmap يستخدم `conf` و`method` كخصائص إلزامية لعقدة `service`، إضافة إلى metadata اختيارية، بينما allowlist السابقة كانت ضيقة أكثر من اللازم. patch offline الجديد يطبق allowlist مغلقة ويُدقق كل قيمة، لكنه يحتفظ بعد التحليل بـ`name` و`product` و`version` فقط؛ ولا يخزن CPE أو fingerprint أو host metadata أو confidence/method. نجحت البوابات عند **409 اختبارات**. يلزم تفويض P3 جديد منفصل قبل أي تجربة حية لاحقة.
