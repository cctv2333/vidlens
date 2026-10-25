#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for the pauses.json shape bug and chapter suggestions.

The CLI pipeline writes {"threshold_db": ..., "gaps": [...]}, while grab/MCP
write a plain list. plan() used to assume a list, so a CLI-produced cache made
it raise AttributeError: 'str' object has no attribute 'get' -- and _do_brief
swallowed that exception, so the brief silently lost its chapter section.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import vidlens_extra as E  # noqa: E402
import vidlens_web as W  # noqa: E402
import vl_mcp as M  # noqa: E402


def gap(t0, t1):
    return {"t0": t0, "t1": t1, "dur": round(t1 - t0, 3), "track": "silence"}


class ReadPausesTests(unittest.TestCase):
    def test_accepts_both_shapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "pauses.json").write_text(
                json.dumps([gap(1, 3)]), encoding="utf-8")
            self.assertEqual(W.read_pauses(d)[0]["dur"], 2.0)

            (d / "pauses.json").write_text(
                json.dumps({"threshold_db": -32, "gaps": [gap(4, 9)]}),
                encoding="utf-8")
            got = W.read_pauses(d)
            self.assertEqual(len(got), 1)
            self.assertEqual(got[0]["t0"], 4.0)

    def test_empty_and_malformed_are_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self.assertEqual(W.read_pauses(d), [])  # no file
            (d / "pauses.json").write_text("{not json", encoding="utf-8")
            self.assertEqual(W.read_pauses(d), [])
            (d / "pauses.json").write_text("42", encoding="utf-8")
            self.assertEqual(W.read_pauses(d), [])
            (d / "pauses.json").write_text(
                json.dumps({"gaps": ["x", {"t1": 2}, {"t0": 1, "t1": 3, "dur": "bad"}]}),
                encoding="utf-8")
            got = W.read_pauses(d)
            self.assertEqual(len(got), 1, "only the usable dict survives")
            self.assertEqual(got[0]["dur"], 2.0, "missing/bad dur falls back to t1-t0")


class PlanTests(unittest.TestCase):
    def _plan(self, pauses):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d = root / "BVtest"
            d.mkdir()
            (d / "shots.json").write_text(
                json.dumps({"threshold": 0.25, "cuts": [400.0]}), encoding="utf-8")
            (d / "pauses.json").write_text(
                json.dumps(pauses, ensure_ascii=False), encoding="utf-8")
            meta = ({"id": "BVtest", "duration": 900.0}, [])
            with mock.patch.object(W, "fetch_meta", return_value=meta), \
                    mock.patch.object(W, "out_root", return_value=root):
                return E.plan("https://example.invalid/v")

    def test_cli_shaped_pauses_no_longer_crashes(self):
        p = self._plan({"threshold_db": -32, "gaps": [gap(700, 710)]})
        self.assertEqual(p["duration"], 900.0)
        self.assertEqual([(c["from"], c["to"]) for c in p["chapters"]],
                         [(0.0, 400.0), (400.0, 700.0), (700.0, 900.0)])

    def test_mcp_shaped_pauses_still_works(self):
        p = self._plan([gap(700, 710)])
        self.assertEqual(len(p["chapters"]), 3)

    def test_broken_pauses_do_not_kill_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d = root / "BVtest"
            d.mkdir()
            (d / "pauses.json").write_text("[{", encoding="utf-8")
            meta = ({"id": "BVtest", "duration": 120.0}, [])
            with mock.patch.object(W, "fetch_meta", return_value=meta), \
                    mock.patch.object(W, "out_root", return_value=root):
                p = E.plan("x")
        self.assertEqual(p["chapters"], [{"from": 0.0, "to": 120.0}])


class ChapterTests(unittest.TestCase):
    def test_cuts_and_long_silences_split_windows(self):
        ch = W.plan_chapters(900.0, [400.0], [gap(700, 710)])
        self.assertEqual([(c["from"], c["to"]) for c in ch],
                         [(0.0, 400.0), (400.0, 700.0), (700.0, 900.0)])

    def test_short_video_is_one_chapter(self):
        ch = W.plan_chapters(120.0, [], [])
        self.assertEqual(ch, [{"from": 0.0, "to": 120.0}])

    def test_brief_shows_chapters_before_transcript(self):
        meta = {"id": "BVx", "title": "t", "extractor": "x", "uploader": "u",
                "upload_date": "20260101", "duration": 900, "view_count": 1,
                "like_count": 1, "description": ""}
        rows = [{"t0": 0.0, "t1": 10.0, "text": "hello", "words": []}]
        brief = W.build_brief(meta, rows, [], [], 900.0, [], "asr", "small",
                              chapters=[{"from": 0.0, "to": 450.0},
                                        {"from": 450.0, "to": 900.0}])
        self.assertIn("## 分步看", brief)
        self.assertLess(brief.index("## 分步看"), brief.index("## 转写"))


class JobBriefTests(unittest.TestCase):
    def test_do_brief_gets_chapters_without_calling_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "BVtest"
            d.mkdir()
            meta = {"id": "BVtest", "duration": 900.0}
            rows = [{"t0": 0.0, "t1": 10.0, "text": "hello", "words": []}]
            gaps = [gap(400, 410)]
            with mock.patch.object(M, "_dir", return_value=(meta, d)), \
                    mock.patch.object(M, "_rows_with_media",
                                      return_value=(meta, rows, gaps, "asr")), \
                    mock.patch.object(M.extra, "plan",
                                      side_effect=AssertionError("plan must not run")):
                out = M._do_brief(lambda *a: None, "u", "zh", "small", False, False)
            self.assertTrue((d / "brief.md").exists())
        self.assertIn("## 分步看", out)
        self.assertIn("06:40.000", out)  # chapter boundary at 400s
        self.assertNotIn("plan must not run", out)


class CachedGapsTests(unittest.TestCase):
    def test_rows_with_media_reads_cli_shaped_pauses(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "meta.json").write_text(
                json.dumps({"meta": {"id": "x", "duration": 100.0}, "threats": []}),
                encoding="utf-8")
            (d / "transcript.jsonl").write_text(
                json.dumps({"t0": 0.0, "t1": 5.0, "text": "hi", "words": []}) + "\n",
                encoding="utf-8")
            (d / "pauses.json").write_text(
                json.dumps({"threshold_db": -32, "gaps": [gap(20, 24)]}),
                encoding="utf-8")
            _meta, _rows, gaps, source = M._rows_with_media("u", d, "zh", "small", False)
        self.assertEqual(source, "asr(cached)")
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["t0"], 20.0)


if __name__ == "__main__":
    unittest.main()
