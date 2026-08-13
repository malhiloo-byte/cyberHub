# CyberOS Module 0.1 — Execution Checklist

- [x] تثبيت dependencies وقفل الإصدارات
- [x] تنفيذ core contracts
- [x] تنفيذ configuration وlogging
- [x] تنفيذ CLI
- [x] كتابة الاختبارات وفحوصات الجودة والأمن
- [x] تحديث التوثيق
- [x] إنشاء checkpoint وتسليم المرحلة

## Module 0.2 — Persistence Kernel

- [ ] اعتماد تصميم SQLite المحلي المحصّن
- [ ] تحديد Database layout وconnection lifecycle
- [ ] تحديد schema versioning وmigration runner
- [ ] تحديد transaction وconcurrency policy
- [ ] تعريف Repository Interfaces وpersistence contracts
- [ ] كتابة contract tests للـCRUD والـtransactions
- [ ] اختبار rollback وعدم فقدان أو فساد البيانات
- [ ] اختبار migration upgrade وdowngrade policy
- [ ] مراجعة SQLite security وfile permissions وbackup boundaries
- [ ] تنفيذ التوثيق والأمثلة وquality gates
- [ ] إنشاء checkpoint وتسليم Module 0.2

### 0.2.a — Database Settings + Path/Security Policy

- [x] إضافة DatabaseSettings إلى configuration models
- [x] إضافة environment overrides الخاصة بقاعدة البيانات
- [x] تنفيذ path resolver آمن للمسار الافتراضي والـcustom path
- [x] تنفيذ parent directory creation بسياسة واضحة
- [x] تنفيذ file mode policy بصلاحية 0600 للملفات الجديدة
- [x] رفض المسارات غير الصالحة أو غير القابلة للكتابة بأخطاء typed
- [x] كتابة unit وsecurity tests للحالات الطبيعية والحدية
- [x] تحديث config example وREADME وتوثيق 0.2.a
