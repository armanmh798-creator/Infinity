# -*- coding: utf-8 -*-
"""فاز پس از تصمیم تیم ۲۵ایجنت Infinity.

- ۲۱ اعلان‌ساز و ۲۲ ژورنال‌نویس: بعد از تصمیم مدیرعامل اجرا می‌شوند و فقط متن می‌سازند؛ تحلیل جدید نمی‌کنند.
- ۲۳ تا ۲۵ غربالگر ALL: ده دارایی را غربال می‌کنند و فقط یک نامزد برای تحلیل کامل برمی‌گردانند.

این فایل هنوز به run_desk در tools/desk25.py وصل نشده است.
تابع فراخوانی موتور (call_engine) از بیرون تزریق می‌شود تا نام توابع موجود حدس زده نشود.
هیچ متن پرامپت یا پاسخی در خلاصه ذخیره نمی‌شود؛ فقط زمان شروع و پایان ثبت می‌شود.
"""
import time

POST_AGENTS = (21, 22)
SCREEN_AGENTS = (23, 24, 25)


def _timed(name, fn, timings):
    t0 = time.time()
    try:
        return fn()
    finally:
        timings[name] = {"start": t0, "end": time.time()}


def run_post(decision, brief, call_engine, timings):
    """اجرای ۲۱ و ۲۲ پس از تصمیم نهایی. خروجی: {21: متن, 22: متن}."""
    out = {}
    for n in POST_AGENTS:
        out[n] = _timed(
            f"agent_{n}",
            lambda n=n: call_engine(n, {"decision": decision, "brief": brief}),
            timings,
        )
    return out


def run_screen(asset_briefs, call_engine, timings, max_candidates=1):
    """اجرای غربالگرهای ۲۳ تا ۲۵ روی ده دارایی. خروجی: فهرست نامزدها (حداکثر max_candidates)."""
    picks = []
    for n in SCREEN_AGENTS:
        picks.append(
            _timed(
                f"agent_{n}",
                lambda n=n: call_engine(n, {"assets": asset_briefs}),
                timings,
            )
        )
    # رأی‌گیری ساده: دارایی‌ای که بیشتر ایجنت‌ها انتخاب کرده‌اند
    votes = {}
    for p in picks:
        if isinstance(p, dict) and p.get("asset"):
            votes[p["asset"]] = votes.get(p["asset"], 0) + 1
    ranked = sorted(votes, key=votes.get, reverse=True)
    return ranked[:max_candidates]
