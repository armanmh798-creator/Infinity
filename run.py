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
# پیش‌فرض‌ها: طلا، سخت‌گیری روی دقت (بدون سیگنال اجباری/ضعیف)، کولداون یک‌ساعته برای سیگنال ساعتی
if not os.environ.get("TA_ASSET", "").strip(): os.environ["TA_ASSET"] = "Gold"
os.environ.setdefault("TA_COOLDOWN_H", "1")
os.environ.setdefault("TA_TECH_AFTER", "2")      # بیشتر از ۱ یعنی ستاپ «فقط تکنیکال/کم‌اطمینان» هرگز پذیرفته نمی‌شود
os.environ.setdefault("TA_MIN_PER_HOUR", "0")    # سیگنال ضعیفِ اجباری در انتهای ساعت ممنوع
os.environ.setdefault("TA_REPO_DIR", os.path.join(HERE, "TradingAgents"))
os.environ.setdefault("TA_STRICT", "1")           # v28: گیت سخت کیفیت
os.environ.setdefault("TA_STRICT_HARD", "1")       # v30: فقط ریسک‌های ساختاری واقعی وتو می‌کنند
os.environ.setdefault("TA_LEAN", "0")              # v29: لایه‌های هماهنگ‌کننده/اقتصاددان/شورا در اجراهای مجهز به ایجنت روشن
os.environ.setdefault("TA_REQUIRE_GO", "0")        # v30: مدیرعامل ناظر است؛ فقط NO صریح وتو می‌کند، WAIT/timeout به‌تنهایی قفل نمی‌کند
os.environ.setdefault("TA_ANALYSTS", "market,social,news,fundamentals")
os.environ["TA_LLM_PROVIDER"] = "1xai"             # v38: فقط 1xAI با ONE_XAI_API_KEY؛ Gemini/Google مستقیم، Grok مستقیم و موتور رایگان حذف شده‌اند
for _k in [k for k in os.environ if k.startswith("GOOGLE_API_KEY") or k in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY", "CEREBRAS_API_KEY", "OPENROUTER_API_KEY", "NVIDIA_API_KEY")]: os.environ.pop(_k, None)
for _k in ("TA_CLAUDE_FALLBACK", "TA_GROK_FALLBACK", "TA_FALLBACK"): os.environ[_k] = "0"      # هیچ fallback به موتور دیگری؛ جایگزین‌ها را روتر داخل 1xAI انتخاب می‌کند
os.environ.setdefault("TA_LITE_AGENTS", "1")       # v28: اگر تیم اصلی TradingAgents افتاد، ICT/SMC و مدیرعامل با گزارش موتور اجرا شوند
os.environ.setdefault("TA_ROUTER", "1")           # v37: روتر ۲۵ عاملی؛ هر نقش با مدل ستون حالت فعلی (Normal/VIP/Gold/Eco)، همه با ONE_XAI_API_KEY
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


def _tehran(ts=None):
    """زمان تهران (UTC+3:30، بدون ساعت تابستانی) به‌صورت متن."""
    import datetime as _dt
    ts = time.time() if ts is None else ts
    try:
        from zoneinfo import ZoneInfo
        d = _dt.datetime.fromtimestamp(ts, ZoneInfo("Asia/Tehran"))
    except Exception:
        d = _dt.datetime.fromtimestamp(ts, _dt.timezone(_dt.timedelta(hours=3, minutes=30)))
    return d.strftime("%Y-%m-%d %H:%M:%S")


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



def _no_signal_diagnosis(default_reason="در این بازه ستاپ واجد شرایط پیدا نشد"):
    """خلاصهٔ دلیل بی‌سیگنالی از وضعیت واقعی موتور؛ بدون حدس‌زدن خبر یا نظر مدیرعامل."""
    reasons = []
    try:
        ng_fn = G.get("news_guard") if isinstance(G, dict) else None
        if callable(ng_fn):
            ng = ng_fn() or {}
            near = ng.get("near") or []
            if near:
                x = near[0]
                reasons.append(f"فیلتر خبر: {str(x.get('title') or 'خبر مهم')} ({x.get('impact', 'اثرگذار')})")
            elif ng.get("err"):
                reasons.append("تقویم خبر قابل‌تأیید نبود؛ فیلتر احتیاطی فعال بماند")
    except Exception:
        pass
    try:
        board = G.get("_ALL", {}) if isinstance(G, dict) else {}
        rows = board.get("rows", []) if isinstance(board, dict) else []
        for row in rows[:3]:
            if not isinstance(row, dict):
                continue
            asset = str(row.get("a") or "")
            why = str(row.get("why") or "").strip()
            llm = row.get("llm") or {}
            verdict = str(llm.get("verdict") or "").upper()
            grade = str(llm.get("grade") or "").upper()
            ceo_why = str(llm.get("why") or "").strip()
            if verdict == "NO":
                why = "مدیرعامل: NO" + (f"؛ {ceo_why}" if ceo_why else "")
            elif verdict == "WAIT" and ceo_why and not why:
                why = "مدیرعامل: WAIT؛ " + ceo_why
            elif verdict and grade and not why:
                why = f"مدیرعامل {verdict} · درجه {grade}"
            if not why:
                tier = int(row.get("tier", -1) or 0)
                if tier == 0:
                    why = "ستاپ فعال نبود یا هنوز در حال شکل‌گیری است"
                elif tier < 0:
                    why = "دادهٔ تازه یا بک‌تست معتبر در دسترس نبود"
            if why:
                reasons.append((f"{asset}: " if asset else "") + why)
    except Exception:
        pass
    # لاگ آخرین دور، فقط اگر وضعیت ساختاری دلیل مشخصی نداده باشد.
    if not reasons:
        try:
            tail = open(LOGP, encoding="utf-8", errors="ignore").read()[-5000:]
            patterns = [
                (r"مدیرعامل[^\n]{0,180}", "نظر مدیرعامل"),
                (r"پرچم سخت[^\n]{0,180}", "فیلتر ریسک"),
                (r"خبر[^\n]{0,180}(?:WAIT|NO|ممنوع|نزدیک)[^\n]{0,100}", "فیلتر خبر"),
                (r"بازار بسته[^\n]{0,120}", "بازار بسته"),
                (r"داده[^\n]{0,120}(?:کهنه|تازه|ناموجود)[^\n]{0,80}", "دادهٔ بازار"),
            ]
            for pat, _ in patterns:
                m = re.findall(pat, tail, flags=re.I)
                if m:
                    reasons.append(m[-1].strip()[:190]); break
        except Exception:
            pass
    clean = []
    for item in reasons:
        item = re.sub(r"\s+", " ", str(item)).strip(" ؛،|")
        if item and item not in clean:
            clean.append(item)
    return " | ".join(clean[:2])[:360] if clean else default_reason

def _journal_count():
    """تعداد رکوردهای ژورنال سیگنال؛ فقط برای گزارش، نه تصمیم معاملاتی."""
    path = os.path.join(DATA, "scalp_journal_signals.jsonl")
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return sum(1 for line in f if line.strip())
    except Exception:
        return 0


def _scrub(t):
    for k in ("ONE_XAI_API_KEY", "GROK_API_KEY", "NTFY_TOPIC", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "CTRADER_CLIENT_SECRET", "CTRADER_ACCESS_TOKEN"):
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
     "_REQUIRE_GO": os.environ.get("TA_REQUIRE_GO", "1") != "0",  # v29: رأی مدیرعامل در مسیر مدلی لازم است
     "_WR_W": float(os.environ.get("TA_WR_W", "1.0") or 1.0)}                    # وزن اضافهٔ حد پایین وین‌ریت در رتبه‌بندی


