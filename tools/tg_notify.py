# -*- coding: utf-8 -*-
"""اعلان تلگرام بعد از هر اجرا: وضعیت اتصال موتورها و هزینه. متن پرامپت و پاسخ ایجنت‌ها هرگز فرستاده نمی‌شود.
توکن فقط از متغیر محیطی خوانده می‌شود و هیچ‌جا چاپ نمی‌شود. بدون توکن/چت‌آیدی فقط متن را چاپ می‌کند (dry-run).
استفاده: python tools/tg_notify.py   (بعد از مرحلهٔ اجرا، با if: always())
"""
import os, json, collections, urllib.request, urllib.parse

DATA = os.environ.get("TA_DATA") or "data"
RUN = os.environ.get("GITHUB_RUN_ID", "")


def _load(name):
    try:
        d = json.load(open(os.path.join(DATA, name), encoding="utf-8"))
        return d if (not RUN or d.get("run_id") == RUN) else None
    except Exception:
        return None


def build():
    st = {"success": "تمام شد", "failure": "با خطا تمام شد", "cancelled": "لغو شد"}.get(os.environ.get("JOB_STATUS", ""), "نامشخص")
    mode, asset = os.environ.get("RUN_MODE", ""), os.environ.get("RUN_ASSET", "")
    L = [f"Infinity · {mode} · {asset} · {st}"]
    desk, cost = _load("desk_summary.json"), _load("cost_summary.json")
    if os.environ.get("DESK_PATCHED") == "0":
        L.append("⚠ تیم ۲۵ایجنت به موتور وصل نشد (وصله اعمال نشد)؛ اجرا با موتور قبلی انجام شد.")
    if desk:
        ags = [a for a in desk.get("agents", []) if a.get("status") != "skipped" or a.get("served")]
        ok = [a for a in ags if a.get("status") == "ok"]
        fb = [a for a in ags if a.get("status") == "fallback"]
        bad = [a for a in ags if a.get("status") not in ("ok", "fallback")]
        L.append(f"تیم: {len(ok)} موتور اصلی ✓ · {len(fb)} جایگزین · {len(bad)} ناموفق/بودجه")
        t = desk.get("tally", {})
        L.append(f"رأی‌ها: GO {t.get('GO', 0)} · WAIT {t.get('WAIT', 0)} · NO {t.get('NO', 0)} · {desk.get('seconds', 0)} ثانیه")
        per = collections.defaultdict(lambda: [0, 0])
        for a in ags:
            m = a.get("planned") or "?"
            per[m][0] += 1
            if a.get("status") == "ok":
                per[m][1] += 1
        L.append("اتصال موتورها (سالم/کل): " + " · ".join(f"{m} {v[1]}/{v[0]}" for m, v in sorted(per.items())))
        errs = collections.Counter(str(a.get("status"))[:24] for a in bad)
        if errs:
            L.append("خطاها: " + " · ".join(f"{k}×{n}" for k, n in errs.most_common(4)))
    elif os.environ.get("DESK_PATCHED") != "0":
        L.append("گزارش تیم برای این اجرا ثبت نشد.")
    if cost:
        try:
            L.append(f"هزینه (برآورد): {int(cost['spent_toman']):,} از سقف {int(cost['cap_toman']):,} تومان · {cost.get('calls', 0)} تماس"
                     + (" · ⛔ سقف پر شد" if cost.get("stopped_by_cap") else ""))
        except Exception:
            L.append("خلاصهٔ هزینه خوانده نشد.")
    else:
        L.append("هیچ تماس پولی ثبت نشد.")
    L.append("برآورد با قیمت لیست؛ مبلغ نهایی در صفحهٔ مصرف 1xAi.")
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
        print(f"tg_notify: ارسال ناموفق ({type(e).__name__} {code})")  # بدون چاپ آدرس چون توکن دارد
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
