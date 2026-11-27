# -*- coding: utf-8 -*-
"""تیم ۲۵ایجنت Infinity: مسیریاب موتورها و اجرای مشورتی ایجنت‌ها از درگاه 1xAi (یک کلید، همهٔ موتورها).

- هر ایجنت در هر حالت (Normal / VIP / Gold / Eco) موتور اصلی و زنجیرهٔ جایگزین دارد؛ ناموفق = رفتن به جایگزین.
- ایجنت‌ها فقط مشاوره می‌دهند؛ سطوح قیمت و گیت‌های ریسک پایتون معتبر می‌مانند.
- نظم اجرا (v2): مرحلهٔ ۱ سلاطین (ایجنت ۲ تا ۶) هر کدام تنها و مستقل، مرحلهٔ ۲ تیم تحقیق (بقیهٔ pre)، مرحلهٔ ۳ مدیرعامل (آرمان میرحسینی).
  زمان شروع و پایان هر ایجنت اندازه‌گیری و در data/desk_summary.json ثبت می‌شود و همان گزارش انضباط به مدیرعامل داده می‌شود.
- Grok (۱۱) همان دیده‌بان X داخل engine است. ایجنت‌های post (۲۱، ۲۲) و screen (۲۳ تا ۲۵) هنوز به موتور وصل نیستند.
- سقف هزینه: تیم فقط تا TA_DESK_SHARE از سقف اجرا (پیش‌فرض ۰٫۴۵) خرج می‌کند تا مدیرعامل اصلی جا داشته باشد.
- هیچ متن پرامپت یا پاسخ در فایل خلاصه ذخیره نمی‌شود.
استفاده‌ی دستی: python tools/desk25.py --table [Normal|VIP|Gold|Eco]   |   python tools/desk25.py --estimate
"""
import os, re, sys, json, time
import concurrent.futures as cf

OP, SO, HA = "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"
FA = "claude-fable-5-2"
# Mythos در بررسی موتورها HTTP 404 داد؛ تا زمانی که در حساب فعال نشده Fable جایگزین است. با TA_MYTHOS_MODEL می‌شود برگرداند.
MY = os.environ.get("TA_MYTHOS_MODEL", "").strip() or FA
# gemini-3.8-flash نام پنل 1xAi است؛ پاسخ خالی‌اش از سقف کم توکن بود (پایین‌تر، کف ۱۵۰۰ توکن).
GS, GF, GA = "gpt-6.2-sol", "gemini-3.8-flash", "gemini-4-argon"
GK = "grok-4.7"
# deepseek-flash و glm-5.3-flash: نام‌های جایگزین؛ با تماس واقعی هنوز سنجیده نشده‌اند (بررسی موتورها در اجرای بعدی می‌سنجد).
DP, DF = "deepseek-v4-pro", "deepseek-flash"
QP, QF = "qwen3.7-plus", "qwen3.8-flash"
GL, GLF, MM = "glm-5.3", "glm-5.3-flash", "MiniMax-M3.1-Flash"
LU = "gpt-6-luna"

# قیمت برآوردی هر هزار توکن (تومان): (ورودی، خروجی). قیمت Luna از برازش روی گزارش مصرف خود شما (۷۹ تماس) است و تقریبی. قیمت DF و GLF هم برآوردی است. فقط برای سقف هزینه؛ عدد نهایی در صفحهٔ مصرف 1xAi است.
PRICE_1K = {
    FA: (2700, 15000), "claude-mythos-5-2": (2700, 15000), OP: (1350, 8800), SO: (705, 3524), HA: (90, 500),
    GS: (490, 2200), GA: (360, 2800), GF: (160, 800), GK: (420, 3300),
    LU: (360, 585), DP: (106, 423), DF: (32, 127), QP: (115, 458), QF: (32, 100), GL: (88, 529), GLF: (32, 106), MM: (32, 127),
}

SOVEREIGN_IDS = (2, 3, 4, 5, 6)

SYSTEM_BASE = (
    "You are one named specialist on a trading desk that analyses a single trade setup. "
    "Judge ONLY from the BRIEF; never invent prices, news, indicator values or statistics. "
    "If the brief lacks what your role needs, answer NA. "
    "The brief may end with an output-format request addressed to the desk chief: ignore it. "
    "You are advisory; you cannot change levels or risk gates. Be blunt and specific, no disclaimers.\nYOUR ROLE: ")
