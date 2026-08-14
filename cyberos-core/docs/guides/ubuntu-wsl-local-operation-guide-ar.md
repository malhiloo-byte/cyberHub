# دليل تشغيل CyberOS محليًا على Ubuntu WSL

**الغرض:** هذا الدليل يشرح تشغيل مشروع CyberOS من الصفر على Ubuntu داخل WSL، بدءًا من تثبيت المتطلبات ووصولًا إلى إنشاء سياق محلي آمن وتشغيل أوامر الـCLI والتحقق من الجودة.

> **حالة المشروع عند كتابة الدليل:** نواة Python وCLI تعملان محليًا، وتخزن البيانات في SQLite، وتدعم دورة Workspace → Engagement → Scope → Target → Task. أمر `cyberos recon nmap-localhost` موجود لكنه ينفذ Nmap الحقيقي؛ لا تشغّله إلا بعد تفويض صريح ومستقل، وضمن `127.0.0.1` فقط. لا يوجد حاليًا تفويض مفتوح أو تلقائي لأي scan حي.

## 1. ما الذي يعمل حاليًا، وما الذي لا يعمل بعد؟

| المجال | الحالة | ماذا يعني ذلك عمليًا؟ |
|---|---|---|
| CyberOS Core وCLI | جاهز للاستخدام المحلي | تستطيع إنشاء Workspaces وEngagements وScopes وTargets، وإجراء تقييم Scope، وإدارة Tasks وقراءة السجلات. |
| SQLite migrations | جاهزة | تُطبّق تلقائيًا عند استخدام الـCLI؛ المخطط الحالي يتوقف عند migration `0006`. |
| Quality gates | جاهزة | يمكنك تشغيل pytest وRuff وmypy strict وبناء wheel عبر `bash scripts/check.sh`. |
| localhost Nmap adapter | مقيد ومصرح-بالتفويض فقط | يقبل `127.0.0.1` فقط وports `22,80,443` فقط و`-sT` فقط؛ لا تشغله من دون تفويض منفصل. |
| Home network / RFC1918 / CIDR scanning | غير جاهز وممنوع حاليًا | لا تستخدمه لمسح شبكة المنزل أو `192.168.x.x` أو أي نطاق متعدد الأجهزة. |
| Module 2.2 multi-host recon | تصميم فقط | لا يوجد تنفيذ ولا migration ولا live multi-host adapter؛ يجب اعتماد قرارات Section 14 أولًا. |
| React Web UI | Preview محلي منفصل | الواجهة الحالية ليست بعدُ لوحة تحكم مرتبطة مباشرة بقاعدة SQLite أو CLI؛ استخدم CLI كنقطة تشغيل فعلية. |

## 2. المتطلبات الأساسية في WSL

افتح **Ubuntu WSL**، ثم نفّذ الآتي مرة واحدة. المشروع يتطلب Python `3.11+`؛ إصدار Python الأحدث مقبول أيضًا.

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip

python3 --version
git --version
```

للتأكد من إمكانية تشغيل جودة المشروع كاملة، لا تعمل من مسار Windows مثل `/mnt/c/...` إن أمكن. استخدم مجلد Linux المنزلي مثل `~/cyberHub`؛ فهو عادةً أسرع وأكثر استقرارًا للـvenv وSQLite.

## 3. تنزيل المشروع أو مزامنته

### 3.1 تثبيت جديد من الصفر

```bash
cd ~
git clone https://github.com/malhiloo-byte/cyberHub.git
cd ~/cyberHub
git remote -v
git branch --show-current
git log -1 --oneline
```

ينبغي أن يظهر remote باسم `origin` أو `github` يشير إلى مستودعك، وأن تكون على فرع `main`.

### 3.2 إذا كان المشروع موجودًا عندك مسبقًا

```bash
cd ~/cyberHub
git fetch origin
git checkout main
git pull --ff-only origin main
git status --short
git rev-parse HEAD
```

إذا ظهر `git status --short` فارغًا، فنسختك المحلية نظيفة. إذا كانت لديك تعديلات محلية مهمة، لا تستخدم `git reset --hard`. اعرضها أولًا عبر `git diff` أو انسخها إلى branch منفصل.

## 4. إنشاء بيئة Python وتثبيت CyberOS Core

```bash
cd ~/cyberHub/cyberos-core

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

