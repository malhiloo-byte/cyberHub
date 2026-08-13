# Module 0.4.a — Domain Primitives & Target Canonicalization

## الحالة

تم تنفيذ الشريحة كطبقة Domain نقية فوق Module 0.3. لا تحتوي هذه الشريحة على SQLite أو migrations أو repositories أو CLI أو Matcher Engine أو ScopeValidationService، ولا تنفذ DNS أو HTTP أو subprocess أو أي network side effect.

## المخرجات

أضيفت `ScopeId` و`TargetId` كـ`NewType` فوق UUID مع تحقق UUID4، إضافة إلى `ScopeStatus` و`TargetRule` و`TargetKind`. أضيفت أخطاء typed مستقلة لـinvalid value وcontrol characters وwildcard وIP وnetwork safety وURL وunknown kind.

ينفذ `TargetCanonicalizer` و`CandidateParser` تحويلًا محليًا deterministic للأنواع الستة: FQDN، wildcard، IPv4، IPv6، CIDR، وURL. يعتمد FQDN على lowercase وإزالة trailing dot وIDNA encoding ثابت، ويقبل wildcard بصيغة `*.` في أقصى اليسار فقط. يتم ضغط IPv6، وتطبيع CIDR إلى network/prefix، وتوحيد scheme/host/port/path/query في URL مع رفض credentials وfragments وwildcards.

سياسة الأمان في هذه الشريحة ترفض default routes `0.0.0.0/0` و`::/0`، والقيم ذات control characters، والمسافات الداخلية، والأنماط الغامضة. IPv4 ذات leading-zero octets تُعامل كصيغة غير صارمة وترفضها مكتبة parsing القياسية بدل إعادة تفسيرها بصمت.

## الاختبارات

تغطي الاختبارات UUID4 stability وenum values، canonical forms للأنواع الستة، malformed FQDN، unsafe wildcard، malformed IP/CIDR، IPv6 compression، URL credentials/fragments/unsupported schemes، وtyped error leakage boundaries. الاختبارات pure unit ولا تنشئ قاعدة بيانات ولا تتصل بالشبكة.

## حدود الشرائح اللاحقة

لا يوجد Scope aggregate أو Target aggregate في هذه الشريحة؛ توجد primitives فقط. لا يوجد matcher precedence أو Include/Exclude evaluation؛ ذلك مؤجل إلى 0.4.f. ولا يوجد SQL schema؛ migration 0003 مؤجل إلى 0.4.d بعد Schema Design Review منفصل.