FORMAT = ("Reply in exactly this format, English, max 70 words in total:\n"
          "VERDICT: GO|WAIT|NO|NA\nCONF: 0-100\nWHY: <one or two sentences>")
SOV_RULE = ("\nYou are one of the five sovereigns. You work alone and report only to the desk chief; you do not see anyone else. "
            "Take a clear stance. Use NA only if the brief lacks everything your method needs; "
            "if only some data is missing, judge from what is present and name what is missing.")
FORMAT_S = ("Reply in exactly this format, English, max 120 words in total:\n"
            "VERDICT: GO|WAIT|NO|NA\nCONF: 0-100\n"
            "WHY: <three or four sentences: your signature method applied to this brief, the single biggest risk, and what would change your mind>")

# حالت چهارم Eco: کارگرها فقط روی سه موتور ارزان (Haiku 5.5، GLM 5.3 Flash، GPT-6 Luna)؛ مدیرعامل (آرمان میرحسینی) Sonnet 5.5 با Opus 5.5 فقط جایگزین.
ECO = {1: SO,
       2: HA, 3: LU, 4: GLF, 5: HA, 6: LU, 7: LU, 8: HA, 9: LU, 10: HA,
       11: GK,
       12: GLF, 13: LU, 14: HA, 15: GLF, 16: HA, 17: GLF, 18: HA, 19: GLF, 20: LU,
       21: GLF, 22: HA, 23: HA, 24: GLF, 25: LU}
ECO_POOL = [HA, GLF, LU]

def _a(i, name, cat, phase, n, v, g, fb, role, mt=500):
    return {"id": i, "name": name, "cat": cat, "phase": phase, "models": {"Normal": n, "VIP": v, "Gold": g, "Eco": ECO.get(i, HA)},
            "fb": fb, "role": role, "max_tokens": mt}