بعد كل Terminal جديدة، فعّل البيئة قبل استخدام CyberOS:

```bash
cd ~/cyberHub/cyberos-core
source .venv/bin/activate
```

تحقق من تثبيت الحزمة:

```bash
cyberos version
cyberos --help
cyberos recon --help
```

إذا ظهر `cyberos: command not found` فغالبًا لم تُفعّل `.venv` أو لم ينجح أمر التثبيت editable.

## 5. إعداد ملف config وقاعدة SQLite محلية

استخدم config صريحًا في مجلدك المنزلي حتى لا تختلط بياناتك بملفات المشروع أو بالـfixtures. الأوامر أدناه تجعل قاعدة البيانات في `~/.cyberos/cyberos.sqlite3`.

```bash
mkdir -p ~/.cyberos/logs
cp ~/cyberHub/cyberos-core/config/cyberos.example.toml ~/.cyberos/cyberos.toml

export CYBEROS_CONFIG="$HOME/.cyberos/cyberos.toml"
printf '%s\n' "$CYBEROS_CONFIG"
```

يمكنك إضافة السطر التالي إلى `~/.bashrc` كي لا تعيد تصديره كل مرة:

```bash
echo 'export CYBEROS_CONFIG="$HOME/.cyberos/cyberos.toml"' >> ~/.bashrc
source ~/.bashrc
```

استخدم خيار `--file "$CYBEROS_CONFIG"` دائمًا في أمثلة هذا الدليل. يمنع ذلك تشغيل الأوامر على config خاطئ أو قاعدة غير مقصودة.

## 6. فحص الصحة والجودة

### 6.1 فحص البيئة وقاعدة البيانات

```bash
cd ~/cyberHub/cyberos-core
source .venv/bin/activate

cyberos doctor --json --file "$CYBEROS_CONFIG"
```

أول أمر CLI يحتاج قاعدة بيانات سيشغل migrations الداخلية forward-only حتى `0006`. لا تعدّل ملفات migrations يدويًا ولا تحذف قاعدة البيانات إذا كانت تحتوي عملك الفعلي.

### 6.2 تشغيل الاختبارات وبوابات الجودة

```bash
cd ~/cyberHub/cyberos-core
source .venv/bin/activate

pytest -q
bash scripts/check.sh
```

الأمر `scripts/check.sh` يجمع regression suite وRuff lint وRuff format check وmypy strict وبناء wheel. إذا فشل، لا تنتقل إلى live execution؛ راجع أول خطأ ظاهر وأصلحه أو حدّث نسختك من GitHub.

## 7. دورة العمل المحلية الآمنة

CyberOS يعتمد **fail-closed**: لا يكفي أن تعرف عنوانًا أو تكتبه؛ يجب أن يكون Target مسجلًا داخل Scope مصرح به. لا يوجد shell strings أو `shell=True` في مسار التنفيذ؛ commands هي argv tuples مقيدة.

### 7.1 إنشاء Workspace

```bash
cyberos workspace create "WSL Learning Lab" \
  --description "Local CyberOS learning workspace" \
  --json --file "$CYBEROS_CONFIG"
```

انسخ قيمة `data.id` من JSON إلى متغير. في بقية الدليل استبدل القيم بين الأقواس بالقيم التي أعادها CyberOS.

```bash
export WORKSPACE_ID="ضع-UUID-الخاص-بك-هنا"
```

### 7.2 إنشاء Engagement

```bash
cyberos engagement create "$WORKSPACE_ID" "WSL Localhost Lab" \
  --kind learning \
  --authorization-reference "LOCAL-WSL-LEARNING-$(date +%F)" \
  --json --file "$CYBEROS_CONFIG"

export ENGAGEMENT_ID="ضع-UUID-الخاص-بالـEngagement"
```

### 7.3 إنشاء Scope وTarget localhost فقط

```bash
cyberos scope create "$ENGAGEMENT_ID" "Loopback Only" \
  --description "Explicit local WSL loopback laboratory only" \
  --json --file "$CYBEROS_CONFIG"

export SCOPE_ID="ضع-UUID-الخاص-بالـScope"

cyberos target add "$SCOPE_ID" \
  --rule include --kind ipv4 --value 127.0.0.1 \
  --json --file "$CYBEROS_CONFIG"

export TARGET_ID="ضع-UUID-الخاص-بالـTarget"
```

