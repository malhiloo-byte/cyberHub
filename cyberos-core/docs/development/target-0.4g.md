# Module 0.4.g — Application Scope Services & Boundary Guards

## الحالة

تم تنفيذ `ScopeValidationService` كحد تطبيقي read-only فوق ScopeRepository وTargetRepository وScopeMatcher. لا ينفذ Task Runner أو subprocess أو DNS أو HTTP أو CLI operations.

## Explicit candidate contract

اعتمدت الشريحة القرار المعماري Option 2: `TargetCandidate` immutable DTO يحتوي `raw_value` و`TargetKind` صريحًا. يرفض DTO النص الفارغ والنوع المجهول، ولا يستخدم auto-inference. هذا يمنع ambiguity بين FQDN وURL وIP/CIDR ويحافظ على fail-closed semantics من 0.4.a.

## Service operations

`evaluate_candidate(scope_id, candidate, evaluated_at)` يقرأ Scope وTargets داخل UnitOfWork، يغلق المعاملة دون تعديل، يعيد بناء aggregate للتحقق، ثم يمرر candidate مباشرة إلى ScopeMatcher. النتيجة `ScopeEvaluationResult` تحتوي Scope ID، candidate، decision، matched Target ID، matching rule، reason، evaluation timestamp، Scope status، وScope version، بحيث تكون قابلة للتدقيق دون SQL leakage.

`authorize_execution(scope_id, candidate, evaluated_at)` لا ينشئ execution job ولا ينفذ action. يحول نتيجة INCLUDED فقط إلى `ExecutionAuthorization` تحتوي Scope ID وcandidate وauthorization timestamp وmatched Target ID وInclude rule وreason وScope version. كل نتيجة أخرى تفشل typed وبشكل fail-closed.

## Boundary policy

Scope غير authorized يعيد `SCOPE_NOT_AUTHORIZED`، وScope archived يعيد `SCOPE_ARCHIVED`، وScope المنتهي يعيد `SCOPE_EXPIRED`. نتيجة EXCLUDED تتحول إلى `TARGET_EXCLUDED`، وأي DENIED_OUT_OF_SCOPE أو candidate invalid يتحول إلى `TARGET_OUT_OF_SCOPE`. لا يوجد مسار يسمح بإرجاع authorization عند الرفض.

## Verification

تغطي اختبارات التكامل workflow المقبول، draft وarchived وexpired scopes، excluded targets، missing Scope، DTO immutability والتحقق، وغياب SQL أو تفاصيل داخلية في الأخطاء. نجحت **230 اختبارًا**، مع نجاح Ruff وmypy strict وformatting وwheel build. Boundary review أكد أن الشريحة authorization-only ولا تحتوي Task/Job execution أو subprocess أو network أو CLI.
