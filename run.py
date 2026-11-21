"""TradingAgents Ultimate · اجراکنندهٔ GitHub Actions (بدون مرورگر، بدون Colab).
- موتور تحلیل در engine.py است (ساخته‌شده از نوت‌بوک v23).
- خروجی تحلیل فقط به‌صورت اعلان ntfy به گوشی می‌رود؛ لاگ عمومی Actions فقط وضعیت کوتاه نشان می‌دهد.
"""
import os, sys, io, re, json, time, types, html, tempfile, traceback, threading

_REAL = sys.__stdout__
HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(HERE, "engine.py")
DATA = os.environ.get("TA_DATA") or os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)
os.environ.setdefault("TA_REPO_DIR", os.path.join(HERE, "TradingAgents"))
LOGP = os.path.join(tempfile.gettempdir(), "ta_last_run.log")
RUN_STARTED = time.time()


class _Tee:
    """همهٔ خروجی موتور (که ممکن است نتیجهٔ تحلیل باشد) فقط در فایل موقت می‌رود، نه در لاگ عمومی."""
    encoding = "utf-8"
    def __init__(self): self.f = open(LOGP, "w", encoding="utf-8", errors="ignore")
    def write(self, s):
        try: self.f.write(s)
        except Exception: pass
        return len(s)
    def flush(self):
        try: self.f.flush()
        except Exception: pass
    def isatty(self): return False


sys.stdout = sys.stderr = _Tee()


def say(m):
    _REAL.write(str(m) + "\n"); _REAL.flush()