AGENTS = [
    _a(1, "آرمان میرحسینی (مدیرعامل)", "فرماندهی", "synth", GS, MY, MY, [FA, OP, GS, SO],
       "Chief's second engine. Read all specialist reports, find the strongest agreement and the strongest disagreement, "
       "list at most 3 concrete risks and give a lean GO/WAIT/NO in at most 150 words. Do not average votes blindly: weigh by evidence in the brief. "
       "You also supervise discipline: the script gives you a measured log of who ran, with which engine, when, and who failed or was late.", 900),
    _a(2, "Al Brooks", "سلاطین · پرایس‌اکشن", "pre", SO, SO, OP, [DP],
       "Al Brooks: read the setup bar by bar. Trend versus trading range, always-in direction, signal and entry bar quality, with-trend pullbacks, failed breakouts, trapped traders."),
    _a(3, "Larry Williams", "سلاطین · نوسان و تکنیکال", "pre", GF, GS, SO, [GLF],
       "Larry Williams: short-term volatility breakout logic (expansion beyond prior range), short-term lows and highs inside the larger trend, smash-day style reversals. Judge if the timing fits."),
    _a(4, "Jake Bernstein", "سلاطین · سیکل و فصلی", "pre", QP, GA, SO, [GF],
       "Jake Bernstein: seasonal and cyclical tendencies, time of year and day of week, cycle timing, momentum timing. Say NA if the brief has no date/cycle information."),
    _a(5, "Richard Wyckoff", "سلاطین · ساختار بازار", "pre", DF, DP, SO, [GLF],
       "Richard Wyckoff: accumulation or distribution phase, spring or upthrust, effort versus result, support/resistance structure and where the composite operator seems positioned."),
    _a(6, "Linda Raschke", "سلاطین · مومنتوم و شکست", "pre", GLF, GL, SO, [QF],
       "Linda Raschke: momentum, pullbacks to the 20 EMA in a strong trend, 80-20 style reversals, breakout failures versus continuation. Judge quality of the momentum."),
    _a(7, "پروفسور اقتصاد ارشد", "تحقیق و کلان", "pre", DP, GS, OP, [GF],
       "Senior macro economist: rates, real yields, dollar, inflation, central banks and how they bear on this asset and direction. Use only macro facts present in the brief; otherwise NA."),
    _a(8, "معامله‌گر باتجربه", "تحقیق و ژورنال", "pre", DP, SO, SO, [DF],
       "Veteran discretionary trader: does the setup match a disciplined playbook, what are its typical failure modes, what would make you skip it."),
    _a(9, "تریدر خبری (Kovner)", "میز خبر", "pre", DP, SO, SO, [GF],
       "Bruce Kovner style news and event-risk trader: scheduled events and headlines near the entry, whether to stand aside, whether the move already priced the news."),
    _a(10, "مدیر ریسک", "کنترل حجم و SL/TP", "pre", DP, SO, SO, [GLF],
       "Risk manager: sanity of stop and target distance versus volatility, reward-to-risk, risk per trade, correlation and exposure. Flag stops inside the noise."),
    _a(11, "Grok (دیده‌بان X)", "ساپورتر کل تیم", "engine", GK, GK, GK, [HA],
       "X sentiment scout; implemented in engine.py via _x_scout_text (TA_X_SCOUT)."),
    _a(12, "تریدر خوش‌بین (کلون ۱)", "تحقیق · موافق", "pre", DF, GF, HA, [HA],
       "Optimist: make the strongest honest case FOR taking this setup, using only facts in the brief."),
    _a(13, "تریدر بدبین (کلون ۲)", "تحقیق · نقد", "pre", MM, MM, HA, [GLF],
       "Pessimist: make the strongest honest case AGAINST this setup and name what would invalidate it, using only facts in the brief."),
    _a(14, "تحلیل‌گر بازار (کلون ۳)", "تکنیکال مولتی‌تایم", "pre", DF, GF, HA, [HA],
       "Technical market analyst: do the timeframes, trend, key levels and indicators in the brief agree with the setup direction?"),
    _a(15, "تحلیل‌گر خبر (کلون ۴)", "تقویم و اخبار", "pre", DF, GF, GF, [HA],
       "News analyst: from the calendar and headlines in the brief, is there event risk or a catalyst that helps or hurts this setup?"),
    _a(16, "تحلیل‌گر بنیادی (کلون ۵)", "فاندامنتال", "pre", GLF, QF, HA, [HA],
       "Fundamental analyst: valuation, flows, macro or on-chain fundamentals present in the brief and whether they support the direction."),
    _a(17, "تحلیل‌گر احساسات (کلون ۶)", "سنتیمنت بازار", "pre", GLF, MM, HA, [QF],
       "Sentiment analyst: positioning, crowding, funding or social tone present in the brief; is the trade with or against a crowded side?"),
    _a(18, "اعتبارسنج اجرا", "اسپرد و لغزش", "pre", GLF, GF, HA, [HA],
       "Execution validator: spread, slippage, liquidity and session timing from the brief; can this entry realistically be filled near the stated level?"),
    _a(19, "گردآورندهٔ خبر و نگهبان", "رصد پنجرهٔ خبر", "pre", QF, HA, HA, [GLF],
       "News window guard: list in one line the news or calendar items inside the next trading window that matter; NA if none are in the brief."),
    _a(20, "بازبین بک‌تست ۹۰ روزه", "بک‌تست ۶ تایم‌فریم", "pre", GLF, DF, DF, [HA],
       "Backtest reviewer: judge the evidence in the brief (sample size, win rate, expectancy, out-of-sample). Small samples deserve low trust; say so."),
    _a(21, "اعلان‌ساز تلگرام", "خروجی · کارت‌ها", "post", QF, HA, HA, [GLF], "Telegram card writer (after the decision; not wired yet)."),
    _a(22, "ژورنال‌نویس", "خروجی · ثبت", "post", GLF, DF, HA, [HA], "Journal writer (after the decision; not wired yet)."),
    _a(23, "غربالگر تکنیکال (ALL)", "غربال ۱۰ دارایی", "screen", QF, HA, HA, [GLF], "Technical screener for ALL mode (not wired yet)."),
    _a(24, "غربالگر زمینه (ALL)", "غربال نقدینگی", "screen", GLF, QF, QF, [HA], "Context screener for ALL mode (not wired yet)."),
    _a(25, "رتبه‌بند نامزدها (ALL)", "انتخاب بهترین", "screen", GLF, DF, DF, [HA], "Candidate ranker for ALL mode (not wired yet)."),
]

def norm_mode(m):
    m = str(m or "").strip().lower()
    return {"vip": "VIP", "gold": "Gold", "eco": "Eco"}.get(m, "Normal")

