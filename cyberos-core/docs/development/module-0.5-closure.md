# Module 0.5 — Task Execution & Persistence Closure

## Scope

أغلق Module 0.5 السلسلة من Task domain إلى التنفيذ المحلي والتخزين وCLI. أصبح المسار:

```text
ScopeValidationService
  → ExecutionAuthorization
  → Task.create
  → SQLiteTaskRepository (pending)
  → TaskExecutionEngine / SafeSubprocessRunner
  → SQLiteTaskRepository (terminal result)
  → Task CLI envelopes
```

## 0.5.a–0.5.b foundations

يفرض Task عقد Target-Bound وTime-Aware authorization، ويحظر raw target strings والتفويض المنتهي أو غير Include. `SafeSubprocessRunner` يستخدم `asyncio.create_subprocess_exec` مع argv tuple، بيئة allowlist معزولة، output caps، وtimeout escalation عبر SIGTERM ثم SIGKILL. `TaskExecutionEngine` يعيد Taskًا immutable إلى `RUNNING` ثم `COMPLETED` أو `FAILED`.

## 0.5.c persistence

Migration `0004_tasks.sql` تحفظ snapshot Task وExecutionResult مع JSON validation وstatus/result consistency وUTC timestamp checks وFK RESTRICT إلى Scope وTarget. `TaskRecord` عقد محايد، و`TaskMapper` يحافظ على UUID/UTC/enum/bytes/duration round-trip. `SQLiteTaskRepository` يعمل داخل `SQLiteUnitOfWork` ويستخدم optimistic concurrency.

## 0.5.d application and CLI

`TaskService` هو orchestrator الوحيد. يحجز authorization، يتحقق من `target_id`، يحفظ pending داخل transaction قصيرة، ينفذ خارج transaction، ثم يحفظ terminal result داخل transaction ثانية. أضيفت الأوامر:

```text
cyberos task run SCOPE_ID TARGET_ID --kind KIND --value VALUE -- COMMAND...
cyberos task list --scope-id ID
cyberos task list --target-id ID
cyberos task show TASK_ID
```

يستخدم CLI `OperationResult` بصيغة JSON أو text، ويعرض bytes كنص UTF-8 آمن مع replacement. exit code هو 0 للنجاح، 1 لأخطاء الإدخال والعقد، و2 للرفض الأمني أو فشل/timeout run. قراءة `task show` لمهمة failed تظل عملية قراءة ناجحة ولا تتحول تلقائيًا إلى code 2.

## Full System Integration Audit

ينشئ الاختبار قاعدة SQLite جديدة، يطبق migrations 0001–0004، يبني Workspace وEngagement وScope، يضيف Include وExclude Targets، يفوض Scope، يستخرج `ExecutionAuthorization`، ينفذ أمرًا محليًا محايدًا عبر TaskService، ويتحقق من persisted TaskRecord وstdout. كما يمرر الهدف excluded ويتأكد من `TARGET_EXCLUDED` وعدم إنشاء Task جديد. اختبار CLI يثبت أن shell metacharacters تبقى literal argv ولا تُفسر.

## Verification result

النتيجة النهائية هي **276 اختبارًا ناجحًا**. اجتازت البوابة pytest، Ruff، mypy `--strict`، formatting، وwheel build. مراجعة الحدود أكدت عدم إضافة Module 1، وعدم وجود network tools أو DNS أو HTTP أو direct CLI subprocess أو shell execution. تم تحديث checklist والوثائق وحفظ checkpoint الإغلاق.

## Next boundary

الخطوة التالية المقترحة هي Module 1 — Recon Orchestrator. يجب أن يبدأ بتصميم architecture منفصل يستهلك TaskService وScope authorization، ولا يضيف أدوات reconnaissance أو plugins قبل تحديد contracts والـaudit model.
