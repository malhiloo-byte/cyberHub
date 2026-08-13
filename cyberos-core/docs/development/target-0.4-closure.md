# Module 0.4 — Target & Scope Management Closure

## النتيجة

أُغلق Module 0.4 رسميًا فوق Module 0.3. أصبحت لدى CyberOS طبقة محلية privacy-first لإدارة Scope وTarget، canonicalization، matching، authorization، execution boundary guards، وCLI قابل للأتمتة. لا تنفذ هذه الطبقة Recon أو Scanner أو Job أو Task أو Network activity.

## ما تم بناؤه

بدأت الشريحة 0.4.a بـScopeId وTargetId وEnums وcanonicalization deterministic للأنواع الستة: FQDN وwildcard وIPv4 وIPv6 وCIDR وURL. في 0.4.b أضيفت Scope وTarget aggregates immutable مع lifecycle وarchive/version guards. في 0.4.c أضيفت Migration 0003 بجدولي `scopes` و`targets` وقيود FK/UNIQUE/CHECK وRESTRICT.

في 0.4.e أضيفت repository ports وmappers وSQLite repositories مع round-trip validation وoptimistic concurrency وtyped error translation. في 0.4.f أضيف ScopeMatcher بقاعدة `exclude > include > fail-closed`. في 0.4.g أضيفت `TargetCandidate` و`ScopeValidationService` وDTOs التدقيق، بحيث لا يصدر `ExecutionAuthorization` إلا عند INCLUDED داخل Scope authorized وغير منتهٍ. وأخيرًا أضيفت في 0.4.h أوامر CLI الأربعة المطلوبة.

## CLI contract

```text
cyberos scope create <engagement-id> <name> [--description] [--json]
cyberos target add <scope-id> --rule <include|exclude> --kind <kind> --value <value> [--json]
cyberos scope authorize <scope-id> --authorization-reference <reference> [--expires-at] [--json]
cyberos scope evaluate <scope-id> --kind <kind> --value <value> [--json]
```

`TargetKind` إلزامي ولا يوجد auto-inference. `scope evaluate` read-only ويعيد OperationResult JSON أو human-readable text. القرار INCLUDED يخرج code 0، EXCLUDED وDENIED_OUT_OF_SCOPE يخرجان code 2، ومدخلات CLI أو lifecycle errors الجديدة تخرج code 1. لا يعرض المستخدم raw SQL أو traceback.

## Security and boundaries

قاعدة التفويض هي `authorized + not expired + active include match + no active exclude match`. Scope غير authorized أو archived أو expired يفشل مغلقًا. Exclude يتغلب دائمًا على Include. لا تستدعي Domain وMatcher وScopeValidationService DNS أو HTTP أو subprocess، ولا تملك CLI matching logic أو execution adapters.

## Verification

النتيجة النهائية هي **233 اختبارًا ناجحًا**. اجتازت البوابة `pytest` وRuff و`mypy --strict` وformatting وwheel build. تضمنت المراجعة اختبارات pure domain، migration/schema، repositories، services، matcher matrix، authorization boundary، CLI E2E، JSON/text output، exit codes، no-traceback/no-SQL-leakage، وغياب side effects.

## Checkpoint and next module

Checkpoint الإغلاق النهائي: `17e66812`.

الخطوة التالية المقترحة للمراجعة، دون تنفيذ تلقائي، هي **Module 0.5.a — Task Domain Models & Execution Specs**. يجب أن يكون عقده الأمني الأول هو قبول `ExecutionAuthorization` فقط، مع رفض أي raw target string أو unvalidated candidate.
