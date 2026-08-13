# Module 0.4.b — Scope & Target Aggregates

## الحالة

تم تنفيذ الشريحة كـimmutable Domain layer فوق 0.4.a. لا تحتوي على SQLite أو migration 0003 أو repositories أو Matcher Engine أو ScopeValidationService أو CLI أو network activity.

## Target model

أضيف `Target` باستخدام `TargetId` و`ScopeId` و`TargetRule` و`TargetKind` و`TargetStatus` typed values. ينشئ `Target.create` قيمة canonical فقط عبر `TargetCanonicalizer`، ويثبت UTC timestamps وversion يبدأ من 1. أي Target غير canonical يُرفض حتى لو كان قابلًا للتحليل، مما يمنع اختلاف representation داخل aggregate أو persistence لاحق.

الأرشفة immutable: `archive` يعيد نسخة جديدة بحالة `archived` ويثبت `archived_at` ويرفع version. Target مؤرشف لا يقبل update أو archive مرة ثانية. `with_value` يعيد نسخة جديدة بعد canonicalization ولا يعدل الكائن الأصلي.

## Scope aggregate

أضيف `Scope` كـimmutable aggregate يملك tuple من Targets ويشير إلى `EngagementId`. lifecycle هو:

```text
draft → validated → authorized → archived
draft → archived
validated → archived
```

`mark_validated` يثبت `validated_at`. `authorize` يتطلب reference غير فارغ، يثبت `authorized_at`، ويقبل expiry مستقبلية فقط. `archive` نهائي ويثبت `archived_at`. أضيفت `return_to_draft` كعملية صريحة من validated أو authorized لإعادة الفحص والتفويض عند الحاجة.

سُمّيت عملية الانتقال `mark_validated` بدل `validate` لأن `validate` اسم classmethod محجوز في `pydantic.BaseModel`، ولتفادي override غير مقصود أو تعارض مع type checking. هذا تغيير داخلي في API الشريحة ولم يضف أي alias صامت.

## Authorized Scope immutability

لا يسمح Scope بحالة `authorized` بإضافة Target أو تعديل Target أو أرشفته. يعيد النظام `AUTHORIZED_SCOPE_IMMUTABLE`. يجب استدعاء `return_to_draft` صراحة أولًا، ثم تعديل Targets، ثم `mark_validated` و`authorize` من جديد. Scope مؤرشف يرفض أي state change أو Target mutation ويرجع `SCOPE_ARCHIVED`.

تتحقق Domain layer كذلك من أن كل Target يملك نفس `scope_id`، وتمنع timestamps غير UTC، وتفرض version إيجابيًا، وتمنع expiry قبل أو عند authorization time.

## الاختبارات والحدود

تمت إضافة pure unit tests لإنشاء Target وcanonical values والأرشفة والتحديث، ولـScope lifecycle والauthorization وexpiry والعودة الصريحة إلى draft، ورفض transitions، وauthorized immutability، وarchived guards، وforeign Target ownership. لا تنشئ الاختبارات قاعدة بيانات ولا تتصل بالشبكة.

Boundary review أثبت عدم وجود SQLite أو persistence أو network أو subprocess imports/calls، وعدم وجود migration أو repository أو matcher implementation ضمن domain packages. Migration inventory ما زال يحتوي 0001 و0002 فقط؛ 0003 مؤجل إلى 0.4.d بعد Schema Design Review.
