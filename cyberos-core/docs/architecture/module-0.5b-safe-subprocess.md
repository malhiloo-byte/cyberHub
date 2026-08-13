# Module 0.5.b — Safe Subprocess Execution Engine

## Architectural decision

يعتمد هذا الموديول `asyncio.create_subprocess_exec` مع `argv` tuple فقط. لا يسمح العقد بتمرير shell command string، ولا يستخدم `shell=True` أو parsing يدويًا لرموز Shell. يبقى التنفيذ في طبقة `cyberos.execution` ولا يُدخل subprocess إلى Domain أو Persistence أو CLI.

## Responsibilities and non-responsibilities

يبدأ `SafeSubprocessRunner` process محليًا، يمرر `ExecutionSpec.command` كما هي، يبني environment جديدًا من allowlist، يلتقط stdout/stderr بحدود ذاكرة، يطبق timeout، ثم يعيد `ExecutionResult` immutable قابلًا للتدقيق. لا يقوم runner بإنشاء Task أو حفظه أو تنفيذ authorization؛ إنشاء Task والتحقق من `ExecutionAuthorization` يظلان في Domain/Application layers. كما لا يقوم بأي DNS أو HTTP أو network-tool invocation.

> عند timeout يعيد runner نتيجة تحمل `timeout_exceeded=True` و`failure_reason=TIMEOUT_EXCEEDED`. تقوم طبقة التطبيق اللاحقة بتحويل هذه النتيجة إلى transition من Task إلى `FAILED` ضمن transaction المناسبة؛ لا توجد Persistence في هذه الشريحة.

## Public contract

```python
async def run(
    self,
    spec: ExecutionSpec,
    *,
    environment: Mapping[str, str] | None = None,
    cwd: str | Path | None = None,
) -> ExecutionResult
```

`environment` ليس environment موروثًا؛ هو مصدر قيم اختياري تُرشّح مفاتيحه عبر `spec.env_policy.allowed_keys`. إذا لم يُمرر، تكون البيئة الابنة فارغة. `cwd` يُمرر إلى process launcher بعد التحقق من النوع، ولا يغيّر سياسة command أو authorization.

`ExecutionResult` يحمل bytes خامًا لتجنب decoding loss، مع `exit_code`, `stdout`, `stderr`, `truncated`, `duration_seconds`, `timeout_exceeded`, و`failure_reason`. يمثل `truncated` قطع أي stream، ويطبق `max_output_bytes` لكل stream بصورة مستقلة.

## Output and memory policy

تقرأ collector tasks stdout وstderr بالتوازي. يحتفظ كل collector بأقصى `max_output_bytes` فقط، ويواصل drain للـpipe بعد بلوغ السقف حتى لا يعلّق child بسبب امتلاء pipe. لذلك لا تتجاوز الذاكرة المحتفظ بها الحدين، وتبقى نتيجة partial قابلة للاستخدام. لا يتم قتل process لمجرد بلوغ output cap؛ timeout هو حد التشغيل الزمني المستقل.

## Timeout and termination policy

ينتظر runner process حتى `timeout_seconds`. عند التجاوز يرسل `SIGTERM` عبر `Process.terminate()`، وينتظر grace period قصيرة، ثم يرسل `SIGKILL` عبر `Process.kill()` إذا بقي process حيًا. بعد ذلك يستنزف pipe readers ويعيد exit code الفعلي وسبب `TIMEOUT_EXCEEDED`. لا يستخدم `preexec_fn` أو shell process. إنشاء process group ليس جزءًا من هذا slice؛ لذلك يبقى process-tree cancellation extension موثقًا للمستقبل قبل تشغيل أدوات قد تطلق descendants.

## Error policy

فشل spawn يرفع `CyberOSError(EXECUTION_START_FAILED)` دون تسريب `OSError` أو command internals إلى boundary. Non-zero exit code ليس exception؛ يعود في `ExecutionResult` حتى يستطيع caller تحليل الأداة. Timeout لا يرفع exception لأنه نتيجة تنفيذ قابلة للتدقيق، بل يثبت `failure_reason`.

## Option A — TaskExecutionEngine

اعتمد المشروع Option A: `TaskExecutionEngine` هو orchestrator رفيع يستقبل `Task` و`ExecutionSpec` و`ExecutionAuthorizationContract`. يتحقق من تطابق الـspec والـScope والـTarget وصلاحية التفويض، ثم يعيد Task immutable إلى `RUNNING` قبل استدعاء runner. بعد النتيجة يعيد Taskًا إلى `COMPLETED` فقط عندما يكون `exit_code == 0` بلا timeout؛ وأي timeout أو non-zero exit code يعيد Taskًا إلى `FAILED`. لا يكتب engine إلى قاعدة البيانات ولا يغيّر Task in-place، وتظل مهمة application layer لاحقًا حفظ النسخة الجديدة داخل transaction.

## Security review

العقد يمنع shell injection structurally عبر tuple argv. البيئة لا ترث `os.environ`، ولا يسمح runner بمفاتيح خارج allowlist، ولا يكتب output إلى ملفات مؤقتة. الاختبارات تستخدم `echo` و`sleep` و`sys.executable -c` فقط، ولا تتصل بالشبكة أو تستدعي أدوات فحص حقيقية.
