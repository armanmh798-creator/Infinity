# -*- coding: utf-8 -*-
"""شنوندهٔ فرمان تلگرام برای Infinity؛ هیچ تماس پولی با مدل‌ها ندارد.
هر بار اجرا پیام‌های تازهٔ ربات را می‌خواند و اگر مالک فرمان /run داده باشد، ta.yml را روی TA_WORKFLOW_REF راه می‌اندازد.
پیام‌ها بعد از خوانده‌شدن با offset تأیید می‌شوند تا هر فرمان یک‌بار اجرا شود.
لاگ این مخزن عمومی است: توکن، شناسهٔ گفتگو و متن پیام‌ها هرگز چاپ نمی‌شوند."""
import json, os, sys, time, urllib.error, urllib.parse, urllib.request

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
OWNER_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
GH_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
REPO = os.environ.get("GITHUB_REPOSITORY", "").strip()
WORKFLOW = os.environ.get("TA_WORKFLOW_FILE", "ta.yml").strip() or "ta.yml"
REF = os.environ.get("TA_WORKFLOW_REF", "main").strip() or "main"
MAX_AGE_SEC = int(os.environ.get("TA_CMD_MAX_AGE_SEC", "1800"))

# حالت = ورودی mode در ta.yml
MODES = {"normal": "Normal", "نرمال": "Normal",
         "vip": "VIP", "ویآیپی": "VIP",
         "gold": "Gold", "گلد": "Gold",
         "eco": "Eco", "اکو": "Eco"}
# دارایی = ورودی asset در ta.yml (فقط گزینه‌های موجود روی main)
ASSETS = {"gold": "Gold", "xau": "Gold", "xauusd": "Gold", "طلا": "Gold",
          "all": "ALL", "همه": "ALL", "nas100": "NAS100", "eurusd": "EURUSD",
          "gbpusd": "GBPUSD", "btc": "BTC", "eth": "ETH", "doge": "DOGE",
          "xrp": "XRP", "ada": "ADA", "sol": "SOL", "trx": "TRX"}
MINUTES = ("15", "20", "30", "45", "60")
DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
HELP = ("فرمان‌ها:\n"
        "/run ← حالت Normal روی Gold تا ۶۰ دقیقه\n"
        "/run vip gold 30 ← حالت، دارایی و دقیقهٔ دلخواه\n"
        "حالت: normal، vip، gold، eco (یا نرمال، گلد، اکو، وی‌آی‌پی)\n"
        "دارایی: gold، btc، eth، all، nas100، eurusd، gbpusd، doge، xrp، ada، sol، trx\n"
        "دقیقه: 15، 20، 30، 45، 60")


def norm(s):
    return s.translate(DIGITS).replace("\u200c", "").replace("ي", "ی").replace("ك", "ک").strip().lower()


def _http(url, payload=None, headers=None, timeout=20):
    """(status, body)؛ در خطا نشانی درخواست چاپ نمی‌شود، چون توکن داخل آن است."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    hdr = dict(headers or {})
    if data is not None:
        hdr["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdr)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


def tg(method, params=None):
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    _, body = _http(url)
    try:
        return json.loads(body) if body else {}
    except ValueError:
        return {}


def send(text):
    tg("sendMessage", {"chat_id": OWNER_CHAT, "text": text})


def parse(args):
    mode = asset = mins = None
    for raw in args:
        t = norm(raw)
        if t in MODES and mode is None:
            mode = MODES[t]
        elif t in ASSETS and asset is None:
            asset = ASSETS[t]
        elif t in MINUTES and mins is None:
            mins = t
        else:
            return None, f"ناشناخته یا تکراری: {raw}"
    return (mode or "Normal", asset or "Gold", mins or "60"), None


def dispatch(mode, asset, mins):
    url = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}/dispatches"
    headers = {"Authorization": f"Bearer {GH_TOKEN}",
               "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    status, _ = _http(url, {"ref": REF, "inputs": {"mode": mode, "asset": asset, "search_min": mins}}, headers)
    return status


def main():
    if not (TOKEN and OWNER_CHAT and GH_TOKEN and REPO):
        print("متغیرهای لازم تنظیم نشده‌اند.")
        return 0
    data = tg("getUpdates", {"timeout": 0, "limit": 100})
    updates = data.get("result", []) if data.get("ok") else []
    if not updates:
        print("پیام تازه‌ای نیست.")
        return 0

    now = int(time.time())
    last_id = max(u["update_id"] for u in updates)
    run_args = None
    for u in updates:
        msg = u.get("message") or {}
        if str((msg.get("chat") or {}).get("id")) != OWNER_CHAT:
            continue
        text = (msg.get("text") or "").strip()
        if not text.startswith("/"):
            continue
        if now - int(msg.get("date", 0)) > MAX_AGE_SEC:
            continue
        parts = text.split()
        cmd = parts[0].split("@")[0].lower()
        if cmd == "/run":
            run_args = parts[1:]
        elif cmd in ("/help", "/start"):
            send(HELP)

    if run_args is not None:
        cfg, err = parse(run_args)
        if err:
            send(err + "\n\n" + HELP)
        else:
            mode, asset, mins = cfg
            status = dispatch(mode, asset, mins)
            if status == 204:
                send(f"✅ اجرا شد: حالت {mode} · دارایی {asset} · تا {mins} دقیقه\nشروع در GitHub Actions و گزارش بعد از پایان.")
            else:
                send(f"❌ اجرا ثبت نشد (کد {status}). دسترسی توکن یا نام شاخه را بررسی کنید.")

    # تأیید همهٔ پیام‌های خوانده‌شده تا دوباره اجرا نشوند
    tg("getUpdates", {"offset": last_id + 1, "limit": 1})
    return 0


if __name__ == "__main__":
    sys.exit(main())
