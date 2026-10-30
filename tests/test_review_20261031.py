#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fixes from the 2026-10-31 field report (BV12txe6GE15).

R-1 sentence timing, R-2 grid vs chapter wording, R-3 tool-name prefix,
R-5 comment limit, R-6 date/truncation shapes.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import vidlens as core  # noqa: E402
import vidlens_extra as extra  # noqa: E402
import vidlens_sensevoice as sv  # noqa: E402


class SentenceSplitTests(unittest.TestCase):
    """20s blocks used to cut sentences in half and give 20s-granularity codes."""

    TEXT = "各位下午好。这次会议我主要讲三件事。第一，营收下降8%。"
    TOKENS = list(TEXT)                       # SenseVoice: one token per CJK char
    TS = [0.2 * i for i in range(len(TEXT))]

    def test_splits_at_full_stops_with_real_times(self):
        rows = sv.split_sentences(self.TEXT, self.TOKENS, self.TS, 10.0, 30.0)
        self.assertEqual([r["text"] for r in rows],
                         ["各位下午好。", "这次会议我主要讲三件事。", "第一，营收下降8%。"])
        self.assertAlmostEqual(rows[0]["t0"], 10.0, places=3)
        self.assertAlmostEqual(rows[1]["t0"], 10.0 + 0.2 * 6, places=3)
        self.assertLess(rows[0]["t1"], rows[1]["t1"])

    def test_no_second_decode_is_needed(self):
        rows = sv.split_sentences(self.TEXT, self.TOKENS, self.TS, 0.0, 20.0)
        self.assertTrue(all(r["t1"] <= 20.0 for r in rows))

    def test_falls_back_to_one_row_when_tokens_disagree(self):
        # English BPE / ITN: token count != char count -> do not invent a split
        rows = sv.split_sentences("Hello world. Second sentence.", ["Hello", "world"],
                                  [0.0, 0.4], 5.0, 9.0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["t0"], 5.0)

    def test_empty_text_is_empty(self):
        self.assertEqual(sv.split_sentences("", [], [], 0.0, 1.0), [])

    def test_join_rows_closes_the_chunk_seam(self):
        rows = [{"t0": 0.0, "t1": 5.0, "text": "更有意思"},
                {"t0": 5.0, "t1": 8.0, "text": "的是，1972年"}]
        out = sv._join_rows(rows)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["text"], "更有意思的是，1972年")
        self.assertEqual(out[0]["t1"], 8.0)

    def test_join_rows_keeps_finished_sentences(self):
        rows = [{"t0": 0.0, "t1": 5.0, "text": "第一句。"},
                {"t0": 5.0, "t1": 8.0, "text": "第二句。"}]
        self.assertEqual(len(sv._join_rows(rows)), 2)


class ToolNamePrefixTests(unittest.TestCase):
    """Text that says `video_window` sends a plugin user to a tool that isn't there."""

    def tearDown(self):
        os.environ.pop("VIDLENS_TOOL_PREFIX", None)

    def test_default_surface_is_unchanged(self):
        self.assertEqual(core.retitle("用 `video_window` 读台词"), "用 `video_window` 读台词")

    def test_plugin_surface_renames(self):
        os.environ["VIDLENS_TOOL_PREFIX"] = "vidlens_"
        out = core.retitle("用 `video_window` 和 video_ocr，别用 video_visual_scan")
        self.assertIn("vidlens_window", out)
        self.assertIn("vidlens_ocr", out)
        self.assertNotIn("video_window", out)

    def test_cli_commands_are_not_renamed(self):
        os.environ["VIDLENS_TOOL_PREFIX"] = "vidlens_"
        self.assertIn("vl clip", core.retitle("命令示例：`vl clip <url>`"))

    def test_unknown_words_are_left_alone(self):
        os.environ["VIDLENS_TOOL_PREFIX"] = "vidlens_"
        self.assertEqual(core.retitle("video_codec=x264"), "video_codec=x264")


class DateShapeTests(unittest.TestCase):
    def test_iso_date_normalises_bilibili_shape(self):
        self.assertEqual(core.iso_date("20261030"), "2026-10-30")
        self.assertEqual(core.iso_date("2026-10-30"), "2026-10-30")
        self.assertEqual(core.iso_date(None), "")


class CommentsTrimTests(unittest.TestCase):
    def test_block_reports_what_was_trimmed(self):
        info = {"view": 100, "like": 5, "like_rate": 5.0, "reply_count": 40,
                "reply_per_1k_views": 400.0, "danmaku": 1,
                "comments": [{"like": 1, "text_clean": "好", "threats": [],
                              "text": "好", "user": "u", "time": 0,
                              "pictures": [], "rcount": 0}],
                "neg_hits": 0, "pos_hits": 0, "neg_per_100": 0.0,
                "neg_like_ratio": 0.0, "controversy": "低", "scam_reports": 0,
                "trimmed": 6}
        block = extra.comments_block(info)
        self.assertIn("另有 6 条", block)


class PlanWordingTests(unittest.TestCase):
    """A 300s grid is not a chapter; calling it one invites invented story turns."""

    GRID = {"id": "BVx", "duration": 881.8, "source": "grid",
            "chapters": [{"from": 0.0, "to": 300.0}, {"from": 300.0, "to": 600.0},
                         {"from": 600.0, "to": 881.8}]}

    def test_short_video_says_no_split_needed(self):
        from unittest import mock
        import vl_mcp
        with mock.patch.object(vl_mcp.extra, "plan", lambda *a, **k: dict(self.GRID)):
            out = vl_mcp.video_plan("https://example.com/x")
        self.assertIn("不需要分段", out)
        self.assertIn("（grid）", out)
        self.assertNotIn("章节 3 个", out)

    def test_long_video_keeps_the_grid_advice(self):
        from unittest import mock
        import vl_mcp
        grid = dict(self.GRID, duration=3600.0,
                    chapters=[{"from": 0.0, "to": 300.0}, {"from": 300.0, "to": 600.0}])
        with mock.patch.object(vl_mcp.extra, "plan", lambda *a, **k: grid):
            out = vl_mcp.video_plan("https://example.com/x")
        self.assertIn("分段", out)
        self.assertIn("不代表内容转折", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
