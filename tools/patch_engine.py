"""وصلهٔ زمان اجرا روی engine.py؛ فایل داخل مخزن دست‌نخورده می‌ماند و فقط نسخهٔ روی ماشین اجرا تغییر می‌کند.
سقف تماس مدیرعامل: تا TA_CEO_MAX_CALLS تماس در هر اجرا با TA_CEO_MODEL و بعد از آن با TA_CEO_FALLBACK_MODEL.
اگر متن موتور با انتظار نخواند، با خطا می‌ایستد تا اجرا با مدیرعامل اشتباه شروع نشود."""
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "engine.py"
MARK = "# [patch] ceo-call-cap v1"
ANCHOR = "import os, re, time, json, getpass, requests\n"
HELPER = MARK + '''
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
'''
OLD = ('        opus = os.environ.get("CLAUDE_OPUS_MODEL", "claude-opus-5-5").strip()\n'
       '        for k_, model in enumerate((opus, deep)):')
NEW = ('        opus = _ceo_model()\n'
       '        for k_, model in enumerate((opus, deep)):')


def main():
    src = open(PATH, encoding="utf-8").read()
    if MARK in src:
        print("patch_engine: از قبل اعمال شده است.")
        return 0
    if src.count(ANCHOR) != 1 or src.count(OLD) != 1:
        print(f"patch_engine: متن engine.py با انتظار نمی‌خواند (anchor={src.count(ANCHOR)}, ceo={src.count(OLD)}). اجرا متوقف شد.")
        return 1
    src = src.replace(ANCHOR, ANCHOR + HELPER, 1).replace(OLD, NEW, 1)
    compile(src, PATH, "exec")
    with open(PATH, "w", encoding="utf-8") as f:
        f.write(src)
    print("patch_engine: سقف تماس مدیرعامل اعمال شد.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