def _ntfy(title, message, priority=3, tags=None):
    """ارسال اعلان مستقل شروع/پایان؛ NTFY_TOPIC باید فقط نام topic باشد."""
    topic = os.environ.get("NTFY_TOPIC", "").strip().replace("https://ntfy.sh/", "").strip("/")
    if not topic:
        say("⚠ NTFY_TOPIC تنظیم نشده؛ اعلان ارسال نشد.")
        return False
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", topic):
        say("⚠ مقدار NTFY_TOPIC نامعتبر است؛ فقط نام topic را بدون URL وارد کنید.")
        return False
    try:
        import requests
        # هدر HTTP فقط ASCII؛ عنوان فارسی/ایموجی داخل بدنه می‌رود تا UnicodeEncodeError رخ ندهد.
        body = f"{title}\n{message}" if title else str(message)
        r = requests.post(
            f"https://ntfy.sh/{topic}",
            data=body.encode("utf-8"),
            headers={"Title": "Infinity", "Priority": str(priority), "Tags": ",".join(tags or [])},
            timeout=15,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        say(f"⚠ ارسال اعلان ntfy ناموفق بود: {type(e).__name__}")
        return False


def _journal_count():
    """تعداد رکوردهای ژورنال سیگنال؛ فقط برای گزارش، نه تصمیم معاملاتی."""
    path = os.path.join(DATA, "scalp_journal_signals.jsonl")
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return sum(1 for line in f if line.strip())
    except Exception:
        return 0


def _scrub(t):
    for k in ("GOOGLE_API_KEY", "GOOGLE_API_KEY_2", "GOOGLE_API_KEY_3", "NTFY_TOPIC", "CTRADER_CLIENT_SECRET", "CTRADER_ACCESS_TOKEN"):
        v = os.environ.get(k, "")
        if v: t = str(t).replace(v, "***")
    return str(t)


# ---------- جایگزین IPython: کارت‌های HTML به متن ساده در فایل موقت تبدیل می‌شوند ----------
def _txt(h):
    h = re.sub(r"<style.*?</style>", "", h, flags=re.S | re.I)
    h = re.sub(r"<script.*?</script>", "", h, flags=re.S | re.I)
    h = re.sub(r"<br\s*/?>|</(div|p|tr|summary|li|details|table)>", "\n", h, flags=re.I)
    h = re.sub(r"</t[dh]>", " | ", h, flags=re.I)
    h = html.unescape(re.sub(r"<[^>]+>", "", h))
    return re.sub(r"\n\s*\n+", "\n", h).strip()


class HTML:
    def __init__(self, data=""): self.data = data


class Pretty(HTML):
    pass


def display(*objs, **kw):
    if kw.get("display_id"): return None          # کارت‌های زندهٔ پیشرفت (هر چند ثانیه) در لاگ نمی‌آیند
    for o in objs:
        t = _txt(o.data if hasattr(o, "data") else str(o))
        if t: sys.stdout.write(t + "\n")


def update_display(*a, **k): return None
def clear_output(*a, **k): return None


class StopExecution(Exception):
    pass


class _HeadlessStop(Exception):
    """خروج عادی: ستاپ فعالی نیست یا همین سیگنال تازه فرستاده شده."""


_m = {n: types.ModuleType(n) for n in ("IPython", "IPython.display", "IPython.core", "IPython.core.error")}
for _n in ("display", "HTML", "Pretty", "clear_output", "update_display"): setattr(_m["IPython.display"], _n, globals()[_n])
_m["IPython.core.error"].StopExecution = StopExecution
_m["IPython"].display = _m["IPython.display"]; _m["IPython"].core = _m["IPython.core"]; _m["IPython.core"].error = _m["IPython.core.error"]
sys.modules.update(_m)


def _fail_notify(title, body):
    """اعلان خطا؛ حداکثر هر ۶ ساعت یک‌بار تا هر ۳۰ دقیقه گوشی را پر نکند."""
    tp = os.environ.get("NTFY_TOPIC", "").strip()
    if not tp: return
    stamp = os.path.join(DATA, "fail_stamp")
    try:
        if time.time() - float(open(stamp).read()) < 6 * 3600: return
    except Exception: pass
    try:
        import requests
        requests.post("https://ntfy.sh/", json={"topic": tp, "title": title[:100], "message": _scrub(body)[:900], "priority": 4, "tags": ["warning"]}, timeout=15)
        open(stamp, "w").write(str(time.time()))
    except Exception: pass


G = {"__name__": "ta_engine", "__file__": ENGINE, "_HEADLESS": True, "_DATA": DATA, "_HeadlessStop": _HeadlessStop,
     "_FALLBACK": os.environ.get("TA_FALLBACK", "0") == "1", "_COOLDOWN_H": float(os.environ.get("TA_COOLDOWN_H", "3") or 3),
     "_SEARCH_MIN": float(os.environ.get("TA_SEARCH_MIN", "55") or 55),          # حداکثر دقیقهٔ جست‌وجوی مداوم
     "_RESCAN_SEC": float(os.environ.get("TA_RESCAN_SEC", "240") or 240),        # فاصلهٔ اسکن‌های پشت‌سرهم
     "_FINAL_FALLBACK": os.environ.get("TA_FINAL_FALLBACK", "0") == "1",         # پایان مهلت: بهترین گزینه با پرچم ریسک. پیش‌فرض خاموش (برای معاملهٔ خودکار: بی‌سیگنال بهتر از سیگنال ضعیف)
     "_MIN_LV": int(os.environ.get("TA_MIN_LV", "3") or 3),                      # حداقل پلهٔ اطمینان: ۴ = ۱:۳ کامل | ۳ = فضای ≥۸۵٪ ۱:۳ (پایین‌تر از ۳ هرگز نمی‌پذیرد)
     "_REQUIRE_GO": False,                 # شرط GO مدیرعامل حذف شد؛ تصمیم نهایی همچنان تابع فیلترهای موتور است
     "_WR_W": float(os.environ.get("TA_WR_W", "1.0") or 1.0)}                    # وزن اضافهٔ حد پایین وین‌ریت در رتبه‌بندی

os.environ.setdefault("TA_AGENTS", "0")  # پیش‌فرض: تیم کامل ایجنت‌ها، نه فقط تحلیل تکنیکال
rc, status = 0, "ok"
t0 = time.time()
_before_signals = _journal_count()
_ntfy("Infinity", f"🟢 شروع اسکن Infinity\nدارایی: {os.environ.get('TA_ASSET', 'ALL')}\nزمان UTC: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(t0))}", 3, ["rocket"])

# هشدار آماده‌باش: پنج دقیقه مانده به پایان مهلت جست‌وجوی موتور، مگر اینکه سیگنال زودتر ارسال شده باشد.
_prewarn_stop = threading.Event()
_search_minutes = max(1.0, float(os.environ.get("TA_SEARCH_MIN", "55") or 55))
def _pre_signal_warning():
    # اگر مهلت خیلی کوتاه باشد، دست‌کم ۶۰ ثانیه برای شروع موتور فرصت می‌دهیم.
    wait_seconds = max(60.0, _search_minutes * 60.0 - 300.0)
    deadline = time.monotonic() + wait_seconds
    while not _prewarn_stop.is_set():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        _prewarn_stop.wait(min(remaining, 2.0))
    if _prewarn_stop.is_set():
        return
    run_state = G.get("_RUN", {})
    if isinstance(run_state, dict) and run_state.get("sent"):
        return  # سیگنال نهایی زودتر رسیده؛ هشدار آماده‌باش دیگر لازم نیست.
    _ntfy("Infinity", "⏳ احتمالاً تا ۵ دقیقهٔ دیگر تحلیل به پایان می‌رسد و نتیجه/سیگنال آماده می‌شود؛ آماده باشید! 🚀", 4, ["hourglass", "bell"])

_prewarn_thread = threading.Thread(target=_pre_signal_warning, name="ntfy-pre-signal", daemon=True)
if not os.environ.get("NTFY_TOPIC", "").strip(): say("⚠ NTFY_TOPIC خالی است؛ هیچ اعلانی نمی‌آید.")
if not any(os.environ.get(k, "").strip() for k in ("GOOGLE_API_KEY", "GOOGLE_API_KEY_2", "GOOGLE_API_KEY_3")): say("⚠ هر سه کلید GOOGLE_API_KEY خالی‌اند؛ حداقل یکی را در Secrets و workflow بگذارید."); status, rc = "error: no key", 1
else:
    try:
        _prewarn_thread.start()
        exec(compile(open(ENGINE, encoding="utf-8").read(), ENGINE, "exec"), G)
    except _HeadlessStop as e:
        status = f"skip ({e})"
    except BaseException as e:
        status, rc = f"error: {type(e).__name__}", 1
        tail = _scrub("".join(traceback.format_exception_only(type(e), e)))[:400]
        say("خطا: " + tail)
        try: sys.stdout.flush(); log_tail = open(LOGP, encoding="utf-8", errors="ignore").read()[-700:]
        except Exception: log_tail = ""
        _fail_notify("Infinity error", tail + "\n---\n" + log_tail)
    finally:
        _prewarn_stop.set()
duration = (time.time() - t0) / 60
_after_signals = _journal_count()
_new_signals = max(0, _after_signals - _before_signals)
summary = (f"وضعیت: {status}\nمدت اجرا: {duration:.1f} دقیقه\n"
           f"دارایی درخواستی: {os.environ.get('TA_ASSET', 'ALL')}\n"
           f"رکورد سیگنال جدید در ژورنال: {_new_signals}\n"
           f"زمان پایان UTC: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}")
# گزارش متنیِ قابل دریافت به‌عنوان Artifact در پایان هر اجرا
try:
    os.makedirs(DATA, exist_ok=True)
    report_path = os.path.join(DATA, "last_run_report.txt")
    with open(report_path, "w", encoding="utf-8") as rf:
        rf.write(summary + "\n\n--- LOG ---\n")
        try:
            sys.stdout.flush()
            rf.write(open(LOGP, encoding="utf-8", errors="ignore").read())
        except Exception:
            pass
except Exception as e:
    say(f"⚠ ذخیره گزارش ناموفق بود: {type(e).__name__}")

say(f"TradingAgents: {status} · {duration:.1f} دقیقه · سیگنال جدید: {_new_signals}")
# پیام پایانِ جداگانه عمداً حذف شده؛ پیام نهایی سیگنال را خود engine.py ارسال می‌کند.
sys.stdout.flush()
os._exit(rc)      # نخ‌های پس‌زمینه بسته شوند؛ Actions منتظر نماند
