"""شنوندهٔ فرمان تلگرام برای Infinity؛ هیچ تماس پولی با مدل‌ها ندارد.
هر بار اجرا پیام‌های تازهٔ ربات را می‌خواند و اگر مالک فرمان /run داده باشد، گردش‌کار ta.yml را راه می‌اندازد.
لاگ این مخزن عمومی است: توکن، شناسهٔ گفتگو و متن پیام‌ها هرگز چاپ نمی‌شوند."""
import json, os, sys, time, urllib.error, urllib.request

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
OWNER_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
GH_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
REPO = os.environ.get("GITHUB_REPOSITORY", "").strip()
WORKFLOW = os.environ.get("TA_WORKFLOW_FILE", "ta.yml")
REF = os.environ.get("TA_WORKFLOW_REF", "main")
MAX_AGE_SEC = int(os.environ.get("TA_CMD_MAX_AGE_SEC", "1800"))

MODES = {"vip": "VIP", "normal": "Normal", "نرمال": "Normal"}
ASSETS = {"gold": "Gold", "xau": "Gold", "xauusd": "Gold", "طلا": "Gold", "btc": "BTC", "eth": "ETH",
          "silver": "Silver", "نقره": "Silver", "all": "ALL", "همه": "ALL"}
MINUTES = ("15", "20", "30", "45", "60")
DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
HELP = ("فرمان‌ها:\n"
        "/run ← اجرای Normal روی Gold تا ۶۰ دقیقه\n"
        "/run vip gold 30 ← حالت، دارایی و دقیقهٔ دلخواه\n"
        "حالت: normal یا vip\n"
        "دارایی: gold، btc، eth، silver، all\n"
        "دقیقه: 15، 20، 30، 45، 60\n"
        "فرمان هر چند دقیقه یک بار خوانده می‌شود.")


def _http(url, payload=None, headers=None, timeout=20):
    """(status, body)؛ در خطا نشانی درخواست چاپ یا برگردانده نمی‌شود، چون توکن داخل آن است."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    hdr = dict(headers or {})
    if data is not None: hdr["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdr)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


def tg(method, payload=None):
    status, body = _http("https://api.telegram.org/bot" + TOKEN + "/" + method, payload or {})
    if status != 200: return None, status
    try: j = json.loads(body)
    except ValueError: return None, status
    return (j.get("result") if j.get("ok") else None), status


def say(chat_id, text):
    tg("sendMessage", {"chat_id": chat_id, "text": text})


def parse(text):
    """(inputs, bad)؛ پیام غیر از /run هر دو None. فرمان مبهم اجرا نمی‌شود و واژهٔ ناشناخته در bad برمی‌گردد."""
    parts = text.translate(DIGITS).strip().split()
    if not parts or parts[0].split("@")[0].lower() != "/run": return None, None
    mode, asset, minutes = "Normal", "Gold", "60"
    for p in parts[1:]:
        k = p.lower()
        if k in MODES: mode = MODES[k]
        elif k in ASSETS: asset = ASSETS[k]
        elif k in MINUTES: minutes = k
        else: return None, p
    return {"mode": mode, "asset": asset, "search_min": minutes}, None


def main():
    if not TOKEN:
        print("TELEGRAM_BOT_TOKEN تنظیم نشده؛ کاری انجام نشد."); return 0
    updates, status = tg("getUpdates", {"timeout": 0, "allowed_updates": ["message"]})
    if updates is None:
        print(f"::warning::خواندن پیام‌های تلگرام ناموفق بود (HTTP {status})."); return 0
    if not updates:
        print("پیام تازه‌ای نیست."); return 0
    # اول دریافت پیام‌ها تأیید می‌شود تا یک فرمان هرگز دو بار اجرا نشود.
    last_id = max(int(u.get("update_id", 0)) for u in updates)
    acked, status = tg("getUpdates", {"offset": last_id + 1, "timeout": 0, "limit": 1, "allowed_updates": ["message"]})
    if acked is None:
        print(f"::warning::تأیید دریافت پیام‌ها ناموفق بود (HTTP {status})؛ فرمانی اجرا نشد."); return 0
    now, chosen, senders = time.time(), None, []
    for u in updates:
        m = u.get("message") or {}
        chat, text = str((m.get("chat") or {}).get("id", "")), str(m.get("text") or "")
        if not chat or not text: continue
        if not OWNER_CHAT:
            if chat not in senders: senders.append(chat)
            continue
        if chat != OWNER_CHAT: continue
        if now - float(m.get("date", 0) or 0) > MAX_AGE_SEC: continue
        chosen = (chat, text)      # فقط آخرین پیام مالک
    if not OWNER_CHAT:
        for chat in senders[:3]:
            say(chat, "ربات هنوز به مالک وصل نیست و فرمانی اجرا نمی‌کند.\nشناسهٔ این گفتگو: " + chat
                + "\nمالک باید آن را در GitHub ← Settings ← Secrets and variables ← Actions با نام TELEGRAM_CHAT_ID ذخیره کند.")
        print("TELEGRAM_CHAT_ID تنظیم نشده؛ هیچ فرمانی اجرا نشد."); return 0
    if not chosen:
        print("فرمان تازه‌ای از مالک نیست."); return 0
    chat, text = chosen
    inputs, bad = parse(text)
    if inputs is None:
        say(chat, HELP if bad is None else "«" + bad + "» را نشناختم؛ چیزی اجرا نشد.\n\n" + HELP)
        print("پیام مالک فرمان اجرا نبود."); return 0
    status, _ = _http(f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}/dispatches",
                      {"ref": REF, "inputs": inputs},
                      {"Authorization": "Bearer " + GH_TOKEN, "Accept": "application/vnd.github+json",
                       "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "infinity-telegram-listener"})
    if status == 204:
        say(chat, f"اجرا شروع شد ✅\nحالت: {inputs['mode']}\nدارایی: {inputs['asset']}\nحداکثر جست‌وجو: {inputs['search_min']} دقیقه")
        print("یک اجرا راه‌اندازی شد."); return 0
    say(chat, f"شروع اجرا ناموفق بود (GitHub HTTP {status}). چیزی اجرا نشد.")
    print(f"::warning::راه‌اندازی اجرا ناموفق بود (GitHub HTTP {status})."); return 0


if __name__ == "__main__":
    sys.exit(main())
