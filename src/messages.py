"""Bengali Telegram messages (HTML parse mode)."""
from __future__ import annotations

import pandas as pd

from .risk import ICON, NAMES

_DIG = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")


def bn(x) -> str:
    return str(x).translate(_DIG)


def mm(v: float) -> str:
    return bn(f"{v:.0f}") + " মিমি"


def when(t: pd.Timestamp, now: pd.Timestamp) -> str:
    if t is None:
        return "–"
    d = (t.normalize() - now.normalize()).days
    day = {0: "আজ", 1: "আগামীকাল", 2: "পরশু"}.get(d, bn(t.strftime("%d/%m")))
    h = t.hour
    part = ("রাত" if h < 4 else "ভোর" if h < 6 else "সকাল" if h < 12 else "দুপুর" if h < 15 else "বিকেল" if h < 18
            else "সন্ধ্যা" if h < 20 else "রাত")
    h12 = h % 12 or 12
    return f"{day} {part} {bn(h12)}টা"


TIPS = {3: "নিচু এলাকার দোকান/বাসার মালপত্র উঁচুতে রাখুন, পানিতে ডোবা রাস্তা ও খোলা ড্রেন এড়িয়ে চলুন, "
           "বিদ্যুতের তার থেকে দূরে থাকুন।",
        2: "সম্ভব হলে যাত্রা আগেভাগে সারুন, নিচু রাস্তায় জলাবদ্ধতা হতে পারে।",
        1: "ছাতা রাখুন; বড় জলাবদ্ধতার সম্ভাবনা কম।"}
FOOT = "\n<i>উৎস: Open-Meteo (ECMWF, GFS, ICON) · স্বয়ংক্রিয় পূর্বাভাস, সরকারি সতর্কবার্তা নয়।</i>"


def area_lines(res) -> str:
    rows = sorted(res["areas"], key=lambda r: (-r.level, -r.r3_likely))
    return "\n".join(f"{ICON[r.level]} {r.name}: ৩ ঘণ্টায় {mm(r.r3_likely)}, ২৪ ঘণ্টায় {mm(r.r24_likely)}" for r in rows)


def alert(res, now, city) -> str:
    w = res["worst"]
    lines = [f"{ICON[w.level]} <b>{city}: জলাবদ্ধতার {NAMES[w.level]} ঝুঁকি</b>",
             f"সবচেয়ে ভারী বৃষ্টি: {when(w.peak_time, now)} থেকে ৩ ঘণ্টা",
             f"৩ ঘণ্টায় সম্ভাব্য বৃষ্টি: {mm(w.r3_likely)} (কোনো মডেলে সর্বোচ্চ {mm(w.r3_worst)})",
             f"২৪ ঘণ্টায়: {mm(w.r24_likely)} (সর্বোচ্চ {mm(w.r24_worst)})"]
    if w.prob is not None:
        lines.append(f"বৃষ্টির সম্ভাবনা: {bn(f'{w.prob:.0f}')}%")
    if w.tide_at_peak:
        lines.append("🌊 ভারী বৃষ্টির সময় জোয়ার — পানি নামতে দেরি হতে পারে।")
    elif res["tides"]:
        lines.append("🌊 পরের জোয়ার: " + ", ".join(when(t, now) for t in res["tides"][:2]))
    lines += ["", "<b>এলাকাভিত্তিক:</b>", area_lines(res), "", "💡 " + TIPS.get(w.level, ""), FOOT]
    return "\n".join(lines)


def all_clear(res, now, city) -> str:
    return (f"✅ <b>{city}: জলাবদ্ধতার ঝুঁকি কমেছে</b>\nআগামী ২৪ ঘণ্টায় সর্বোচ্চ ৩ ঘণ্টার বৃষ্টি: "
            f"{mm(res['worst'].r3_likely if res['worst'] else 0)}।" + FOOT)


def morning(res, now, city) -> str:
    w = res["worst"]
    head = f"☀️ <b>{city}: আজকের বৃষ্টির খবর</b>" if w.level == 0 else f"🌧 <b>{city}: আজকের বৃষ্টির খবর</b>"
    return "\n".join([head, f"ঝুঁকি: {ICON[w.level]} {NAMES[w.level]}",
                      f"২৪ ঘণ্টায় সম্ভাব্য বৃষ্টি: {mm(w.r24_likely)} · সবচেয়ে ভারী: {when(w.peak_time, now)}",
                      "", area_lines(res), FOOT])
