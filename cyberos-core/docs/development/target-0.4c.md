# Module 0.4.c — Schema Design Review & Migration 0003

## الحالة

تم تنفيذ ومراجعة `0003_target_scope.sql` فوق `0002_workspace_engagement.sql` باستخدام MigrationRunner نفسه من Module 0.2. لم تُعدّل 0001 أو 0002، ولم تُضف Repositories أو Mappers أو Matcher أو ScopeValidationService أو CLI.

## Schema inventory

تحتوي قاعدة البيانات بعد التطبيق على الجداول التالية فقط:

```text
schema_migrations
workspaces
engagements
scopes
targets
```

أضيف جدول `scopes` بعلاقة إلزامية إلى `engagements`، وجدول `targets` بعلاقة إلزامية إلى `scopes`. العلاقات تستخدم `ON DELETE RESTRICT` و`ON UPDATE RESTRICT` لحماية السجل التاريخي ومنع orphan rows أو حذف parent يملك children.

## Scope constraints

يقبل Scope الحالات `draft` و`validated` و`authorized` و`archived`. يفرض SQL invariants الخاصة بتوافق timestamps مع الحالة، ووجود authorization reference عند authorized، ووجود validated/authorized timestamps، وexpiry بعد authorization، وarchive timestamp عند archived. تُفحص timestamps كقيم UTC ISO-8601 ذات suffix `+00:00` بصيغة حتمية مناسبة لطبقة SQLite الحالية.

يوجد `uq_scopes_engagement_name_nocase` لمنع تكرار Scope name داخل Engagement مع السماح بالتكرار في Engagements مختلفة. كما توجد فهارس الحالة والإنشاء لدعم قوائم مستقبلية دون إدخال Repository في هذه الشريحة.

## Target constraints

يقبل Target القواعد `include` و`exclude` والأنواع الستة المعتمدة: `fqdn` و`wildcard` و`ipv4` و`ipv6` و`cidr` و`url`. يقبل حالتي `active` و`archived`، ويثبت archive timestamp وversion invariants، ويضع حدًا لقيمة canonical المخزنة بطول 4096.

يمنع `uq_targets_scope_rule_kind_value` تكرار قاعدة Target canonical نفسها داخل Scope. وتوجد فهارس scope/status/rule وscope/kind لعمليات القراءة المستقبلية.

## Migration mechanics

الملف لا يحتوي `IF NOT EXISTS` ولا `BEGIN` أو `COMMIT` داخليين. MigrationRunner يملك المعاملة الذرية، ويسجل SHA-256 checksum في `schema_migrations`. التطبيق idempotent، والتاريخ forward-only، وأي فشل في migration 0003 يعيد المعاملة كاملة بحيث لا تبقى جداول 0001 أو 0002 أو 0003 جزئيًا.

## Verification

تغطي اختبارات التكامل تطبيق migration وتسجل checksum، idempotency، schema version 3، `quick_check`، `foreign_key_check`، unique indexes، status/rule/kind/length/version constraints، ISO-8601 UTC checks، foreign-key RESTRICT، atomic rollback، checksum mismatch، وعدم إنشاء جداول مستقبلية خارج Scope وTarget.

العدد الكلي بعد هذه الشريحة هو **192 اختبارًا ناجحًا**، مع نجاح Ruff وmypy strict وformatting وwheel build. لا يحتوي التغيير على network side effects أو SQL خارج migration والاختبارات المقصودة.
