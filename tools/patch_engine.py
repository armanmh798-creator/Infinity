"""وصله‌های زمان اجرا برای Infinity v36؛ engine.py و run.py داخل مخزن دست‌نخورده می‌مانند.
استفاده: python tools/patch_engine.py engine.py run.py
1) Gemini: بلوک کلید و انتخاب مدل Gemini با یک تکهٔ کوتاه عوض می‌شود (فقط وقتی TA_LLM_PROVIDER=1xai).
2) مدیرعامل: تا TA_CEO_MAX_CALLS تماس با TA_CEO_MODEL، بعد با TA_CEO_FALLBACK_MODEL.
3) Grok: مدل‌های grok-* از _grok_chat (کلید و آدرس 1xAi) می‌گذرند و یک تماس دیده‌بان X در هر اجرا به پرامپت مدیرعامل اضافه می‌شود.
4) ALL: فهرست ده دارایی.
5) run.py: بررسی کلید برای 1xai فقط ONE_XAI_API_KEY را می‌خواهد.
6) سقف هزینهٔ هر اجرا (TA_COST_CAP_TOMAN) و ثبت هزینهٔ هر تماس در data/cost_summary.json.
اگر متن فایل‌ها با انتظار نخواند، بدون نوشتن چیزی با خطا می‌ایستد."""
import os, sys

ENGINE = sys.argv[1] if len(sys.argv) > 1 else "engine.py"
RUN = sys.argv[2] if len(sys.argv) > 2 else None
MARK = "# [patch] infinity-1xai v3"
ANCHOR = "import os, re, time, json, getpass, requests\n"

HELPER = MARK + '''
_GROK_SCOUT = {}

def _ceo_model():
    """مدل مدیرعامل برای این تماس: مدل اصلی تا سقف تماس، بعد مدل پشتیبان."""
    n = int(os.environ.get("TA_CEO_CALLS", "0") or 0) + 1
    os.environ["TA_CEO_CALLS"] = str(n)
    try: cap = int(os.environ.get("TA_CEO_MAX_CALLS", "3") or 3)
    except ValueError: cap = 3
    opus = os.environ.get("CLAUDE_OPUS_MODEL", "claude-opus-5-5").strip()
    name = "TA_CEO_MODEL" if n <= cap else "TA_CEO_FALLBACK_MODEL"
    model = os.environ.get(name, "").strip() or opus
    allowed = {os.environ.get(k, d).strip() for k, d in (
        ("CLAUDE_SONNET_MODEL", "claude-sonnet-5-5"), ("CLAUDE_HAIKU_MODEL", "claude-haiku-5-5"),
        ("CLAUDE_OPUS_MODEL", "claude-opus-5-5"), ("CLAUDE_FABLE_MODEL", "claude-fable-5-2"),
        ("CLAUDE_MYTHOS_MODEL", "claude-mythos-5-2"))}
    if model not in allowed or not model.startswith("claude-"):
        print(f"⚠ {name}={model} در فهرست مدل‌های Claude این اجرا نیست؛ مدیرعامل با {opus} اجرا می‌شود.")
        model = opus
    print(f"مدیرعامل · تماس {n} · مدل {model}")
    return model

def _x_scout_text():
    """یک تماس Grok در هر اجرا برای خلاصهٔ احساسات X؛ خاموشی یا خطا یعنی متن خالی."""
    if os.environ.get("TA_X_SCOUT", "1") != "1": return ""
    a = str(globals().get("ASSET", ""))
    if a in _GROK_SCOUT: return _GROK_SCOUT[a]
    out = ""
    try:
        q = ("You are the X (Twitter) sentiment scout of a scalp-trading desk. Asset: " + a + ". "
             "If you have live access to X, summarise in at most 150 words the main themes of the last 24 hours: "
             "bullish vs bearish balance, notable accounts, breaking news and rumours. "
             "If you do NOT have live X access, begin with 'NO LIVE X ACCESS' and add only what you know. No price predictions.")
        t = str(_grok_chat(q, os.environ.get("GROK_MODEL", "grok-4.7")) or "").strip()
        if t: out = "\\n\\nX SENTIMENT SCOUT (Grok; advisory, unverified social data):\\n" + t[:1200]
    except Exception as e:
        print(f"⚠ دیده‌بان X (Grok) ناموفق بود: {type(e).__name__}: {str(e)[:120]}")
    _GROK_SCOUT[a] = out
    return out

_BUDGET = {"spent": 0.0, "calls": 0, "by": {}, "stop": False}
_PRICE_1K = {"claude-fable": (2700, 15000), "claude-mythos": (2700, 15000), "claude-opus": (1350, 8800),
             "claude-sonnet": (705, 3524), "claude-haiku": (90, 500), "grok": (420, 3300)}

class _BudgetStop(BaseException):
    """سقف هزینهٔ اجرا پر شد؛ عمداً BaseException است تا try/except Exception معمولی جلویش را نگیرد."""

def _budget_cap():
    try: return float(os.environ.get("TA_COST_CAP_TOMAN", "0") or 0)
    except ValueError: return 0.0

def _budget_write():
    try:
        d = os.environ.get("TA_DATA", "data"); os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "cost_summary.json"), "w", encoding="utf-8") as f:
            json.dump({"run_id": os.environ.get("GITHUB_RUN_ID", ""), "mode": os.environ.get("TA_MODE", ""),
                       "asset": os.environ.get("TA_ASSET", ""), "cap_toman": _budget_cap(),
                       "spent_toman": round(_BUDGET["spent"]), "calls": _BUDGET["calls"],
                       "stopped_by_cap": _BUDGET["stop"], "by_model": _BUDGET["by"]}, f, ensure_ascii=False)
    except Exception: pass

def _budget_add(model, usage, cost):
    """هزینهٔ هر تماس: عدد واقعی درگاه اگر در هدر آمده باشد، وگرنه برآورد از توکن‌ها با قیمت لیست؛ هرگز خطا نمی‌دهد."""
    try:
        m = str(model or ""); u = usage or {}
        tin = int(u.get("input_tokens", u.get("prompt_tokens", 0)) or 0)
        tout = int(u.get("output_tokens", u.get("completion_tokens", 0)) or 0)
        c = None
        if cost is not None:
            try: c = float(cost)
            except Exception: c = None
        if c is None:
            pin, pout = next((v for k, v in _PRICE_1K.items() if m.startswith(k)), (705, 3524))
            c = tin / 1000.0 * pin + tout / 1000.0 * pout
        _BUDGET["spent"] += c; _BUDGET["calls"] += 1
        b = _BUDGET["by"].setdefault(m, {"calls": 0, "in": 0, "out": 0, "toman": 0})
        b["calls"] += 1; b["in"] += tin; b["out"] += tout; b["toman"] = round(b["toman"] + c)
        _budget_write()
    except Exception: pass

def _budget_check():
    cap = _budget_cap()
    if cap > 0 and _BUDGET["spent"] >= cap:
        _BUDGET["stop"] = True; _budget_write()
        print(f"⛔ سقف هزینهٔ این اجرا ({cap:,.0f} تومان) پر شد؛ تماس‌های مدل متوقف شدند.")
        raise _BudgetStop("cost cap reached")
'''