### 7.4 تفويض الـScope وتقييمه بدون تنفيذ

بعد إضافة Target، لا يمكن توسيع Scope مصرح به بصمت. إذا احتجت Target مختلفًا، أنشئ Scope جديدًا أو انتظر workflow مراجعة/اعتماد مناسب؛ لا تعدّل Scope مصرح به لتجاوز الحماية.

```bash
cyberos scope authorize "$SCOPE_ID" \
  --authorization-reference "LOCALHOST-ONLY-APPROVAL-$(date +%F)" \
  --json --file "$CYBEROS_CONFIG"

cyberos scope evaluate "$SCOPE_ID" \
  --kind ipv4 --value 127.0.0.1 \
  --json --file "$CYBEROS_CONFIG"
```

النتيجة الصحيحة يجب أن تتضمن `decision: included`، و`scope_status: authorized`، و`matched_target_id` المطابق لـ`$TARGET_ID`.

## 8. الأوامر الآمنة المتاحة الآن

الجدول التالي يفرق بين أوامر القراءة/الإدارة وبين أوامر قد تنفذ فعلًا.

| الأمر | الأثر | مناسب للتشغيل الآن؟ |
|---|---|---|
| `cyberos version` و`cyberos doctor` | قراءة وتشخيص | نعم |
| `workspace create` و`engagement create` و`scope create` و`target add` | يكتب فقط في SQLite المحلية | نعم، إذا كانت البيانات تخصك |
| `scope evaluate` | تقييم read-only بدون network | نعم |
| `task list` و`task show` | قراءة Tasks | نعم |
| `task run` | ينفذ argv محليًا بعد authorization | فقط مع أمر محلي آمن ومصرح به تفهمه |
| `recon nmap-localhost` | يشغّل Nmap الحقيقي | **ليس الآن تلقائيًا؛ يحتاج تفويضًا صريحًا منفصلًا لكل تجربة** |

أمثلة قراءة مفيدة:

```bash
cyberos task list --scope-id "$SCOPE_ID" --json --file "$CYBEROS_CONFIG"

# بعد وجود Task ID:
cyberos task show "ضع-TASK-ID" --json --file "$CYBEROS_CONFIG"
```

## 9. Nmap localhost: الحالة الحالية وطريقة الاستخدام عند التفويض فقط

### 9.1 الحدود الصارمة

الأمر الرسمي الحالي لا يقبل إلا:

| العنصر | القيمة المسموحة |
|---|---|
| Target | `127.0.0.1` فقط |
| Scan mode | TCP Connect `-sT` فقط |
| Ports | مجموعة فرعية من `22,80,443` فقط |
| Binary path | مسار صريح، عادةً `/usr/bin/nmap` |
| Binary identity | SHA-256 صريح يطابق الملف |
| Output | XML bounded/redacted داخل الـpipeline |

لا تستخدم `-sS` داخل WSL لهذه التجربة؛ غالبًا يحتاج raw socket privileges. لا تمرر flags أخرى، ولا تستخدم `nmap` مباشرة لتجاوز CyberOS، ولا تغير target إلى gateway أو شبكة المنزل.

### 9.2 التحقق دون تشغيل scan

يمكنك تثبيت Nmap وحساب هويته دون تنفيذ scan:

```bash
sudo apt update
sudo apt install -y nmap

/usr/bin/nmap --version
sha256sum /usr/bin/nmap
```

### 9.3 الأمر الذي يستخدم فقط بعد تفويض صريح جديد

لا تنفذ الأمر التالي الآن إلا إذا كان لديك تفويض صريح منفصل لتجربة واحدة، وكان `$SCOPE_ID` و`$TARGET_ID` يشيران إلى سياق `127.0.0.1` مصرح به حديثًا:

```bash
export NMAP_SHA256="ضع-هنا-قيمة-sha256sum-الكاملة"

cyberos recon nmap-localhost "$SCOPE_ID" "$TARGET_ID" \
  --nmap-sha256 "$NMAP_SHA256" \
  --nmap-version "7.94SVN" \
  --ports 22,80,443 \
  --nmap-path /usr/bin/nmap \
  --json --file "$CYBEROS_CONFIG"
```

بعد أي trial، لا تعيد التشغيل تلقائيًا عند الفشل. اقرأ Task أولًا:

```bash
cyberos task list --scope-id "$SCOPE_ID" --json --file "$CYBEROS_CONFIG"
```