# ---------- خلاصهٔ آموزش‌های ۳ فایل (به ایجنت‌ها داده می‌شود؛ فقط مشاوره، بدون اختیار حذف سیگنال) ----------
_KNOW = """BACKGROUND PRINCIPLES (from the desk's training dossiers; use as judgement guidance, do not quote, do not change the required output format):
1. Win rate alone proves nothing. Expectancy = WR*avgWin - LR*avgLoss, net of spread/slippage/commission; profit factor must be >1. With 1:3 reward:risk break-even win rate is about 25% BEFORE costs; costs push the real threshold higher, and a high win rate with big losers still loses.
2. Match the strategy to the regime. Range/mean-reversion (RSI<30/>70, Bollinger edge, ADX low) works in a range and gets run over in a strong trend. Trend pullbacks (price vs EMA50/200, RSI dips toward 40-50 in an uptrend, mirror in a downtrend) have a medium win rate but larger R. Breakouts have frequent false breaks: prefer a retest or a confirming close, and above-average volume.
3. Support/resistance trades need confirmation (reversal candle, divergence, retest); stop goes where the idea is invalidated, ideally ATR-based, never inside the noise.
4. VWAP: above = buyers in control (buy pullbacks), below = sellers in control; it is a bias tool, weak in thin liquidity and outside the active session.
5. Crypto futures crowding filter: strongly positive funding (about +0.05% per interval or more) with rising open interest means crowded longs and correction risk; very negative funding is the mirror. Treat as a flag that lowers confidence, not as a direction signal. BTC leads ETH and alts.
6. Stand aside or flag risk around high-impact news (FOMC, CPI, NFP) and in thin or rollover hours.
7. Filters must not manufacture edge: a setup with weak raw expectancy is not rescued by stacking indicators. Small samples (under ~30 trades) and unconfirmed out-of-sample results deserve low trust; say so honestly. No result is guaranteed.
"""
G["_KNOW"] = os.environ.get("TA_KNOW", "1") != "0" and _KNOW or ""

os.environ.setdefault("TA_AGENTS", "0")  # پیش‌فرض: موتور سبک بدون ایجنت مدلی (سریع، بدون نیاز به کلید)؛ TA_AGENTS=1 = تیم کامل ایجنت‌ها

