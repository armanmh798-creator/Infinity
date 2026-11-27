# -*- coding: utf-8 -*-
"""بررسی اتصال موتورهای تیم قبل از اجرا (در GitHub Actions، با کلید ONE_XAI_API_KEY).
- فهرست مدل‌های حساب را از درگاه می‌گیرد (اگر در دسترس باشد) و با موتورهای تیم مقایسه می‌کند.
- هر موتور را با یک تماس بسیار کوچک (حداکثر ۱۶ توکن خروجی) امتحان می‌کند؛ هزینهٔ کل چند صد تومان.
- نتیجه در data/engine_check.json و پیام تلگرام. متن پاسخ مدل‌ها و کلید هرگز چاپ یا ارسال نمی‌شود.
- اگر موتوری نبود و نام مشابهی در فهرست حساب بود، فقط پیشنهاد می‌دهد (TA_MODEL_MAP)؛ خودش چیزی را عوض نمی‌کند.
استفاده: python tools/check_engines.py   (TA_CHECK=0 برای رد شدن)
"""
import os, sys, json, time, urllib.request, urllib.parse
import concurrent.futures as cf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import desk25  # noqa: E402

DATA = os.environ.get("TA_DATA") or "data"
RUN = os.environ.get("GITHUB_RUN_ID", "")


def team_models():
    s = set()
    for a in desk25.AGENTS:
        for m in a["models"].values():
            s.add(m)
        for m in a["fb"]:
            s.add(m)
    s.update([desk25.OP, desk25.SO, desk25.HA, desk25.FA, desk25.MY, desk25.GK])
    return sorted(s)


def list_account_models():
    """فهرست مدل‌های حساب؛ اگر درگاه این مسیر را نداشته باشد None."""
    import requests
    base = os.environ.get("ONE_XAI_BASE_URL", "https://1xai.ir").rstrip("/")
    key = os.environ.get("ONE_XAI_API_KEY", "").strip()
    try:
        r = requests.get(base + "/v1/models", headers={"Authorization": "Bearer " + key}, timeout=20)
        if r.status_code != 200:
            return None
        j = r.json()
        items = j.get("data") if isinstance(j, dict) else j
        return {str(x.get("id")) for x in (items or []) if isinstance(x, dict) and x.get("id")}
    except Exception:
        return None


def probe(model, http=None):
    http = http or desk25._http_call
    msgs = [{"role": "user", "content": "Reply with the single word OK."}]
    t0 = time.time()
    try:
        text, u = http(desk25._alias(model), msgs, 16, 40)
        ok = bool(str(text).strip())
        tin = int(u.get("prompt_tokens", u.get("input_tokens", 0)) or 0)
        tout = int(u.get("completion_tokens", u.get("output_tokens", 0)) or 0)
        return {"model": model, "ok": ok, "err": "" if ok else "empty", "sec": round(time.time() - t0, 1),
                "toman": round(desk25.est_toman(model, tin, tout))}
    except Exception as e:
        return {"model": model, "ok": False, "err": str(e)[:40], "sec": round(time.time() - t0, 1), "toman": 0}


def suggest(model, avail):
    """نام مشابه در فهرست حساب (بر پایهٔ پیشوند خانواده)؛ فقط پیشنهاد."""
    fam = model.split("-")[0].lower()
    return sorted(x for x in (avail or []) if x.lower().startswith(fam))[:4]


def build(res, avail):
    good = [r for r in res if r["ok"]]
    bad = [r for r in res if not r["ok"]]
    L = [f"Infinity · بررسی موتورها · {len(good)} از {len(res)} سالم"]
    if good:
        L.append("✓ " + " · ".join(f"{r['model']} ({r['sec']}s)" for r in good))
    for r in bad:
        s = suggest(r["model"], avail)
        L.append(f"✗ {r['model']}: {r['err']}" + (f" ← نام‌های نزدیک در حساب: {', '.join(s)}" if s else ""))
    if avail is None:
        L.append("فهرست مدل‌های حساب از درگاه خوانده نشد؛ فقط نتیجهٔ تماس‌های آزمایشی بالا معتبر است.")
    L.append("هزینهٔ این بررسی (برآورد): %d تومان" % sum(r["toman"] for r in res))
    if bad:
        L.append("موتور ناسالم در تیم خودکار به جایگزین می‌رود؛ اگر نام در حساب فرق دارد TA_MODEL_MAP را تنظیم کنید.")
    return "\n".join(L)[:3800]


def send_tg(msg):
    tok = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not tok or not chat:
        print("check_engines: توکن یا چت‌آیدی تنظیم نیست؛ پیش‌نمایش:\n" + msg)
        return
    try:
        data = urllib.parse.urlencode({"chat_id": chat, "text": msg, "disable_web_page_preview": "true"}).encode()
        urllib.request.urlopen(urllib.request.Request("https://api.telegram.org/bot" + tok + "/sendMessage", data=data), timeout=20).read()
        print("check_engines: گزارش به تلگرام رفت.")
    except Exception as e:
        print(f"check_engines: ارسال تلگرام ناموفق ({type(e).__name__} {getattr(e, 'code', '')})")  # بدون چاپ آدرس چون توکن دارد
        print(msg)


def main(http=None, avail=None, send=True):
    if os.environ.get("TA_CHECK", "1") != "1":
        print("check_engines: TA_CHECK=0؛ رد شد.")
        return 0
    if not os.environ.get("ONE_XAI_API_KEY", "").strip() and http is None:
        print("check_engines: ONE_XAI_API_KEY خالی است.")
        return 1
    avail = avail if avail is not None else (list_account_models() if http is None else None)
    models = team_models()
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(lambda m: probe(m, http), models))
    res.sort(key=lambda r: (r["ok"], r["model"]))
    try:
        os.makedirs(DATA, exist_ok=True)
        with open(os.path.join(DATA, "engine_check.json"), "w", encoding="utf-8") as f:
            json.dump({"run_id": RUN, "results": res, "listed": sorted(avail) if avail else None}, f, ensure_ascii=False)
    except Exception:
        pass
    msg = build(res, avail)
    print(msg)
    if send:
        send_tg(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