> **قاعدة تشغيل:** فشل parser أو Scope أو binary identity هو نتيجة أمنية يجب تحليلها، وليس إشارة لتجريب flags أو targets أخرى.

## 10. تشغيل واجهة React محليًا (اختياري)

واجهة المشروع موجودة في جذر المستودع وتعمل كـpreview مستقل. لا تعتبرها حاليًا واجهة تشغيل live لـSQLite أو Nmap؛ مصدر الحقيقة التنفيذي هو `cyberos-core` وCLI.

```bash
cd ~/cyberHub
corepack enable
pnpm install
pnpm dev
```

بعدها افتح العنوان الذي يظهر في Terminal، وغالبًا يكون `http://localhost:3000`. أوقفها عبر `Ctrl+C`.

## 11. تحديث المشروع مستقبلًا

نفّذ التحديثات في Terminal لا تشغّل فيه `pnpm dev`:

```bash
cd ~/cyberHub
git fetch origin
git checkout main
git pull --ff-only origin main

cd cyberos-core
source .venv/bin/activate
python -m pip install -e '.[dev]'
bash scripts/check.sh
```

بعد أي تحديث يتضمن تغييرات في Python dependencies، أعد أمر `pip install -e '.[dev]'`. بعد أي تحديث للواجهة، شغّل `pnpm install` من جذر المستودع إن تغيّر `pnpm-lock.yaml`.

## 12. Troubleshooting

| المشكلة | التشخيص أو الحل الآمن |
|---|---|
| `cyberos: command not found` | نفّذ `source .venv/bin/activate` ثم `python -m pip install -e '.[dev]'`. |
| `CONFIG_NOT_FOUND` | تأكد من `echo "$CYBEROS_CONFIG"` وأن الملف موجود: `ls -l "$CYBEROS_CONFIG"`. |
| `SCOPE_NOT_AUTHORIZED` | راجع Scope؛ لا تنفذ Task أو Nmap قبل `scope authorize`. |
| `TARGET_OUT_OF_SCOPE` أو `TARGET_EXCLUDED` | لا تغير command أو target للالتفاف. أضف Target الصحيح داخل Scope draft جديد واتبع approval workflow. |
| `NMAP_BINARY_IDENTITY_MISMATCH` | أعد `sha256sum /usr/bin/nmap` واستخدم القيمة الكاملة؛ لا تعطّل التحقق. |
| `NMAP_XML_INVALID` | لا تعمل retry. افحص `task list`، احتفظ بالـerror code redacted، ثم أصلح parser offline واختبره أولًا. |
| `permission denied` لـNmap | استخدم profile الرسمي `-sT` فقط، ولا تستخدم `sudo` لإجبار scan. |
| SQLite locked | أغلق terminals أخرى تعمل على نفس القاعدة، وتأكد أن config يشير إلى `~/.cyberos/cyberos.sqlite3`. لا تحذف DB كحل أول. |
| فشل `bash scripts/check.sh` | نفّذ `git status --short` ثم حدّث main أو راجع أول failure. لا تشغّل live adapter مع test suite فاشل. |

## 13. Checklist يومي مختصر

```bash
cd ~/cyberHub/cyberos-core
source .venv/bin/activate
export CYBEROS_CONFIG="$HOME/.cyberos/cyberos.toml"

git -C ~/cyberHub status --short
cyberos version
cyberos doctor --json --file "$CYBEROS_CONFIG"
cyberos scope evaluate "$SCOPE_ID" --kind ipv4 --value 127.0.0.1 --json --file "$CYBEROS_CONFIG"
```

إذا كانت البيئة سليمة وScope returned `included`، يمكنك متابعة إجراءات **offline** والتعليم وإدارة البيانات. أما أي live Nmap invocation فيبقى قرارًا منفصلًا، single-use، وموثقًا.

## 14. الخطوة التالية الصحيحة

قبل أي P3 جديد، راجع أن آخر commit موجود محليًا وأن `bash scripts/check.sh` نجح. بعد ذلك يلزم تفويض مستقل واحد لتجربة localhost واحدة، ثم يجب فحص Task وEvidence بدل التكرار. في الوقت نفسه، وثيقة Module 2.2 جاهزة للمراجعة، لكنها لا تخول تنفيذ multi-host recon حتى تعتمد قراراتها صراحة.
