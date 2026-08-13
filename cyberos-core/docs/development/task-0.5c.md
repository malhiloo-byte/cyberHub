# Module 0.5.c — Task Persistence & Migration 0004

## Implementation summary

تم تنفيذ persistence slice فوق Migration 0003 دون تعديل أي migration سابقة. أصبح `ExecutionResult` عقدًا محايدًا في `cyberos.domain.task.result`، مع re-export صريح من `cyberos.execution.runner` يحافظ على imports السابقة. أضيف `TaskRecord` immutable projection ليجمع Task snapshot مع نتيجة التنفيذ دون إدخال SQLite أو repository concerns إلى Domain.

## Schema

أنشأ `0004_tasks.sql` جدول `tasks` المرتبط بـ`scopes` و`targets` عبر `ON DELETE RESTRICT` و`ON UPDATE RESTRICT`. تُخزّن command وenvironment allowlist كـJSON مع `json_valid` وarray checks. تُفرض قيود status والقيم العددية وUTC ISO-8601 timestamps وversion وboolean fields وoutput length. ويُفرض status/result matrix بحيث لا تحمل `pending` و`running` نتيجة، بينما تتطلب الحالات terminal بيانات execution المناسبة.

الفهارس المستخدمة هي `idx_tasks_scope_status` و`idx_tasks_target_status`. استخدمت migration ملف SQL صريحًا دون `IF NOT EXISTS` أو `BEGIN` أو `COMMIT` داخلي، وبقيت مسؤولية atomicity وchecksum لدى MigrationRunner.

## Mapper and repository

يقوم `TaskMapper` بتحويل UUID4 وTaskStatus وUTC datetimes وExecutionSpec JSON وbytes وduration milliseconds وtimeout/error metadata في الاتجاهين. أي JSON أو row لا يمر validation يتحول إلى `PERSISTENCE_MAPPING_FAILED` دون تسريب raw row.

يوفر `SQLiteTaskRepository` العمليات `add`, `get`, `list_by_scope`, `list_by_target`، و`update_status_and_result`. كل SQL parameterized وثابت، ولا يملك repository commit أو rollback؛ `SQLiteUnitOfWork` هو صاحب transaction. التحديث يستخدم `WHERE id = ? AND version = ?`، ويرفع `TASK_NOT_FOUND` أو `CONCURRENCY_CONFLICT` بعد existence check، ثم يعيد قراءة snapshot المحدث.

## Verification

أضيفت اختبارات migration وrepository تغطي تطبيق 0004، checksum، forward-only/idempotency، `quick_check`، `foreign_key_check`، الفهارس، pending وcompleted وfailed round-trip، truncated stdout/stderr، timeout/error metadata، optimistic concurrency، rollback boundary، FK protection للـScope وTarget، وعدم تسريب `sqlite3.Row`.

النتيجة النهائية: **272 اختبارًا ناجحًا**، ونجاح Ruff وmypy `--strict` وformatting وwheel build. لم تُضف CLI أو subprocess أو network tools في هذه الشريحة. الاختبارات التنفيذية السابقة بقيت ناجحة بعد نقل العقد.

## Known boundaries

حفظ stdout وstderr حاليًا داخل SQLite BLOB بحد `max_output_bytes` لكل stream، دون artifact storage أو compression أو retention scheduler. Task persistence تحفظ snapshot الحالي؛ event/audit history وCLI وapplication orchestration مؤجلة للشرائح التالية.

## Next slice

الخطوة التالية المقترحة هي **0.5.d — Task CLI & Full System Integration Audit**، مع مراجعة حدود CLI، envelopes، إدارة lifecycle، ودمج persistence مع execution دون السماح بتجاوز authorization أو optimistic concurrency.
