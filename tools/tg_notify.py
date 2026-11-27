# -*- coding: utf-8 -*-
"""اعلان تلگرام فارسی بعد از هر اجرا: وضعیت موتورها، فعالیت سلاطین، نظر مدیرعامل، هزینه و دلیل واقعی نتیجه.
متن پرامپت و پاسخ کامل ایجنت‌ها هرگز فرستاده نمی‌شود؛ فقط برچسب رأی، درصد اطمینان و موتور.
این گزارش فقط به TELEGRAM_CHAT_ID مالک می‌رود و برای مشتری نیست.
توکن فقط از متغیر محیطی خوانده می‌شود و هیچ‌جا چاپ نمی‌شود. بدون توکن/چت‌آیدی فقط پیش‌نمایش چاپ می‌شود.
استفاده: python tools/tg_notify.py   (بعد از مرحلهٔ اجرا، با if: always())
"""
import os, json, collections, urllib.request, urllib.parse

DATA = os.environ.get("TA_DATA") or "data"
RUN = os.environ.get("GITHUB_RUN_ID", "")
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
SOV_IDS = (2, 3, 4, 5, 6)

VERDICT_FA = {"GO": "✅ ورود", "WAIT": "⏳ صبر", "NO": "⛔ رد", "NA": "➖ بدون نظر"}
STATUS_ICON = {"ok": "✅", "fallback": "🔁", "empty": "🫥", "budget": "💸", "timeout": "⏰", "skipped": "⏭"}
RUN_STATUS_FA = {"success": "🟢 تمام شد", "failure": "🔴 با خطا تمام شد", "cancelled": "🟡 لغو شد"}


def fa(x):
    return str(x).translate(FA_DIGITS)


def _load(name):
    try:
        d = json.load(open(os.path.join(DATA, name), encoding="utf-8"))
        return d if (not RUN or d.get("run_id") == RUN) else None
    except Exception:
        return None


def _files_diag():
    """وضعیت فایل‌های گزارش: وجود دارند؟ مال همین اجرا هستند؟ (بدون محتوا)"""
    try:
        names = sorted(os.listdir(DATA))
    except Exception:
        return ["📂 پوشهٔ داده پیدا نشد؛ مسیر TA_DATA را در workflow بررسی کنید."]
    out = ["📂 وضعیت فایل‌های گزارش:"]
    for name in ("desk_summary.json", "cost_summary.json"):
        if name not in names:
            out.append(f"  • {name}: فایل وجود ندارد (احتمالاً این مرحله اجرا نشده یا قبل از ساخت فایل متوقف شده)")
            continue
        try:
            rid = json.load(open(os.path.join(DATA, name), encoding="utf-8")).get("run_id")
        except Exception:
            out.append(f"  • {name}: فایل هست ولی خوانده نشد (JSON خراب)")
            continue
        if RUN and str(rid) != str(RUN):
            out.append(f"  • {name}: مال اجرای دیگری است ({rid}) و برای این اجرا استفاده نشد")
        else:
            out.append(f"  • {name}: ✅ مال همین اجرا")
    return out


def _conf(a):
    c = a.get("conf")
    return (fa(c) + "٪") if c is not None else "—"


def _icon(status):
    if status in STATUS_ICON:
        return STATUS_ICON[status]
    return "❌" if str(status).startswith("err") else "❔"


def _agent_line(a):
    verdict = VERDICT_FA.get(a.get("verdict"), "➖ بدون نظر")
    served = a.get("served") or a.get("planned") or "—"
    s, e = a.get("start"), a.get("end")
    dur = ""
    if isinstance(s, (int, float)) and isinstance(e, (int, float)):
        dur = " · " + fa(round(e - s)) + " ثانیه"
    return f"{_icon(a.get('status'))} {a.get('name', '؟')}: {verdict} · اطمینان {_conf(a)} · {served}{dur}"


def _diagnosis(desk, cost):
    """دلیل واقعی نتیجه را از داده‌ها می‌خواند؛ دلیل بازاری یا توجیه ساختگی نمی‌نویسد."""
    reasons = []
    if os.environ.get("JOB_STATUS") == "failure":
        reasons.append("اجرا با خطا تمام شد؛ برای جزئیات، لاگ Actions را ببینید.")
    if os.environ.get("DESK_PATCHED") == "0":
        reasons.append("وصل‌شدن تیم ۲۵ایجنت ناموفق بود؛ اجرا با موتور قبلی انجام شد.")
    calls = int(cost.get("calls", 0) or 0) if cost else 0
    if not cost or calls == 0:
        reasons.append("هیچ تماس پولی انجام نشد؛ موتورها عملاً اجرا نشده‌اند.")
    if desk is None and os.environ.get("DESK_PATCHED") != "0":
        reasons.append("گزارش تیم برای این اجرا در دسترس نیست (فایل desk_summary.json بالا را ببینید).")
    if desk:
        agents = desk.get("agents", [])
        if agents and not any(a.get("status") in ("ok", "fallback") for a in agents):
            reasons.append("هیچ موتوری پاسخ قابل‌استفاده نداد؛ اتصال API یا کلید 1xAi را بررسی کنید.")
    if cost and cost.get("stopped_by_cap"):
        reasons.append("سقف هزینهٔ اجرا پر شد و اجرا زودتر متوقف شد.")
    if not reasons:
        reasons.append("اجرا کامل بود؛ سیگنالی صادر نشد. جزئیات گیت کیفیت در لاگ موجود است.")
    return ["🔎 دلیل واقعی نتیجه:"] + ["  • " + r for r in reasons]


