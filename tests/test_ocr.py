"""Screen-text OCR: the parts that can be tested without a video or a model.

The engine itself is RapidOCR (Apache-2.0). These tests pin down the rules around
it, because the useful behaviour is not "run a model" — it is deciding what on
screen is a caption, what is a watermark, and what is a diagram's label.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import vidlens_ocr as O  # noqa: E402


class LazyImportTests(unittest.TestCase):
    """OCR is an optional extra: importing vidlens must not pull opencv/onnxruntime."""

    def test_importing_the_module_does_not_import_the_engine(self):
        code = ("import sys; sys.path.insert(0, r'%s'); import vidlens_ocr; "
                "print('rapidocr' in sys.modules or 'cv2' in sys.modules)" % ROOT)
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr[-500:])
        self.assertEqual(out.stdout.strip(), "False")

    def test_available_is_a_tuple_not_an_exception(self):
        ok, why = O.available()
        self.assertIsInstance(ok, bool)
        self.assertIsInstance(why, str)
        if not ok:
            self.assertTrue(why)


class NoiseTests(unittest.TestCase):
    """A watermark read 8 times is the failure mode this replaces."""

    def test_platform_watermark_is_noise(self):
        self.assertTrue(O.is_noise("折光AI1996 bilibili"))
        self.assertTrue(O.is_noise("哔哩哔哩"))
        self.assertTrue(O.is_noise("UP主：张三 B站"))

    def test_a_caption_mentioning_bilibili_is_kept(self):
        long = "这个视频最早发在bilibili，后来被搬到别的地方去了，请注意来源"
        self.assertFalse(O.is_noise(long))

    def test_timecode_and_punctuation_are_noise(self):
        self.assertTrue(O.is_noise("01:11"))
        self.assertTrue(O.is_noise("· · ·"))
        self.assertTrue(O.is_noise("。"))

    def test_short_captions_survive(self):
        self.assertFalse(O.is_noise("0 层"))
        self.assertFalse(O.is_noise("这是人类"))

    def test_low_score_is_noise(self):
        self.assertTrue(O.is_noise("某个很长的句子", score=0.1))


class OverlayTests(unittest.TestCase):
    def test_a_string_in_most_frames_is_an_overlay(self):
        frames = [{"t": float(i), "lines": [{"text": "折光AI1996 bilibili", "score": 0.9},
                                            {"text": f"第{i}句台词", "score": 0.9}]}
                  for i in range(10)]
        overlays = O.overlay_texts(frames)
        self.assertIn(O.normalize("折光AI1996 bilibili"), overlays)
        self.assertNotIn(O.normalize("第0句台词"), overlays)

    def test_a_caption_that_happens_to_repeat_twice_is_not_an_overlay(self):
        frames = [{"t": float(i), "lines": [{"text": "重复两次的句子", "score": 0.9}]}
                  for i in range(2)]
        self.assertEqual(O.overlay_texts(frames), set())


class MergeTests(unittest.TestCase):
    def test_the_same_caption_across_frames_is_one_block(self):
        frames = [{"t": 0.0, "lines": [{"text": "全世界有195个主权国家", "score": 0.9}]},
                  {"t": 20.0, "lines": [{"text": "全世界有195个主权国家", "score": 0.9}]},
                  {"t": 40.0, "lines": [{"text": "剩下的193个", "score": 0.9}]}]
        blocks = O.merge_captions(frames)
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0]["frames"], 2)
        self.assertEqual(blocks[0]["t0"], 0.0)
        self.assertEqual(blocks[0]["t1"], 20.0)

    def test_a_caption_that_changes_by_a_character_is_still_the_same(self):
        self.assertTrue(O.same_caption("全世界有195个主权国家", "全世界有195个主权国家。"))

    def test_different_captions_are_not_merged(self):
        self.assertFalse(O.same_caption("这是人类", "重建巴别塔的图"))

    def test_a_caption_split_across_frames_stays_split(self):
        blocks = O.merge_captions([
            {"t": 0.0, "lines": [{"text": "于是今年2月，", "score": 0.9}]},
            {"t": 30.0, "lines": [{"text": "印度的Sarvam推出了模型", "score": 0.9}]}])
        self.assertEqual([b["text"] for b in blocks], ["于是今年2月，", "印度的Sarvam推出了模型"])


class DiagramTests(unittest.TestCase):
    def test_a_transformer_diagram_is_not_narration(self):
        lines = [{"text": t, "score": 0.9} for t in
                 ("Softmax", "Linear", "Add & Norm", "Feed Forward",
                  "Multi-Head Attention", "Input Embedding", "Output Embedding")]
        self.assertTrue(O.looks_like_diagram(lines))

    def test_two_chinese_lines_are_not_a_diagram(self):
        lines = [{"text": "全世界有195个主权国家", "score": 0.9},
                 {"text": "剩下的193个，都在干嘛？", "score": 0.9}]
        self.assertFalse(O.looks_like_diagram(lines))

    def test_diagram_frame_keeps_its_one_real_caption(self):
        class FakeEngine:
            def __call__(self, _path):
                class R:
                    txts = ("Softmax", "Linear", "Add & Norm", "Feed Forward",
                            "Multi-Head Attention", "重建巴别塔的图")
                    scores = (0.9,) * 6
                return R()

        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "f.jpg"
            p.write_bytes(b"x")
            saved = O._ENGINE
            try:
                O._ENGINE = FakeEngine()
                res = O.ocr_frames([{"t": 44.5, "path": str(p)}])
            finally:
                O._ENGINE = saved
        self.assertEqual([b["text"] for b in res["blocks"]], ["重建巴别塔的图"])
        self.assertEqual(len(res["diagram"]), 1)
        self.assertIn("Softmax", res["diagram"][0]["text"])


class TimestampTests(unittest.TestCase):
    def test_points_are_inside_the_window_and_evenly_spread(self):
        ts = O.timestamps(100.0, 4, 0.0, 40.0)
        self.assertEqual(len(ts), 4)
        self.assertTrue(all(0.0 <= t < 40.0 for t in ts))
        self.assertEqual(ts, sorted(ts))

    def test_a_full_video_window_uses_its_duration(self):
        ts = O.timestamps(60.0, 3)
        self.assertEqual(len(ts), 3)
        self.assertTrue(all(0.0 <= t < 60.0 for t in ts))

    def test_zero_length_window_still_returns_one_point(self):
        self.assertEqual(O.timestamps(10.0, 5, 5.0, 5.0), [5.0])


class AttributionTests(unittest.TestCase):
    """RapidOCR is Apache-2.0 and its models come from PaddleOCR: say so."""

    def test_notice_names_the_engine_and_its_licence(self):
        notice = (ROOT / "NOTICE.md")
        if not notice.exists():
            self.skipTest("NOTICE.md absent")
        text = notice.read_text(encoding="utf-8")
        self.assertIn("RapidOCR", text)
        self.assertIn("Apache", text)
        self.assertIn("PaddleOCR", text)


if __name__ == "__main__":
    unittest.main()