def chain(a, mode):
    """موتور اصلی + جایگزین‌ها بدون تکرار؛ برای مدیرعامل در Normal زنجیرهٔ ارزان‌تر."""
    fb = [OP, SO] if (a["id"] == 1 and mode == "Normal") else a["fb"]
    if mode == "Eco":
        fb = [OP, HA] if a["id"] == 1 else [m for m in ECO_POOL if m != a["models"]["Eco"]]
    out = []
    for m in [a["models"][mode]] + list(fb):
        if m not in out:
            out.append(m)
    return out

def _alias(m):
    """اگر نام مدل در درگاه فرق دارد: TA_MODEL_MAP='{"deepseek-v4-pro":"نام-واقعی"}'."""
    try:
        return json.loads(os.environ.get("TA_MODEL_MAP", "") or "{}").get(m, m)
    except Exception:
        return m

def est_toman(model, tin, tout):
    pin, pout = PRICE_1K.get(model, (705, 3524))
    return tin / 1000.0 * pin + tout / 1000.0 * pout

def estimate(mode, tin=2500, tout=300, synth_in=6000, synth_out=500):
    """برآورد تقریبی هزینهٔ تیم با موتور اصلی هر ایجنت (بدون جایگزین)؛ فقط برای تصمیم‌گیری."""
    mode = norm_mode(mode); total = 0.0; rows = []
    for a in AGENTS:
        if a["phase"] not in ("pre", "synth"):
            continue
        m = a["models"][mode]
        c = est_toman(m, synth_in, synth_out) if a["phase"] == "synth" else est_toman(m, tin, tout)
        rows.append((a["id"], a["name"], m, round(c))); total += c
    return round(total), rows

def _clip(brief, head=5000, tail=1000):
    b = str(brief or "")
    return b if len(b) <= head + tail else b[:head] + "\n[...]\n" + b[-tail:]

def _parse(text):
    t = str(text or "")
    v = re.search(r"VERDICT\s*[:=]\s*\**\s*(GO|WAIT|NO|NA)\b", t, re.I)
    c = re.search(r"CONF\w*\s*[:=]\s*\**\s*(\d{1,3})", t, re.I)
    w = re.search(r"WHY\s*[:=]\s*(.+)", t, re.I | re.S)
    why = re.sub(r"\s+", " ", (w.group(1) if w else t)).strip()[:450]
    return (v.group(1).upper() if v else "NA"), (min(100, int(c.group(1))) if c else None), why

