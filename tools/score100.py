# -*- coding: utf-8 -*-
"""امتیازدهی ۱۰۰تایی سیگنال Infinity.

قاعده:
- هر سیگنال از ۱۰۰ شروع می‌کند.
- پرچم قرمزِ مستدل که هیچ عضوی با آن مخالف نیست: ۱ امتیاز کم می‌کند.
- پرچم قرمزِ مستدل که حداقل یک عضو با آن مخالف است: ۰٫۵ امتیاز.
- پرچم بدون استدلال: کسری ندارد (فقط در فهرست می‌آید).
- فقط «شرط‌های سخت» سیگنال را متوقف می‌کنند: نبود حد ضرر، داده کهنه، بازار بسته، ریوارد زیر حداقل.
نمرهٔ ارسالی همیشه نمرهٔ واقعی است؛ دستکاری نمی‌شود.
"""
FULL, PARTIAL = 1.0, 0.5
TIERS = ((85, "عادی"), (60, "متوسط"), (0, "ریسک بالا"))


def hard_block(sig):
    """sig: dict با کلیدهای sl, rr, min_rr, data_stale, market_closed. خروجی: متن دلیل یا None."""
    if sig.get("sl") is None:
        return "حد ضرر ندارد"
    if sig.get("data_stale"):
        return "داده کهنه است"
    if sig.get("market_closed"):
        return "بازار بسته است"
    if sig.get("rr") is not None and sig["rr"] < sig.get("min_rr", 3.0):
        return "ریوارد کمتر از حداقل است"
    return None


def score_signal(flags):
    """flags: فهرست dict با کلیدهای name, red (bool), reason (str), contested (bool)."""
    s, rows = 100.0, []
    for f in flags or []:
        cut = 0.0
        if f.get("red") and str(f.get("reason", "")).strip():
            cut = PARTIAL if f.get("contested") else FULL
        s -= cut
        rows.append((f.get("name", "?"), cut))
    return round(max(s, 0.0), 1), rows


def tier_of(score):
    return next(t for lo, t in TIERS if score >= lo)


def decide(sig, flags):
    """خروجی: dict(send, score, tier, flags, blocked). send=False فقط با شرط سخت."""
    why = hard_block(sig)
    sc, rows = score_signal(flags)
    return {"send": why is None, "score": sc, "tier": tier_of(sc), "flags": rows, "blocked": why}


if __name__ == "__main__":
    ok = {"sl": 1.0, "rr": 3.2, "min_rr": 3.0}
    f = [{"name": "a", "red": True, "reason": "x", "contested": False},
         {"name": "b", "red": True, "reason": "y", "contested": True},
         {"name": "c", "red": True, "reason": "", "contested": False},
         {"name": "d", "red": False, "reason": "z"}]
    r = decide(ok, f)
    assert r["score"] == 98.5 and r["send"] and r["tier"] == "عادی", r
    assert decide({**ok, "sl": None}, [])["send"] is False
    assert decide({**ok, "data_stale": True}, [])["blocked"] == "داده کهنه است"
    assert decide(ok, [{"name": str(i), "red": True, "reason": "r"} for i in range(50)])["tier"] == "ریسک بالا"
    print("score100 OK")