def build():
    L = [f"🤖 Infinity · {os.environ.get('RUN_ASSET', '') or '—'} · {os.environ.get('RUN_MODE', '') or '—'}",
         RUN_STATUS_FA.get(os.environ.get("JOB_STATUS", ""), "⚪️ وضعیت نامشخص"),
         ""]
    if os.environ.get("DESK_PATCHED") == "0":
        L += ["⚠️ تیم ۲۵ایجنت به موتور وصل نشد؛ اجرا با موتور قبلی انجام شد.", ""]

    desk, cost = _load("desk_summary.json"), _load("cost_summary.json")
    if desk:
        agents = desk.get("agents", [])
        active = [a for a in agents if a.get("status") != "skipped" or a.get("served")]
        ok = sum(1 for a in active if a.get("status") == "ok")
        fb = sum(1 for a in active if a.get("status") == "fallback")
        bad = [a for a in active if a.get("status") not in ("ok", "fallback")]
        t = desk.get("tally", {})
        L.append(f"👥 تیم: {fa(ok)} موتور اصلی ✅ · {fa(fb)} جایگزین 🔁 · {fa(len(bad))} ناموفق")
        L.append(f"🗳 رأی‌ها: {fa(t.get('GO', 0))} ورود · {fa(t.get('WAIT', 0))} صبر · {fa(t.get('NO', 0))} رد")
        if desk.get("seconds") is not None:
            L.append(f"⏱ مدت تیم: {fa(int(desk['seconds']))} ثانیه")
        chief = [a for a in agents if a.get("id") == 1]
        if chief:
            c = chief[-1]
            L.append(f"🎖 نظر مدیرعامل: {VERDICT_FA.get(c.get('verdict'), '➖ بدون نظر')} · اطمینان {_conf(c)}")

        L += ["", "🦁 فعالیت سلاطین پنج‌گانه:"]
        for a in sorted(agents, key=lambda x: x.get("id", 0)):
            if a.get("id") in SOV_IDS:
                L.append(_agent_line(a))

        if bad:
            L += ["", "⚠️ ناموفق یا بی‌پاسخ:"]
            for a in bad[:5]:
                L.append(f"  {_icon(a.get('status'))} {a.get('name', '؟')} ({a.get('status', '—')})")
    elif os.environ.get("DESK_PATCHED") != "0":
        L.append("📭 گزارش تیم برای این اجرا ثبت نشد.")

    L.append("")
    if cost:
        try:
            spent = fa(f"{int(cost['spent_toman']):,}")
            cap = fa(f"{int(cost['cap_toman']):,}")
            calls = fa(cost.get("calls", 0))
            line = f"💰 هزینه (برآورد): {spent} از {cap} تومان · {calls} تماس"
            if cost.get("stopped_by_cap"):
                line += " · ⛔ سقف پر شد"
            L.append(line)
        except Exception:
            L.append("💰 خلاصهٔ هزینه خوانده نشد.")
    else:
        L.append("💰 هیچ تماس پولی ثبت نشد.")
    L.append("ℹ️ برآورد با قیمت لیست؛ مبلغ نهایی در صفحهٔ مصرف 1xAi.")
    L.append("")
    # اگر گزارش تیم یا هزینه مال این اجرا نبود، دقیقاً نشان داده شود کدام فایل مشکل دارد
    if desk is None or cost is None:
        L += _files_diag() + [""]
    L += _diagnosis(desk, cost)
    return "\n".join(L)[:3800]


def main():
    msg = build()
    tok = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not tok or not chat:
        print("tg_notify: توکن یا چت‌آیدی تنظیم نیست؛ فقط پیش‌نمایش:\n" + msg)
        return 0
    try:
        data = urllib.parse.urlencode({"chat_id": chat, "text": msg, "disable_web_page_preview": "true"}).encode()
        req = urllib.request.Request("https://api.telegram.org/bot" + tok + "/sendMessage", data=data)
        urllib.request.urlopen(req, timeout=20).read()
        print("tg_notify: پیام به تلگرام ارسال شد.")
    except Exception as e:
        code = getattr(e, "code", "")
        print(f"tg_notify: ارسال ناموفق ({type(e).__name__} {code})")  # بدون چاپ آدرس، چون توکن در آن است
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
