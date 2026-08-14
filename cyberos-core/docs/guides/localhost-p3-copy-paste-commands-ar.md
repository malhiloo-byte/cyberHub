# أوامر Ubuntu WSL: CyberOS وفحص localhost واحد

> **استخدم هذا الدليل على جهازك فقط.** أمر Nmap في القسم 8 ينفذ فحصًا حيًا واحدًا فعليًا على `127.0.0.1`. لا تنفذه على شبكة المنزل أو gateway أو أي IP آخر، ولا تعيد تنفيذه تلقائيًا إذا ظهر خطأ. لا يوجد في هذه البطاقة أي أمر لمسح subnet أو CIDR.

## 1. تنزيل أو تحديث المشروع

انسخ هذا block كاملًا إلى Ubuntu WSL:

```bash
set -euo pipefail

sudo apt update
sudo apt install -y git python3 python3-venv python3-pip nmap sqlite3

cd ~
if [ -d "$HOME/cyberHub/.git" ]; then
  cd "$HOME/cyberHub"
  git fetch origin
  git checkout main
  git pull --ff-only origin main
else
  git clone https://github.com/malhiloo-byte/cyberHub.git "$HOME/cyberHub"
  cd "$HOME/cyberHub"
fi

git rev-parse HEAD
git status --short
```

## 2. إنشاء Python virtual environment وتثبيت النواة

```bash
cd "$HOME/cyberHub/cyberos-core"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'

cyberos version
```

## 3. إنشاء config وقاعدة SQLite محلية

```bash
mkdir -p "$HOME/.cyberos/logs"
export CYBEROS_CONFIG="$HOME/.cyberos/cyberos.toml"

if [ ! -f "$CYBEROS_CONFIG" ]; then
  cp config/cyberos.example.toml "$CYBEROS_CONFIG"
fi

printf 'Config: %s\n' "$CYBEROS_CONFIG"
cyberos doctor --json --file "$CYBEROS_CONFIG"
```

## 4. تحقق من جودة النسخة قبل أي تشغيل حي

```bash
cd "$HOME/cyberHub/cyberos-core"
source .venv/bin/activate
bash scripts/check.sh
```

لا تنتقل إلى القسم 8 إذا فشل أي اختبار.

## 5. تحقق من Nmap بدون scan

```bash
/usr/bin/nmap --version
export NMAP_SHA256="$(sha256sum /usr/bin/nmap | awk '{print $1}')"
export NMAP_VERSION="$(/usr/bin/nmap --version | sed -n '1s/^Nmap version \([^ ]*\).*/\1/p')"

printf 'NMAP_SHA256=%s\n' "$NMAP_SHA256"
printf 'NMAP_VERSION=%s\n' "$NMAP_VERSION"
```

يجب أن يعرض `NMAP_VERSION` قيمة مثل `7.94SVN`. هذا القسم لا ينفذ scan.

## 6. إنشاء سياق محلي جديد للـlocalhost

نفّذ الأوامر واحدًا واحدًا، وبعد كل أمر انسخ `data.id` من JSON إلى المتغير المبين تحته. إذا كررت التجربة، غيّر أسماء Workspace وEngagement وScope؛ الأسماء فريدة داخل سياقها وCyberOS يرفض الاسم المكرر بدل إنشاء سجل ملتبس.

```bash
cyberos workspace create "WSL Localhost Lab" \
  --description "One explicitly authorized localhost-only CyberOS lab" \
  --json --file "$CYBEROS_CONFIG"
```

```bash
export WORKSPACE_ID="ضع-هنا-data.id-للـWorkspace"

cyberos engagement create "$WORKSPACE_ID" "Localhost TCP Connect Lab" \
  --kind learning \
  --authorization-reference "LOCALHOST-ONLY-$(date +%F)" \
  --json --file "$CYBEROS_CONFIG"
```

```bash
export ENGAGEMENT_ID="ضع-هنا-data.id-للـEngagement"

cyberos scope create "$ENGAGEMENT_ID" "127.0.0.1 Only" \
  --description "Explicit WSL loopback only; no LAN, CIDR, gateway, or external target" \
  --json --file "$CYBEROS_CONFIG"
```

```bash
export SCOPE_ID="ضع-هنا-data.id-للـScope"

cyberos target add "$SCOPE_ID" \
  --rule include \
  --kind ipv4 \
  --value 127.0.0.1 \
  --json --file "$CYBEROS_CONFIG"
```