def _engine_src():
    """متن موتور را می‌خواند و دو عدد را از env می‌گیرد (engine.py دست‌نخورده می‌ماند):
    TA_AGENT_MIN  = سقف زمان تیم ایجنت‌ها بعد از پیدا شدن ستاپ (دقیقه). تمام نشد = سیگنال بدون ایجنت و با پرچم ریسک، اما فرستاده می‌شود.
    TA_LLM_TOPK   = 0 یعنی ایجنت‌ها وسط جست‌وجو نامزدها را رد/کند نمی‌کنند؛ فقط بعد از انتخاب ستاپ تحلیل و درجه‌بندی می‌کنند (مشاور، نه دروازه‌بان)."""
    src = open(ENGINE, encoding="utf-8").read()
    try: _am = float(os.environ.get("TA_AGENT_MIN", "7") or 7)
    except Exception: _am = 7.0
    try: _tk = int(os.environ.get("TA_LLM_TOPK", "0") or 0)
    except Exception: _tk = 0
    try: _ls = max(0.0, float(os.environ.get("TA_LIVE_SEC", "30") or 30))
    except Exception: _ls = 30.0
    for pat, rep in ((r"^LIVE_SECONDS\s*=\s*\d+(?:\.\d+)?", f"LIVE_SECONDS = {_ls:g}"),      # آپدیت زندهٔ قیمت قبل از ارسال سیگنال (پیش‌فرض ۳۰ ثانیه)
                     (r"^AGENT_TIMEOUT_MIN\s*=\s*\d+(?:\.\d+)?", f"AGENT_TIMEOUT_MIN = {max(2.0, _am):g}"),
                     (r"^ALL_LLM_TOPK\s*=\s*\d+", f"ALL_LLM_TOPK = {max(0, _tk)}")):
        src, n = re.subn(pat, rep, src, count=1, flags=re.M)
        if n != 1: say(f"⚠ پچ تنظیمات موتور اعمال نشد: {pat[:20]}")
    if os.environ.get("TA_EXTRA_STRATS", "1") != "0":      # بازگشت به میانگین (بولینگر+RSI) و مومنتوم (RSI+استوکاستیک) در موتور هستند ولی خاموش بودند؛ بک‌تست خودش بهترین را انتخاب می‌کند
        for k_ in ("meanrev", "mom"):
            src, n = re.subn(r'("%s": dict\(n="[^"]*", e="[^"]*", )run=False' % k_, r"\1run=True", src, count=1)
            if n != 1: say(f"⚠ فعال‌سازی استراتژی {k_} انجام نشد")
    if G.get("_KNOW"):      # اصول آموزشی به همهٔ تماس‌های مدلی پیوست می‌شود
        for fn_ in ("_llm_json", "_llm_raw"):
            src, n = re.subn(r"(def %s\(prompt, model\):\n)" % fn_, r"\1    prompt = _KNOW + chr(10) + '---' + chr(10) + str(prompt)\n", src, count=1)
            if n != 1: say(f"⚠ پیوست آموزش به {fn_} انجام نشد")
    return src

rc, status = 0, "ok"
t0 = time.time()
_before_signals = _journal_count()
# اعلان شروع اسکن حذف شد؛ فقط نتیجهٔ نهایی به گوشی می‌رود.

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
    _ntfy("Infinity", "⏳ جست‌وجو نزدیک پایان است؛ اگر مدیرعامل تأیید کند سیگنال می‌آید، وگرنه این نوبت بی‌سیگنال تمام می‌شود (کیفیت مهم‌تر از تعداد).", 3, ["hourglass"])

_prewarn_thread = None  # اعلان‌های میانی حذف شدند تا گوشی فقط نتیجهٔ نهایی را بگیرد.
if not os.environ.get("NTFY_TOPIC", "").strip(): say("⚠ NTFY_TOPIC خالی است؛ هیچ اعلانی نمی‌آید.")
_provider = "1xai"
_primary_key_ok = bool(os.environ.get("ONE_XAI_API_KEY", "").strip())
if os.environ.get("TA_AGENTS", "0") != "0" and not _primary_key_ok: say("⚠ ONE_XAI_API_KEY در GitHub Secrets تنظیم نشده است؛ آن را اضافه کنید."); status, rc = "error: no key", 1
else:
    try:
        exec(compile(_engine_src(), ENGINE, "exec"), G)
    except _HeadlessStop as e:
        status = f"skip ({e})"
        _why = {"no-setup-in-window": "در مهلت اسکن ستاپ واجد شرایط پیدا نشد",
                "nothing-found": "فرصت معتبر پیدا نشد یا گزینهٔ برتر تکراری بود",
                "hourly-quota": "سقف تعداد سیگنال در بازهٔ اخیر پر شده"}.get(str(e), str(e))
        _detail = _no_signal_diagnosis(_why)
        _ntfy("Infinity · بدون سیگنال", f"{os.environ.get('TA_ASSET', 'Gold')} | علت: {_detail}", 3, ["information_source"])
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
           f"دارایی درخواستی: {os.environ.get('TA_ASSET', 'Gold')}\n"
           f"رکورد سیگنال جدید در ژورنال: {_new_signals}\n"
           f"زمان پایان (تهران): {_tehran()}")
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
