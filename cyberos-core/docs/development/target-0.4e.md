# Module 0.4.e — Scope & Target Repositories + Persistence Mapping

## الحالة

تم تنفيذ persistence adapters لـScope وTarget فوق Schema 0003 وUnitOfWork الحالي. بقي Domain خاليًا من SQLite وSQL، ولم تُضف Matcher Engine أو ScopeValidationService أو CLI أو أي network side effect.

## Ports وMappers

أضيفت `ScopeRepository` و`TargetRepository` كـProtocol ports داخل Domain، وتعرّفان عمليات `add/get/list/exists/update/archive` دون معرفة adapter أو transaction implementation. أضيفت `scope_from_row/scope_to_params` و`target_from_row/target_to_params`. يعتمد row mapping على قائمة أعمدة ثابتة، ويعيد Domain model بعد التحقق الكامل من UUID4 وUTC timestamps وenums وcanonical Target value وScope invariants.

أي فشل في mapping يتحول إلى `PERSISTENCE_MAPPING_FAILED` مع أسماء الحقول فقط؛ لا يتم تسريب `sqlite3.Row` أو SQL أو stack trace إلى المستهلك.

## Scope repository

ينفذ `SQLiteScopeRepository` الإضافة والقراءة والقائمة حسب Engagement بترتيب deterministic، و`exists` والتحديث والأرشفة. قبل الإضافة يتحقق من وجود Engagement ومن عدم أرشفته. يترجم duplicate Scope name إلى `SCOPE_NAME_CONFLICT`، وmissing parent إلى `ENGAGEMENT_NOT_FOUND`، وparent archived إلى `ENGAGEMENT_ARCHIVED`. التحديث والأرشفة يستخدمان `WHERE id = ? AND version = ?` ويترجمان stale writes إلى `CONCURRENCY_CONFLICT`.

## Target repository

ينفذ `SQLiteTargetRepository` الإضافة والقراءة والقائمة حسب Scope و`exists` والتحديث والأرشفة. يفرض قبل كل mutation أن يكون Scope موجودًا وفي `draft`؛ ويرفض Scope authorized بـ`AUTHORIZED_SCOPE_IMMUTABLE` وScope archived بـ`SCOPE_ARCHIVED`، ويرفض الحالات غير القابلة للتعديل بـ`SCOPE_NOT_DRAFT`. duplicate `(scope_id, rule, kind, value)` يتحول إلى `TARGET_DUPLICATE`، وmissing parent إلى `SCOPE_NOT_FOUND`.

## Transaction and security boundary

المستودعات لا تملك `commit` أو `rollback`؛ `SQLiteUnitOfWork` يملك transaction boundary. جميع SQL statements parameterized، والـrepositories تعيد Domain objects فقط. اختبارات rollback تثبت عدم بقاء Scope أو Target عند exception داخل UnitOfWork. Boundary review أثبت عدم وجود imports أو calls لـSQLite/network داخل Domain، وعدم إضافة Matcher أو ScopeValidationService أو CLI.

## Verification

تمت إضافة اختبارات round-trip دقيقة للـUUID وUTC وcanonical values، وCRUD/list/exists، وoptimistic concurrency، وarchive/version persistence، وtyped uniqueness errors، وmissing/archived parent guards، وauthorized-scope immutability، وrollback، وعدم تسريب sqlite rows. النتيجة: **200 اختبارًا ناجحًا**، مع نجاح Ruff وmypy strict وformatting وwheel build.
