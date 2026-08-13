# Module 0.4.f — Scope Matcher Engine & Safety Policy

## الحالة

تم تنفيذ `ScopeMatcher` كمحرك Domain نقي وحتمي فوق Scope وTarget models. لا ينفذ DNS أو HTTP أو subprocess أو filesystem أو database activity، ولا يحتوي ScopeValidationService أو Application Services أو CLI.

## MatchResult contract

يعيد المحرك `MatchResult` immutable يحتوي على `decision` و`matched_target_id` و`matching_rule` و`reason`. القرارات هي `INCLUDED` و`EXCLUDED` و`DENIED_OUT_OF_SCOPE`. عند الرفض لا يتم إرجاع Target ID أو Rule، لتجنب إعطاء caller معلومات تفصيلية غير لازمة عن قواعد النطاق.

## Evaluation policy

يطبق المحرك الترتيب الأمني التالي بشكل حتمي:

```text
1. Scope must be authorized and not expired.
2. Active exclude match → EXCLUDED immediately.
3. Active include match → INCLUDED.
4. Everything else → DENIED_OUT_OF_SCOPE.
```

Scope draft أو validated أو archived يفشل مغلقًا حتى إذا تطابقت قاعدة. Scope authorized المنتهي يفشل مغلقًا كذلك. Targets المؤرشفة لا تدخل evaluation. القواعد تُرتب حسب Target ID لضمان deterministic result إذا تطابقت عدة قواعد من الفئة نفسها.

## Matching semantics

يطابق FQDN الاسم canonical exact بصورة case-insensitive نتيجة canonicalization. يطابق wildcard الـroot domain نفسه وكل subdomains التابعة له، لكنه لا يطابق suffix مشابهًا بلا label boundary مثل `badexample.com` ولا domain خارج suffix. يطابق IPv4 وIPv6 العنوان الفردي من العائلة نفسها، ويختبر CIDR membership مع family-aware narrowing.

يحلل URL محليًا باستخدام canonical URL parser، ثم يستخدم host/IP المستخرج عند مقارنة FQDN أو wildcard أو IP أو CIDR. URL Target نفسه يحتاج exact canonical URL، بما في ذلك path وquery بعد normalization. Credentials وfragments وURL invalid candidates تفشل مغلقًا ولا تسبب أي probing أو resolution.

## Verification

تغطي Matrix Unit Tests precedence conflict بين include وexclude، FQDN exact boundaries، wildcard root/subdomain boundaries، IPv4 CIDR داخل/خارج subnet، IPv6 compression وCIDR، exact IP family separation، URL host extraction وports/query، credentials/fragments، invalid candidates، non-authorized/expired scopes، وarchived targets.

نجحت **223 اختبارًا**، إضافة إلى Ruff وmypy strict وformatting وwheel build. Boundary review أثبت عدم وجود network side effects أو nondeterministic filesystem/time/random behavior داخل matcher.