```bash
export TARGET_ID="ضع-هنا-data.id-للـTarget"

cyberos scope authorize "$SCOPE_ID" \
  --authorization-reference "LOCALHOST-P3-ONE-RUN-$(date +%F)" \
  --json --file "$CYBEROS_CONFIG"

cyberos scope evaluate "$SCOPE_ID" \
  --kind ipv4 --value 127.0.0.1 \
  --json --file "$CYBEROS_CONFIG"
```

**توقف هنا إذا لم تكن نتيجة التقييم `included` أو إذا كان `matched_target_id` لا يساوي `$TARGET_ID`.**

إذا انتهى السكربت أو أمر من الأوامر بخطأ، فهذا لا يطفئ Ubuntu أو WSL؛ إنما تنتهي عملية الأمر لحماية النطاق. راجع آخر السطور أو ملف log الذي يعرضه السكربت، ولا تعالج الخطأ بإعادة الفحص الحي.

## 7. مراجعة القيم قبل الفحص الحي

```bash
printf 'Scope:  %s\nTarget: %s\nNmap:   %s (%s)\n' \
  "$SCOPE_ID" "$TARGET_ID" "$NMAP_VERSION" "$NMAP_SHA256"

cyberos scope evaluate "$SCOPE_ID" \
  --kind ipv4 --value 127.0.0.1 \
  --json --file "$CYBEROS_CONFIG"
```

ينبغي أن تكون القيم الثلاثة التالية صحيحة قبل المتابعة: Target هو `127.0.0.1`، وقرار Scope هو `included`، وSHA-256 هو ناتج `/usr/bin/nmap` نفسه.

## 8. الفحص الحي الواحد على localhost فقط

> **نفّذ هذا block مرة واحدة فقط بعد التفويض الصريح لتجربة واحدة.** لا تغيّر target أو ports أو flags، ولا تكرره تلقائيًا عند الخطأ.

```bash
cyberos recon nmap-localhost "$SCOPE_ID" "$TARGET_ID" \
  --nmap-sha256 "$NMAP_SHA256" \
  --nmap-version "$NMAP_VERSION" \
  --ports 22,80,443 \
  --nmap-path /usr/bin/nmap \
  --json --file "$CYBEROS_CONFIG"
```

هذا هو المسار الرسمي المقيد. داخليًا يستخدم TCP Connect (`-sT`) إلى `127.0.0.1` فقط، ويقيد المنافذ إلى `22,80,443`، ويتحقق من هوية binary ويحول XML bounded/redacted إلى نتائج مهيكلة عندما ينجح.

## 9. التحقق بعد الفحص — لا retry

نفّذ أوامر القراءة التالية **بعد** النتيجة، سواء كانت ناجحة أو فاشلة:

```bash
cyberos task list --scope-id "$SCOPE_ID" --json --file "$CYBEROS_CONFIG"

sqlite3 "$HOME/.cyberos/cyberos.sqlite3" \
  "PRAGMA quick_check; PRAGMA foreign_key_check;"
```

| النتيجة | التصرف الصحيح |
|---|---|
| `status: completed` | احتفظ بـTask ID والـreceipt، ثم راجع Assets/Evidence في المسار التالي من CyberOS. |
| `status: failed` أو `NMAP_XML_INVALID` | **لا تعيد الفحص.** انسخ JSON والـTask ID، ثم راجع سبب failure في CyberOS قبل طلب تفويض جديد. |
| `SCOPE_NOT_AUTHORIZED` أو `TARGET_OUT_OF_SCOPE` | لا تحاول تغيير target أو تجاوز Scope؛ أصلح السياق فقط. |
| `NMAP_BINARY_IDENTITY_MISMATCH` | أعد حساب `sha256sum /usr/bin/nmap` ولا تعطّل التحقق. |

## 10. تشغيل الواجهة البصرية اختياريًا

الواجهة الحالية Preview محلي منفصل؛ مصدر الحقيقة التنفيذي يبقى CLI وSQLite.

```bash
cd "$HOME/cyberHub"
corepack enable
pnpm install
pnpm dev
```

افتح العنوان الذي يظهر، وغالبًا `http://localhost:3000`. أوقفها بـ`Ctrl+C`.
