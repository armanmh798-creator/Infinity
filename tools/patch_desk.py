"""وصلهٔ تیم ۲۵ایجنت روی engine.py (بعد از tools/patch_engine.py اجرا می‌شود).
استفاده: python tools/patch_desk.py engine.py
یک تابع _desk_text به engine اضافه می‌کند و گزارش تیم را بعد از دیده‌بان X به پرامپت مدیرعامل می‌چسباند.
اگر متن engine.py با انتظار نخواند یا وصلهٔ قبلی اعمال نشده باشد، چیزی نمی‌نویسد و با خطا می‌ایستد."""
import sys

ENGINE = sys.argv[1] if len(sys.argv) > 1 else "engine.py"
MARK = "# [patch] desk25"
NEEDS = ("# [patch] infinity-1xai v3", "def _x_scout_text():", "def _budget_add(", "def _budget_cap(", "_BUDGET = {")
CALL_OLD = "        prompt += _x_scout_text()\n"
CALL_NEW = CALL_OLD + "        prompt += _desk_text(prompt)\n"
FUNC_ANCHOR = "def _x_scout_text():"
FUNC = MARK + '''
_DESK_CACHE = {"runs": 0, "by": {}}

def _desk_text(brief):
    """تیم ۲۵ایجنت (tools/desk25.py)؛ فقط مشاوره. هر خطا یعنی متن خالی و مدیرعامل بی‌تیم ادامه می‌دهد."""
    if os.environ.get("TA_DESK", "1") != "1": return ""
    a = str(globals().get("ASSET", "") or os.environ.get("TA_ASSET", ""))
    hit = _DESK_CACHE["by"].get(a)
    if hit and time.time() - hit[0] < 900: return hit[1]
    try: cap_runs = int(os.environ.get("TA_DESK_MAX_RUNS", "2") or 2)
    except ValueError: cap_runs = 2
    if _DESK_CACHE["runs"] >= cap_runs: return ""
    _DESK_CACHE["runs"] += 1
    text = ""
    try:
        import importlib.util
        base = os.path.dirname(os.path.abspath(globals().get("__file__") or "engine.py"))
        spec = importlib.util.spec_from_file_location("desk25", os.path.join(base, "tools", "desk25.py"))
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        text = mod.run_desk(str(brief), a, hooks={"add": _budget_add, "spent": lambda: _BUDGET["spent"], "cap": _budget_cap}) or ""
        print(f"تیم ایجنت‌ها · {a} · {'گزارش آماده شد' if text else 'گزارشی نیامد'}")
    except Exception as e:
        print(f"⚠ تیم ایجنت‌ها ناموفق بود: {type(e).__name__}: {str(e)[:120]}")
    _DESK_CACHE["by"][a] = (time.time(), text)
    return text

'''


def main():
    with open(ENGINE, encoding="utf-8") as f:
        src = f.read()
    if MARK in src:
        print("patch_desk: از قبل اعمال شده است.")
        return 0
    miss = [n for n in NEEDS if n not in src]
    if miss or src.count(CALL_OLD) != 1 or src.count(FUNC_ANCHOR) != 1:
        raise SystemExit(f"patch_desk: متن engine.py با انتظار نمی‌خواند {miss} call={src.count(CALL_OLD)}؛ چیزی نوشته نشد.")
    src = src.replace(FUNC_ANCHOR, FUNC + FUNC_ANCHOR, 1).replace(CALL_OLD, CALL_NEW, 1)
    compile(src, ENGINE, "exec")
    with open(ENGINE, "w", encoding="utf-8") as f:
        f.write(src)
    print("patch_desk: تیم ۲۵ایجنت به پرامپت مدیرعامل وصل شد.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
