# Module 0.5.d — Task CLI & Full System Integration Audit

## Design status

هذه وثيقة التصميم المعتمدة للتنفيذ قبل إضافة Task CLI. لا تضيف Module 1 أو network tooling.

## Application boundary

سيضاف `TaskService` كطبقة Application فوق `ScopeValidationService` و`TaskExecutionEngine` و`SQLiteTaskRepository`. الـCLI يستدعي service فقط ولا ينشئ Task ولا يقرأ SQLite ولا يقرر authorization.

في `run` يمر الطلب بهذا الترتيب:

```text
explicit scope_id + target_id + TargetCandidate + argv
        ↓
ScopeValidationService.authorize_execution
        ↓
matched_target_id == requested target_id guard
        ↓
Task.create (Target-Bound + Time-Aware authorization)
        ↓
persist pending TaskRecord and commit
        ↓
TaskExecutionEngine.execute
        ↓
persist terminal TaskRecord with ExecutionResult and optimistic version
```

يُستخدم transaction قصير لحفظ pending، ثم التنفيذ خارج transaction، ثم transaction ثانية لحفظ terminal snapshot. هذا يمنع إبقاء SQLite transaction مفتوحة أثناء process execution، ويترك optimistic concurrency يحمي التحديث النهائي.

## CLI contract

| Command | Contract |
|---|---|
| `cyberos task run SCOPE_ID TARGET_ID --kind KIND --value VALUE COMMAND...` | authorization + create + execute + persist؛ command يتحول مباشرة إلى argv tuple |
| `cyberos task list --scope-id ID` | list by scope بترتيب `created_at DESC, id ASC` |
| `cyberos task list --target-id ID` | list by target بترتيب deterministic |
| `cyberos task show TASK_ID` | snapshot كامل مع status وspec وresult streams وexit code |

لا يوجد auto-inference للـTargetKind، ولا shell command string، ولا `shell=True`. يجب أن تكون `--kind` و`--value` صريحين، ويجب أن يحتوي `COMMAND...` على جزء واحد على الأقل. `task list` يتطلب scope أو target filter واحدًا على الأقل.

## Output envelope and rendering

كل أمر يستخدم `OperationResult` الحالي مع `ok`, `data/error`, و`meta.correlation_id/duration_ms`. JSON يعرض stdout/stderr كنص UTF-8 مع replacement عند الحاجة، إضافة إلى exit code وtruncated وduration_ms وtimeout_exceeded وerror_message. Text يعرض الحقول العملية ويطبع correlation ID. لا تعرض CLI raw SQL أو traceback أو internal exception.

## Exit policy

| Outcome | Exit code |
|---|---:|
| successful run/list/show | 0 |
| invalid input, malformed UUID, missing argument, domain contract error | 1 |
| authorization rejection, excluded/out-of-scope target, failed/timeout task run | 2 |

`task show` يعرض historical failed Task كعملية قراءة ناجحة؛ code 2 يخص نتيجة `run` الفاشلة أو rejection الأمني، لا فشل القراءة نفسها.

## Audit test

سينشئ الاختبار قاعدة SQLite جديدة، يطبق 0001–0004، يبني Workspace ثم Engagement ثم draft Scope ثم Include Target، يعيد Scope إلى authorized، يستخرج `ExecutionAuthorization`، ينفذ `echo` أو `python -c` محليًا، ويحفظ ويسترجع TaskRecord. ثم يختبر candidate مستبعدًا ويتأكد من عدم وجود Task جديد ومن خروج CLI الأمني المناسب. لا يستخدم الاختبار DNS أو HTTP أو أدوات شبكية.

## Security and extension points

كل التنفيذ يمر عبر authorization وTask.create. الـargv tuple يُمرر إلى execution engine دون shell parsing. لا يقبل CLI raw target inference أو direct subprocess. مستقبلاً يمكن إضافة task cancellation، pagination، audit event log، وartifact retention دون تغيير CLI boundary الحالي.
