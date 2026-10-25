#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vidlens_ads - find sponsor reads and cut them out of the evidence.

Why: an ad is not weak evidence, it is zero evidence. Keeping it in a summary
pollutes the transcript with product claims that have no relation to the video's
argument. The user's rule is blunt: 广告直接略过.

Approach: score transcript segments by sponsor vocabulary, group nearby hits,
then keep only groups that are both long enough and dense enough. No ML, no
network, fully inspectable - a wrong detection can be argued with.
"""

from __future__ import annotations

import re

# weight 3 = almost never appears outside a sponsor read
STRONG = {
    "赞助": 3, "广告": 3, "推广": 2, "优惠": 2, "优惠券": 3, "领券": 3, "折扣": 2,
    "下单": 3, "购买": 2, "链接": 2, "小黄车": 3, "购物车": 3, "口令": 3,
    "旗舰店": 3, "包邮": 3, "到手价": 3, "原价": 2, "券后": 3, "直播间": 3,
    "买一送一": 3, "限时": 2, "返现": 3, "秒杀": 3, "新品": 2, "促销": 3,
    "点击": 2, "二维码": 3, "下单立减": 3, "官方": 1,
}
MEDIUM = {
    "品牌": 1, "产品": 1, "成分": 2, "毫克": 2, "补充": 1, "营养": 2, "DHA": 3,
    "效果": 1, "推荐给": 2, "靠谱": 1, "积分": 2, "保温杯": 3, "会员": 1,
    "福利": 2, "合作": 1, "联合": 1, "试用": 2, "体验": 1, "口感": 2, "配方": 2,
    "吸收": 1, "试试": 1, "有需要": 2, "记住这个": 2, "告诉": 0,
}
WEIGHTS = {**{k: v for k, v in STRONG.items()}, **{k: v for k, v in MEDIUM.items()}}

NUM_PROMO = re.compile(r"\d+\s*(毫克|mg|毫升|ml|元|块|折|斤|克|%|天)")

# ASR output for zh is often Traditional. Normalise the characters our vocabulary
# actually uses, rather than pulling in a full converter as a dependency.
_T2S = {
    "贊": "赞", "廣": "广", "薦": "荐", "優": "优", "領": "领", "購": "购",
    "買": "买", "鏈": "链", "車": "车", "艦": "舰", "郵": "邮", "價": "价",
    "後": "后", "殺": "杀", "點": "点", "擊": "击", "維": "维", "碼": "码",
    "產": "产", "補": "补", "營": "营", "養": "养", "譜": "谱", "積": "积",
    "會": "会", "員": "员", "聯": "联", "試": "试", "體": "体", "驗": "验",
    "記": "记", "這": "这", "訴": "诉", "們": "们", "個": "个", "嗎": "吗",
    "讀": "读", "頁": "页", "圖": "图", "幣": "币", "錢": "钱", "費": "费",
    "東": "东", "亞": "亚", "歐": "欧", "國": "国", "際": "际", "戰": "战",
}
_T2S_MAP = {ord(k): v for k, v in _T2S.items()}


def _norm(text: str) -> str:
    return (text or "").translate(_T2S_MAP)

AD_LABEL = "[广告·已跳过]"


def score_text(text: str) -> int:
    if not text:
        return 0
    s = 0
    t = _norm(text)
    for k, w in WEIGHTS.items():
        if w and k in t:
            s += w
    if NUM_PROMO.search(t):
        s += 1
    return s


def detect(rows: list[dict], min_score: float = 6.0, min_dur: float = 15.0,
           density: float = 2.0, join_sec: float = 25.0) -> list[dict]:
    """rows: transcript segments with t0/t1/text. Returns ad ranges.

    Hits are grouped by *time* gap, not segment index: a sponsor read keeps
    mentioning product vocabulary every few seconds, but the ASR splits it into
    unevenly sized segments.
    """
    scored = [(i, score_text(r.get("text") or "")) for i, r in enumerate(rows)]
    scored = [(i, s) for i, s in scored if s > 0]
    if not scored:
        return []
    groups, cur = [], []
    for i, s in scored:
        if cur:
            prev_i = cur[-1][0]
            gap = float(rows[i].get("t0") or 0) - float(rows[prev_i].get("t1") or 0)
            if gap > join_sec:
                groups.append(cur)
                cur = []
        cur.append((i, s))
    if cur:
        groups.append(cur)

    out = []
    for g in groups:
        total = sum(s for _, s in g)
        t0 = float(rows[g[0][0]]["t0"])
        t1 = float(rows[g[-1][0]]["t1"])
        dur = max(0.1, t1 - t0)
        per_min = total / (dur / 60.0)
        if total >= min_score and dur >= min_dur and per_min >= density:
            out.append({"t0": round(t0, 2), "t1": round(t1, 2), "dur": round(dur, 1),
                        "score": round(total, 1), "per_min": round(per_min, 1),
                        "first": (rows[g[0][0]].get("text") or "")[:40],
                        "last": (rows[g[-1][0]].get("text") or "")[:40]})
    # merge overlapping / adjacent
    out.sort(key=lambda x: x["t0"])
    merged = []
    for a in out:
        if merged and a["t0"] <= merged[-1]["t1"] + 2.0:
            merged[-1]["t1"] = max(merged[-1]["t1"], a["t1"])
            merged[-1]["dur"] = round(merged[-1]["t1"] - merged[-1]["t0"], 1)
            merged[-1]["score"] = round(merged[-1]["score"] + a["score"], 1)
            merged[-1]["last"] = a["last"]
        else:
            merged.append(dict(a))
    return merged


def inside(t: float, ranges: list[dict]) -> bool:
    return any(r["t0"] <= t <= r["t1"] for r in ranges)


def strip(rows: list[dict], ranges: list[dict]) -> list[dict]:
    """Drop ad segments from the working set (returns new list)."""
    if not ranges:
        return list(rows)
    return [r for r in rows if not inside(float(r.get("t0") or 0), ranges)]


def section(ranges: list[dict], total_dur: float = 0.0) -> str:
    if not ranges:
        return "## 广告段落\n\n- 未检出赞助/带货内容\n"
    saved = sum(r["dur"] for r in ranges)
    L = ["## 广告段落（已跳过，不计入摘要）", ""]
    for r in ranges:
        L.append(f"- `{_hms(r['t0'])}` → `{_hms(r['t1'])}`（{r['dur']:.0f} 秒，"
                 f"命中密度 {r['per_min']}/分钟）")
    L.append(f"- 共 {len(ranges)} 段、{saved:.0f} 秒"
             + (f"，占全片 {saved / total_dur * 100:.0f}%" if total_dur else ""))
    return "\n".join(L) + "\n"


def _hms(t: float) -> str:
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}" if h else f"{m:02d}:{s:06.3f}"