def _http_call(model, messages, max_tokens, timeout):
    import requests
    base = os.environ.get("ONE_XAI_BASE_URL", "https://1xai.ir").rstrip("/")
    key = os.environ.get("ONE_XAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("no key")
    h = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    if str(model).startswith("gpt-"):
        # مدل‌های GPT در گزارش مصرف 1xAi از /v1/responses رد شده‌اند
        r = requests.post(base + "/v1/responses", headers=h, timeout=timeout,
                          json={"model": model, "input": messages, "max_output_tokens": max(300, int(max_tokens) * 3)})
        if r.status_code != 200:
            raise RuntimeError("HTTP %s" % r.status_code)
        j = r.json()
        txt = j.get("output_text") or ""
        if not txt:
            parts = []
            for o in (j.get("output") or []):
                for c in ((o.get("content") or []) if isinstance(o, dict) else []):
                    if isinstance(c, dict) and c.get("text"):
                        parts.append(str(c["text"]))
            txt = "".join(parts)
        return str(txt), (j.get("usage") or {})
    # مدل‌های «تفکرکننده» (GLM، DeepSeek، Gemini و ...) بخشی از سقف توکن را صرف فکر کردن می‌کنند؛ سقف کم یعنی پاسخ خالی با HTTP 200.
    # برای غیر Claude کف ۱۵۰۰ توکن می‌گذاریم؛ هزینه‌اش روی مدل‌های ارزان ناچیز است.
    mt = int(max_tokens) if str(model).startswith("claude") else max(int(max_tokens), 1500)
    body = {"model": model, "messages": messages, "max_tokens": mt}
    for _ in range(2):
        r = requests.post(base + "/v1/chat/completions", headers=h, json=body, timeout=timeout)
        if r.status_code == 400 and "max_tokens" in r.text and "max_tokens" in body:
            body["max_completion_tokens"] = body.pop("max_tokens"); continue
        break
    if r.status_code != 200:
        raise RuntimeError("HTTP %s" % r.status_code)
    j = r.json()
    ch = (j.get("choices") or [{}])[0].get("message", {})
    c = ch.get("content")
    if isinstance(c, list):
        c = "".join(str(x.get("text", "")) if isinstance(x, dict) else str(x) for x in c)
    return str(c or ""), (j.get("usage") or {})

def _envf(name, default):
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return float(default)

def run_desk(brief, asset="", hooks=None, http=None, mode=None):
    """تیم را در سه مرحله اجرا می‌کند و متن گزارش مشورتی را برمی‌گرداند؛ هرگز استثنا نمی‌دهد."""
    hooks = hooks or {}; http = http or _http_call
    mode = norm_mode(mode or os.environ.get("TA_MODE"))
    share = _envf("TA_DESK_SHARE", 0.45)
    wall = _envf("TA_DESK_BUDGET_SEC", 200)
    workers = max(1, int(_envf("TA_DESK_WORKERS", 6)))
    stagger = max(0.0, _envf("TA_DESK_STAGGER_SEC", 0.4))
    def cap():
        try: return float(hooks["cap"]())
        except Exception: return 0.0
    def over(frac):
        try: return cap() > 0 and float(hooks["spent"]()) >= cap() * frac
        except Exception: return False
    def pay(model, usage, cost):
        try:
            if "add" in hooks: hooks["add"](model, usage, cost)
        except Exception: pass
    brief_t = _clip(brief); t0 = time.time()

    def rec_of(a, stage, status="skipped"):
        return {"id": a["id"], "name": a["name"], "stage": stage, "planned": a["models"][mode], "served": "", "status": status,
                "in": 0, "out": 0, "toman": 0, "verdict": "NA", "conf": None, "why": "", "start": None, "end": None}

    def _ask(a, system_extra, user, frac, mt, stage):
        rec = rec_of(a, stage)
        for m in chain(a, mode)[:3]:
            if over(frac) or time.time() - t0 > wall:
                rec["status"] = "budget"; return rec
            msgs = [{"role": "system", "content": SYSTEM_BASE + a["role"] + system_extra},
                    {"role": "user", "content": user}]
            try:
                text, u = http(_alias(m), msgs, mt, 60)
            except Exception as e:
                rec["status"] = "err:" + str(e)[:40]; continue
            tin = int(u.get("prompt_tokens", u.get("input_tokens", 0)) or 0)
            tout = int(u.get("completion_tokens", u.get("output_tokens", 0)) or 0)
            c = est_toman(m, tin, tout)
            pay(m, u, c)
            rec.update(served=m, **{"in": tin, "out": tout, "toman": round(c)})
            if not str(text).strip():
                rec["status"] = "empty"; continue
            rec["status"] = "ok" if m == a["models"][mode] else "fallback"
            rec["verdict"], rec["conf"], rec["why"] = _parse(text)
            rec["text"] = str(text).strip()
            return rec
        return rec

    def ask(a, system_extra, user, frac, mt, delay, stage):
        if delay: time.sleep(delay)
        s = time.time() - t0
        rec = _ask(a, system_extra, user, frac, mt, stage)
        rec["start"] = round(s, 1); rec["end"] = round(time.time() - t0, 1)
        return rec

    def run_stage(stage, agents, user, extra, mt_of, frac, until):
        out = []
        if not agents: return out
        ex = cf.ThreadPoolExecutor(max_workers=min(workers, len(agents)))
        futs = {ex.submit(ask, a, extra, user, frac, mt_of(a), (k * stagger if k < workers else 0), stage): a for k, a in enumerate(agents)}
        done, pending = cf.wait(list(futs), timeout=max(1.0, until - (time.time() - t0)))
        for f in done:
            try: out.append(f.result())
            except BaseException: out.append(rec_of(futs[f], stage, "crash"))
        for f in pending:
            f.cancel(); out.append(rec_of(futs[f], stage, "timeout"))
        ex.shutdown(wait=False, cancel_futures=True)
        return out

    sov = [a for a in AGENTS if a["phase"] == "pre" and a["id"] in SOVEREIGN_IDS]
    team = [a for a in AGENTS if a["phase"] == "pre" and a["id"] not in SOVEREIGN_IDS]
    head = f"ASSET: {asset}\nMODE: {mode}\n\nBRIEF:\n{brief_t}\n\n"
    recs = run_stage("sovereigns", sov, head + FORMAT_S, SOV_RULE, lambda a: 700, share, 0.40 * wall)
    recs += run_stage("team", team, head + FORMAT, "", lambda a: a["max_tokens"], share, 0.80 * wall)
    recs.sort(key=lambda r: r["id"])
    good = [r for r in recs if r["status"] in ("ok", "fallback") and r["verdict"] != "NA"]
    tally = {k: sum(1 for r in good if r["verdict"] == k) for k in ("GO", "WAIT", "NO")}
    tally_sov = {k: sum(1 for r in good if r["verdict"] == k and r["id"] in SOVEREIGN_IDS) for k in ("GO", "WAIT", "NO")}

    def disc_lines():
        key = lambda r: (r["start"] if r["start"] is not None else 9999, r["id"])
        return [f"{r['stage']} #{r['id']} {r['planned']}->{r['served'] or '-'} {r['status']} {r['start'] if r['start'] is not None else '-'}s..{r['end'] if r['end'] is not None else '-'}s {r['verdict']}"
                for r in sorted(recs, key=key)]

    synth = None
    sa = AGENTS[0]; fr = min(0.6, share + 0.15)
    if good and not over(fr):
        lines = "\n".join(f"[{r['id']} {r['name']}] {r['verdict']} {r['conf'] if r['conf'] is not None else '-'}: {r['why']}" for r in good)
        su = (f"ASSET: {asset}\nMODE: {mode}\n\nBRIEF:\n{brief_t}\n\n"
              f"SPECIALIST REPORTS (specialists 2-6 are the five sovereigns; they worked alone and independently):\n{lines}\n\n"
              "DESK DISCIPLINE LOG (measured by the script, not opinions; format: stage #id planned->served status start..end verdict):\n"
              + "\n".join(disc_lines()) + "\n\n"
              "Reply: LEAN: GO|WAIT|NO, then max 150 words. Name any missing, failed or late specialist that could change the lean.")
        synth = ask(sa, "", su, fr, sa["max_tokens"], 0, "chief")
        recs.append(synth)

    try:
        d = os.environ.get("TA_DATA", "data"); os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "desk_summary.json"), "w", encoding="utf-8") as f:
            json.dump({"run_id": os.environ.get("GITHUB_RUN_ID", ""), "mode": mode, "asset": str(asset), "tally": tally,
                       "tally_sovereigns": tally_sov, "answered": len(good), "asked": len(sov) + len(team),
                       "seconds": round(time.time() - t0),
                       "agents": [{k: v for k, v in r.items() if k not in ("text", "why")} for r in recs]}, f, ensure_ascii=False)
    except Exception:
        pass

    if not good:
        return ""
    hhmm = time.strftime("%H:%M", time.gmtime())
    sg = [r for r in good if r["id"] in SOVEREIGN_IDS]; og = [r for r in good if r["id"] not in SOVEREIGN_IDS]
    fmt = lambda r, n: (f"- {r['name']} [{r['served']}]: {r['verdict']}" + (f" {r['conf']}" if r['conf'] is not None else "") + f" — {r['why'][:n]}")
    out = (f"\n\nDESK TEAM REPORTS ({len(good)} of {len(sov) + len(team)} specialists answered; asset {asset}; {hhmm} UTC; mode {mode}). "
           "Advisory only: unverified model opinions based solely on the brief; Python levels and hard risk gates remain authoritative.\n"
           f"TALLY: GO {tally['GO']} / WAIT {tally['WAIT']} / NO {tally['NO']}\n")
    if sg:
        out += f"\nSOVEREIGNS (each worked alone, unaveraged; {len(sg)} of {len(sov)} answered):\n" + "\n".join(fmt(r, 420) for r in sg) + "\n"
    if og:
        out += "\nRESEARCH TEAM:\n" + "\n".join(fmt(r, 200) for r in og) + "\n"
    miss = [f"#{r['id']}:{r['status']}" for r in recs if r["id"] != 1 and r["status"] not in ("ok", "fallback")]
    if miss:
        out += "\nNOT ANSWERED: " + ", ".join(miss) + "\n"
    if synth and synth.get("text"):
        out += f"\nCHIEF'S SECOND-ENGINE SYNTHESIS [{synth['served']}]:\n{synth['text'][:900]}"
    return out[:9000]

if __name__ == "__main__":
    mode = norm_mode(sys.argv[2] if len(sys.argv) > 2 else "Normal")
    if "--estimate" in sys.argv:
        for m in ("Normal", "VIP", "Gold", "Eco"):
            print(m, estimate(m)[0], "toman (rough, desk only)")
    else:
        for a in AGENTS:
            print(a["id"], a["phase"], a["name"], "|", " → ".join(chain(a, mode)))
