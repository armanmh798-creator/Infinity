# -*- coding: utf-8 -*-
"""وصلهٔ تیم سه‌نفره و ALL جداگانه (بعد از patch_desk.py اجرا می‌شود).
استفاده: python tools/patch_team3.py tools/desk25.py engine.py
1) سلاطین: Al Brooks، Larry Williams، Richard Wyckoff می‌مانند؛ Jake Bernstein و Linda Raschke خاموش می‌شوند.
2) دارایی ALLCRYPTO و ALLFOREX: دامنهٔ اسکن ALL را روی همان گروه می‌گذارد.
اگر هر لنگر پیدا نشود، آن فایل دست‌نخورده می‌ماند و اجرا ادامه می‌دهد (هشدار چاپ می‌شود)."""
import sys

DESK = sys.argv[1] if len(sys.argv) > 1 else "tools/desk25.py"
ENGINE = sys.argv[2] if len(sys.argv) > 2 else "engine.py"
MARK = "# [patch] team3"

DESK_REPS = [
    ("SOVEREIGN_IDS = (2, 3, 4, 5, 6)", "SOVEREIGN_IDS = (2, 3, 5)"),
    ('"سلاطین · سیکل و فصلی", "pre"', '"سلاطین · سیکل و فصلی", "off"'),
    ('"سلاطین · مومنتوم و شکست", "pre"', '"سلاطین · مومنتوم و شکست", "off"'),
    ("one of the five sovereigns", "one of the three sovereigns"),
    ("specialists 2-6 are the five sovereigns", "specialists 2, 3 and 5 are the three sovereigns"),
]
ENGINE_REPS = [(
    'ALL_ASSETS = ["Gold", "BTC", "ETH"]',
    'ALL_ASSETS = ["Gold", "BTC", "ETH"]\n'
    '_ALLGRP = {"ALLCRYPTO": ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "TRX"], "ALLFOREX": ["EURUSD", "GBPUSD", "Gold"]}\n'
    '_g_ = str(ASSET).upper().replace("-", "").replace("_", "").replace(" ", "")\n'
    'if _g_ in _ALLGRP: ALL_ASSETS = list(_ALLGRP[_g_]); ASSET = "ALL"\n'
    '#'),
]


def apply(path, reps):
    try:
        src = open(path, encoding="utf-8").read()
    except OSError as e:
        print(f"patch_team3: {path} خوانده نشد ({type(e).__name__})؛ رد شد.")
        return False
    if MARK in src:
        print(f"patch_team3: {path} از قبل اعمال شده است.")
        return True
    for old, new in reps:
        if src.count(old) != 1:
            print(f"patch_team3: لنگر در {path} پیدا نشد؛ فایل دست‌نخورده ماند: {old[:50]}")
            return False
        src = src.replace(old, new, 1)
    try:
        compile(src, path, "exec")
    except SyntaxError as e:
        print(f"patch_team3: خطای نحو بعد از وصله در {path} ({e.msg})؛ نوشته نشد.")
        return False
    with open(path, "w", encoding="utf-8") as f:
        f.write(src + "\n" + MARK + "\n")
    print(f"patch_team3: {path} وصله شد.")
    return True


if __name__ == "__main__":
    apply(DESK, DESK_REPS)
    apply(ENGINE, ENGINE_REPS)
