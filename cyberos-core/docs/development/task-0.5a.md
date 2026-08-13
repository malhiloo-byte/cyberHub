# Module 0.5.a — Task Domain Models & Execution Specs

## الحالة

تم تنفيذ الشريحة كطبقة Domain نقية فوق عقد التفويض في Module 0.4. لا تحتوي على `0004_tasks.sql` أو Repositories أو CLI أو subprocess أو asyncio أو network activity.

## Target-Bound and Time-Aware authorization

تم تحديث `ScopeEvaluationResult` و`ExecutionAuthorization` لإضافة `expires_at` المنقول من Scope. أصبح إنشاء Task يتطلب `ExecutionAuthorization` structural contract صالحًا، و`scope_id` و`target_id` صريحين. ترفض Domain layer إنشاء Task إذا لم يكن التفويض من النوع التعاقدي، أو إذا اختلف Scope ID، أو اختلف Target ID عن `matched_target_id`، أو كان `expires_at` منتهيًا عند وقت الإنشاء، أو لم تكن القاعدة Include.

هذا الفصل يمنع تمرير raw target strings إلى Task. لا يستورد Task application layer؛ بل يعتمد structural contract صغيرًا (`scope_id`, `matched_target_id`, `matching_rule`, `expires_at`) حتى تبقى Dependency Direction سليمة.

## Task aggregate and lifecycle

يحتوي Task على `TaskId` UUID4، `ScopeId`، `TargetId`، `TaskStatus`، `ExecutionSpec`، authorization expiry، timestamps execution، وversion يبدأ من 1. الحالة الابتدائية `pending`، والانتقالات المسموحة هي:

```text
pending → running → completed
                    → failed
                    → cancelled
pending → cancelled
```

الحالات terminal لا تقبل transitions لاحقة. كل transition يعيد immutable Task جديدًا، يثبت timestamp الخاص به، ويرفع version. الانتقالات غير القانونية ترفع `TASK_INVALID_TRANSITION`.

## ExecutionSpec and EnvPolicy

`ExecutionSpec.command` يجب أن يكون tuple غير فارغ من non-empty strings، وليس shell command string أو list قابلة للتعديل. `timeout_seconds` محصور بين 1 و3600، والافتراضي 30 ثانية. `max_output_bytes` محصور بين 1 و16 MiB، والافتراضي 1 MiB. `EnvPolicy` هي immutable allowlist فريدة من environment names ولا تسمح بـ`=` أو duplicate keys.

هذه الشريحة تصف policy فقط؛ لا تقوم بتشغيل command أو بناء shell invocation. 0.5.b هو المسؤول لاحقًا عن تنفيذ argv عبر `exec`-style subprocess مع تطبيق هذه الحدود.

## Verification

تغطي pure unit tests إنشاء Task بتفويض صالح، رفض raw target strings، Scope/Target mismatch، authorization expiry، missing/non-Include authorization، lifecycle transitions، terminal guards، command/timeout/output/env validation، وimmutable allowlists. النتيجة: **252 اختبارًا ناجحًا**، مع نجاح Ruff وmypy strict وformatting وwheel build. Boundary review أكد عدم وجود persistence أو application import أو subprocess أو DNS أو HTTP.

## Next boundary

الخطوة التالية المقترحة هي **0.5.b — Safe Subprocess Execution Engine**. يجب أن تستقبل executor `Task` و`ExecutionSpec` بعد التحقق، وتستخدم argv tuple وenvironment allowlist وtimeout/output caps، دون shell parsing.
