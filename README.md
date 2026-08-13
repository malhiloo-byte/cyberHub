# CyberOS — Personal Cybersecurity Engineering OS

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](cyberos-core/pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-278%20passing-2ea44f?logo=pytest&logoColor=white)](cyberos-core/tests/)
[![Ruff](https://img.shields.io/badge/code%20style-Ruff-D7FF64?logo=ruff&logoColor=111111)](https://docs.astral.sh/ruff/)
[![Mypy](https://img.shields.io/badge/type%20checking-mypy%20strict-1674B1)](https://mypy.readthedocs.io/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> **الحالة الحالية:** Module 0 مغلق رسميًا بعد Zero-State E2E Audit، مع 278 اختبارًا ناجحًا وبنية محلية آمنة جاهزة للبدء في Module 1 — Recon Orchestrator.

## الرؤية التنفيذية

CyberOS ليس مجموعة Scripts أمنية عامة، ولا يعيد بناء أدوات ممتازة موجودة أصلًا دون سبب. إنه **Personal Cybersecurity Engineering OS**: طبقة شخصية Local-first وPrivacy-first فوق المعرفة والأدوات والـengines الموجودة، تساعد صاحب المسار على التعلم والتدريب وتنفيذ Labs وPentesting المصرح به وتنظيم الأدلة وتحليل النتائج وكتابة التقارير وأتمتة الأعمال المتكررة وقياس التطور الحقيقي.

المسار الذي تخدمه المنظومة هو: **Web Penetration Testing → Network / AD / Cloud Security → API Security → Python / Data / ML → Deep Learning → LLM Security → AI Red Teaming → AI Security Engineering / Research**.

## الوضع الحالي

| المجال | الحالة |
|---|---|
| Core contracts, configuration, logging, typed errors | مكتمل ضمن Module 0 |
| SQLite persistence, migrations, UnitOfWork | مكتمل حتى Migration 0004 |
| Workspace / Engagement / Scope / Target lifecycle | مكتمل ومختبر |
| Fail-closed authorization and target-bound tasks | مكتمل ومختبر |
| Safe argv execution and Task CLI | مكتمل ومختبر |
| Zero-State E2E audit | ناجح — 278 اختبارًا |
| Reconnaissance tooling | مؤجل إلى Module 1 بعد اعتماد التصميم |

## المعمارية

```mermaid
flowchart TD
    UI[Web UI — future operator console] --> CLI[CLI / API boundaries]
    CLI --> APP[Application Services]
    APP --> AUTH[Scope Validation & Execution Authorization]
    APP --> TASK[Task Orchestration]
    TASK --> EXEC[SafeSubprocessRunner / TaskExecutionEngine]
    APP --> UOW[UnitOfWork]
    UOW --> REPO[Repositories & Mappers]
    REPO --> DB[(SQLite local database)]
    DOMAIN[Typed Domain Models & Policies] --> APP
    DOMAIN --> REPO
    PLUGINS[Future Plugin / Engine Adapters] --> APP
```

الحدود الأساسية هي: **Domain → Persistence Mappers → Repositories → Application Services → CLI**. الـDomain لا يعرف SQLite أو SQL أو CLI، والـCLI لا يملك business logic. كل تنفيذ يمر عبر `ExecutionAuthorization` صريح، ويُغلق افتراضيًا عند الشك.

## خارطة الطريق

| Module | الاتجاه | الحالة |
|---:|---|---|
| 0 | Core Domain, Scope Safety, Task Execution, Persistence, CLI Audit | **مكتمل** |
| 1 | Recon Orchestrator | التالي — تصميم أولًا |
| 2 | Web Pentest Workflow & Evidence Capture | مخطط |
| 3 | Network / Active Directory Security | مخطط |
| 4 | Cloud Security Operations | مخطط |
| 5 | API Security Engineering | مخطط |
| 6 | Python, Data & ML Security Analytics | مخطط |
| 7 | Deep Learning Security | مخطط |
| 8 | LLM Security | مخطط |
| 9 | AI Red Teaming | مخطط |
| 10 | AI Security Engineering | مخطط |
| 11 | Research Workbench | مخطط |
| 12 | Knowledge, Evidence & Findings Graph | مخطط |
| 13 | Reporting, Metrics & Progress Measurement | مخطط |
| 14 | Platform Hardening, Extensibility & Operations | مخطط |

## التثبيت والتشغيل السريع

يتطلب النواة Python 3.11 أو أحدث. يفضل تشغيلها داخل virtual environment محلي وعدم وضع أسرار داخل ملفات الإعداد أو المستودع.

```bash
git clone <your-github-repository-url> cyberos
cd cyberos/cyberos-core
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[dev]'
./scripts/check.sh
```

يمكن استخدام ملف TOML معزول للتجارب:

```toml
[database]
path = "/absolute/path/to/cyberos.sqlite3"

[runtime]
data_dir = "/absolute/path/to/cyberos-runtime"
log_dir = "/absolute/path/to/cyberos-runtime/logs"
```

## أمثلة CLI

جميع المعرفات صريحة، ولا يوجد auto-inference لنوع Target. تدعم الأوامر التشغيل النصي و`--json`، وتخفي SQL وtracebacks من واجهة المستخدم.

```bash
cyberos workspace create "Web Security Lab" --json
cyberos engagement create <workspace-id> "Authorized API Lab" --kind learning --json
cyberos scope create <engagement-id> "Approved API Scope" --json
cyberos target add <scope-id> --rule include --kind fqdn --value api.example.com --json
cyberos target add <scope-id> --rule exclude --kind fqdn --value admin.example.com --json
cyberos scope authorize <scope-id> --authorization-reference approval-123 --json
cyberos scope evaluate <scope-id> --kind fqdn --value api.example.com --json

# يجب أن يسبق argv delimiter الأمر المراد تشغيله، خصوصًا إذا احتوى على flags مثل -c.
cyberos task run <scope-id> <target-id> \
  --kind fqdn --value api.example.com --json -- \
  echo "authorized local task"
cyberos task list --scope-id <scope-id> --json
cyberos task show <task-id> --json
```

## سياسة الأمان والنطاق

CyberOS مصمم وفق **Fail-Closed Security**. لا يجوز تشغيل أي Task إلا بعد وجود `ExecutionAuthorization` صادر من Scope authorized وغير منتهٍ، ويجب أن يطابق `scope_id` و`target_id` المطلوبين. قواعد `exclude` لها أولوية على `include`، والهدف غير المطابق مرفوض افتراضيًا. الاستخدام يجب أن يكون على أهداف مملوكة أو مصرح بها صراحة؛ لا يهدف المشروع إلى تجاوز التفويض أو تنفيذ نشاط ضار.

راجع [SECURITY.md](SECURITY.md) للإفصاح المسؤول، و[cyberos-core/README.md](cyberos-core/README.md) لتفاصيل حزمة Python، و[التدقيق النهائي](cyberos-core/docs/development/module-0-final-audit.md) لنتائج Module 0.

## التطوير والاختبارات

```bash
cd cyberos-core
source .venv/bin/activate
pytest -q
ruff check .
ruff format --check .
mypy --strict src
python -m build
```

بوابة الجودة الموحدة موجودة في `cyberos-core/scripts/check.sh`، ويعاد تشغيلها تلقائيًا في GitHub Actions عند كل `push` و`pull_request`.

## الترخيص

هذا المشروع مرخص بموجب [MIT License](LICENSE). يبقى الاستخدام الأمني خاضعًا للتفويض والقوانين والسياسات المعمول بها.