G_START = 'if LLM_PROVIDER != "rayegan":\n    _ui("#7c4dff"'
G_END = '    if LLM_PROVIDER in ("anthropic", "1xai"):\n        _claude_api = '
STUB = '''    # [patch] Gemini کنار گذاشته شد؛ همهٔ موتورها از ONE_XAI_API_KEY می‌آیند
    DEEP = QUICK = 'auto'; _lvl = '-'
    _GKEYS = []; _GK = {"i": 0, "exhausted": False}
    def _gem_resilient(prompt, model=None):
        raise RuntimeError("Gemini در این نسخه غیرفعال است؛ همهٔ تماس‌ها از 1xAi می‌گذرد.")
    print("🔑 Gemini غیرفعال است؛ همهٔ مدل‌ها با ONE_XAI_API_KEY صدا زده می‌شوند.")

'''
CEO_OLD = ('        opus = os.environ.get("CLAUDE_OPUS_MODEL", "claude-opus-5-5").strip()\n'
           '        for k_, model in enumerate((opus, deep)):')
CEO_NEW = ('        opus = _ceo_model()\n'
           '        for k_, model in enumerate((opus, deep)):')
PC_OLD = 'def _primary_chat(prompt, model=None):\n    if LLM_PROVIDER in ("anthropic", "1xai"):\n'
PC_NEW = ('def _primary_chat(prompt, model=None):\n'
          '    if str(model or "").lower().startswith("grok") and LLM_PROVIDER in ("anthropic", "1xai"): return _grok_chat(prompt, model)\n'
          '    if LLM_PROVIDER in ("anthropic", "1xai"):\n')
