#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for sponsor-read detection. No network."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import vidlens_ads as A  # noqa: E402


def seg(t0, t1, text):
    return {"t0": t0, "t1": t1, "text": text}


def make_rows():
    rows = []
    # normal talk
    for i in range(20):
        rows.append(seg(i * 4.0, i * 4.0 + 3.8, f"这里是地缘分析第{i}句，讲中东局势与美债。"))
    # sponsor read: 10 segments, 60s
    ad = [
        "大家可以试试这个新品",
        "两粒就能补充473毫克的有效成分",
        "每天补充的那组人效果更好",
        "有需要的可以点链接下单",
        "官方旗舰店现在有优惠券",
        "领券之后到手价很合适",
        "限时折扣，包邮到家",
        "会员积分还能换一个保温杯",
        "记住这个口令，截图找客服",
        "好了说回正题",
    ]
    for i, t in enumerate(ad):
        rows.append(seg(90 + i * 6.0, 90 + i * 6.0 + 5.5, t))
    # more normal talk
    for i in range(20):
        rows.append(seg(160 + i * 4.0, 160 + i * 4.0 + 3.8, f"继续讲地缘第{i}句。"))
    return rows


class AdTests(unittest.TestCase):
    def test_promo_number_regex_uses_milligrams(self):
        self.assertIsNotNone(A.NUM_PROMO.search("2毫克"))
        self.assertIsNone(A.NUM_PROMO.search("2毫光"))

    def test_score_plain_text_is_zero(self):
        self.assertEqual(A.score_text("中美会晤之后，双方关系走向稳定"), 0)

    def test_score_ad_text_is_high(self):
        self.assertGreaterEqual(A.score_text("点击链接领券下单，官方旗舰店优惠"), 6)

    def test_traditional_chinese_is_normalised(self):
        # ASR often returns Traditional for zh
        self.assertGreaterEqual(A.score_text("兩粒就能夠補充473毫克的DHA"), 3)

    def test_detect_finds_the_sponsor_block(self):
        rows = make_rows()
        ads = A.detect(rows)
        self.assertEqual(len(ads), 1, ads)
        a = ads[0]
        self.assertLess(a["t0"], 100)
        self.assertGreater(a["t1"], 140)
        self.assertGreaterEqual(a["dur"], 40)

    def test_detect_ignores_clean_video(self):
        rows = [seg(i * 5.0, i * 5.0 + 4.5, f"第{i}段：石油价格上涨，黄金下跌。")
                for i in range(60)]
        self.assertEqual(A.detect(rows), [])

    def test_strip_removes_only_ad_range(self):
        rows = make_rows()
        ads = A.detect(rows)
        kept = A.strip(rows, ads)
        self.assertLess(len(kept), len(rows))
        for r in kept:
            for a in ads:
                self.assertFalse(a["t0"] <= r["t0"] <= a["t1"], r["text"])

    def test_section_mentions_duration(self):
        rows = make_rows()
        ads = A.detect(rows)
        sec = A.section(ads, 300.0)
        self.assertIn("已跳过", sec)
        self.assertIn("秒", sec)

    def test_empty_section(self):
        self.assertIn("未检出", A.section([], 100.0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
