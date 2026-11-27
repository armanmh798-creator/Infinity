# -*- coding: utf-8 -*-
"""وصلهٔ امتیاز ۱۰۰ روی engine.py (از patch_team3.py صدا زده می‌شود).
استفاده‌ی مستقل: python tools/patch_score.py engine.py

چه می‌کند:
1) گیت کیفیت _strict_reject دیگر سیگنال را رد نمی‌کند. هر دلیل یکتا (پرچم نرم، پرچم سخت، NO مدیرعامل، NO ایجنت SMC)
   یک امتیاز از ۱۰۰ کم می‌کند و نمره با فهرست دلیل‌ها در متن اعلان می‌آید. تنها رد سخت: نبودن حد ضرر.
   (داده کهنه از قبل در مسیر تحلیل، پیش از این گیت، سیگنال را می‌بندد و دست‌نخورده است.)
2) حلقهٔ جست‌وجوی ALL در پایان مهلت، بهترین گزینه را می‌دهد، حتی وقتی TA_FINAL_FALLBACK=0 باشد.
خاموش‌کردن بدون تغییر کد: متغیر TA_SCORE100=0 (همان رفتار قبلی برمی‌گردد).
اگر هر لنگر دقیقاً یک‌بار پیدا نشود، فایل دست‌نخورده می‌ماند و هشدار چاپ می‌شود."""
import sys

MARK = "# [patch] score100"

BLOCK = r'''# [patch] score100
SCORE100 = os.environ.get("TA_SCORE100", "1") != "0"      # 1 = هر دلیلِ یکتا یک امتیاز از ۱۰۰ کم می‌کند و سیگنال رد نمی‌شود؛ 0 = گیت قدیمی
if SCORE100 and os.environ.get("TA_STRAT_REQUIRED", "0") != "1": STRAT_REQUIRED = False      # نبودِ استراتژیِ کتابچه‌ای دیگر تحلیل را نمی‌بندد؛ فقط یک پرچم (cut) می‌شود و نمره کم می‌کند

def _score100(g):
    """(نمره، فهرست دلیل‌ها، تعداد پرچم سخت). نمرهٔ واقعی؛ دستکاری نمی‌شود."""
    seen, why = set(), []
    def add(t):
        t = str(t or "").replace("⛔", "", 1).strip()
        t = t.splitlines()[0].strip() if t else ""
        if t and t[:60] not in seen: seen.add(t[:60]); why.append(t[:110])
    hard = list(g.get("hard") or [])
    for h in hard: add(h)
    for f in (g.get("flags") or []): add(f)
    if str(g.get("ceo_verdict") or "").upper() == "NO": add("مدیرعامل صریحاً رد کرد (NO)")
    if str(g.get("smc_verdict") or "").upper() == "NO": add("ایجنت ICT/SMC رد کرد (NO)")
    return max(0.0, 100.0 - len(why)), why, len(hard)

def _score_gate(g):
    if g.get("sl") is None: return "حد ضرر ندارد"
    g["_score100"] = _score100(g)
    return None

def _score_line(g):
    s = g.get("_score100")
    if not s: return ""
    sc, why, nh = s
    return "\n".join([f"امتیاز: {sc:g}/100 · {len(why)} پرچم" + (f" ({nh} سخت)" if nh else "")] + ["• " + w for w in why[:3]]) + "\n"

'''

REPS = [
    ("def _strict_reject(g):\n",
     BLOCK + "def _strict_reject(g):\n    if SCORE100: return _score_gate(g)\n    return _strict_reject_old(g)\n\ndef _strict_reject_old(g):\n"),
    ('f"گرید: {_grade} | مدیرعامل: {_ceo}\\n"',
     'f"گرید: {_grade} | مدیرعامل: {_ceo}\\n"\n                   f"{_score_line(g)}"'),
    ("if _FINAL_FALLBACK: ALL_FALLBACK = True; _final = True; continue",
     'if SCORE100 or globals().get("_FINAL_FALLBACK"): ALL_FALLBACK = True; _final = True; continue'),
]


def apply_engine(path="engine.py"):
    try:
        src = open(path, encoding="utf-8").read()
    except OSError as e:
        print(f"patch_score: {path} خوانده نشد ({type(e).__name__})؛ رد شد.")
        return False
    if MARK in src:
        print(f"patch_score: {path} از قبل اعمال شده است.")
        return True
    for old, new in REPS:
        if src.count(old) != 1:
            print(f"patch_score: لنگر دقیقاً یک‌بار پیدا نشد؛ فایل دست‌نخورده ماند: {old[:50]!r}")
            return False
        src = src.replace(old, new, 1)
    try:
        compile(src, path, "exec")
    except SyntaxError as e:
        print(f"patch_score: خطای نحو بعد از وصله ({e.msg})؛ نوشته نشد.")
        return False
    with open(path, "w", encoding="utf-8") as f:
        f.write(src + "\n" + MARK + "\n")
    print(f"patch_score: {path} وصله شد.")
    return True


if __name__ == "__main__":
    apply_engine(sys.argv[1] if len(sys.argv) > 1 else "engine.py")