SC_OLD = r'''        prompt += "\n\nINDEPENDENT FRONTIER TACTICAL REVIEWS (advisory only; Python levels and hard risk gates remain authoritative):\n" + _frontier_tactical_text()
'''
SC_NEW = SC_OLD + '        prompt += _x_scout_text()\n'
BC_OLD = '    via_1xai = LLM_PROVIDER == "1xai"\n    key = _rg_secret("ONE_XAI_API_KEY") if via_1xai'
BC_NEW = '    _budget_check()\n' + BC_OLD
BG_OLD = '    key = _rg_secret("GROK_API_KEY")\n    if not key: raise RuntimeError("GROK_API_KEY is missing")\n'
BG_NEW = '    _budget_check()\n' + BG_OLD
RC_OLD = 'def _record_claude_usage(usage, model=None, cost_toman=None, served_model=None, role=None):\n    """ثبت توکن/هزینهٔ واقعی درگاه در صورت وجود؛ بدون prompt یا کلید."""\n'
RC_NEW = RC_OLD + '    _budget_add(model, usage, cost_toman)\n'
RG_OLD = 'def _record_grok_usage(usage):\n    """Log token counts only; never store prompts, completions or credentials."""\n'
RG_NEW = RG_OLD + '    _budget_add(os.environ.get("GROK_MODEL", "grok-4.7"), usage, None)\n'
ALL_OLD = 'ALL_ASSETS = ["Gold", "BTC", "ETH"]'
ALL_NEW = 'ALL_ASSETS = ["Gold", "NAS100", "EURUSD", "GBPUSD", "BTC", "ETH", "DOGE", "XRP", "ADA", "SOL"]'
RUN_OLD = 'if _provider == "grok" else any('
RUN_NEW = 'if _provider == "grok" else bool(os.environ.get("ONE_XAI_API_KEY", "").strip()) if _provider == "1xai" else any('


def patch_engine(src):
    if MARK in src:
        return src, "engine.py: از قبل اعمال شده است."
    if os.environ.get("TA_LLM_PROVIDER", "").strip().lower() != "1xai":
        raise SystemExit("patch_engine: TA_LLM_PROVIDER باید 1xai باشد؛ چیزی نوشته نشد.")
    if "\r\n" in src:
        raise SystemExit("patch_engine: engine.py با پایان‌خط ویندوز است؛ چیزی نوشته نشد.")
    need = {"anchor": (src.count(ANCHOR), 1), "gemini-start": (src.count(G_START), 1), "gemini-end": (src.count(G_END), 1),
            "ceo": (src.count(CEO_OLD), 1), "primary-chat": (src.count(PC_OLD), 1), "scout": (src.count(SC_OLD), 1),
            "all-assets": (src.count(ALL_OLD), 1), "budget-claude": (src.count(BC_OLD), 1), "budget-grok": (src.count(BG_OLD), 1),
            "rec-claude": (src.count(RC_OLD), 1), "rec-grok": (src.count(RG_OLD), 1)}
    bad = {k: v[0] for k, v in need.items() if v[0] != v[1]}
    if bad or src.index(G_START) > src.index(G_END):
        raise SystemExit(f"patch_engine: متن engine.py با انتظار نمی‌خواند {bad}؛ چیزی نوشته نشد.")
    i, j = src.index(G_START), src.index(G_END)
    src = src[:i] + 'if LLM_PROVIDER != "rayegan":\n' + STUB + src[j:]
    src = (src.replace(ANCHOR, ANCHOR + HELPER, 1).replace(CEO_OLD, CEO_NEW, 1).replace(PC_OLD, PC_NEW, 1)
              .replace(SC_OLD, SC_NEW, 1).replace(ALL_OLD, ALL_NEW, 1)
              .replace(BC_OLD, BC_NEW, 1).replace(BG_OLD, BG_NEW, 1).replace(RC_OLD, RC_NEW, 1).replace(RG_OLD, RG_NEW, 1))
    compile(src, ENGINE, "exec")
    return src, "engine.py: Gemini غیرفعال، سقف تماس مدیرعامل، مسیر Grok، فهرست ده دارایی و سقف هزینه اعمال شد."


def patch_run(src):
    if RUN_NEW in src:
        return src, "run.py: از قبل اعمال شده است."
    if src.count(RUN_OLD) != 1:
        raise SystemExit(f"patch_engine: متن run.py با انتظار نمی‌خواند (کلید={src.count(RUN_OLD)})؛ چیزی نوشته نشد.")
    src = src.replace(RUN_OLD, RUN_NEW, 1)
    compile(src, RUN or "run.py", "exec")
    return src, "run.py: بررسی کلید برای 1xai روی ONE_XAI_API_KEY."


def main():
    jobs = [(ENGINE, patch_engine)] + ([(RUN, patch_run)] if RUN else [])
    results = []
    for path, fn in jobs:                      # اول همه محاسبه می‌شوند؛ نوشتن فقط اگر همه سالم باشند
        with open(path, encoding="utf-8") as f:
            old = f.read()
        new, msg = fn(old)
        results.append((path, old, new, msg))
    for path, old, new, msg in results:
        if new != old:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new)
        print("patch_engine:", msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
