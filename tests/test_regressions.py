"""Regression tests for the issues an external Linux audit reported (2026-10-25).

Every test here names the failure it pins down, so a later refactor that brings
the bug back fails loudly instead of quietly writing a junk file (or hiding the
real model cache behind a directory literally named ``D:\\dev\\models\\whisper``).
"""

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import vidlens as C           # noqa: E402
import vidlens_extra as E     # noqa: E402
import vidlens_sanitize as S  # noqa: E402
import vidlens_web as W       # noqa: E402
import vl_mcp as M            # noqa: E402


class PackagingTests(unittest.TestCase):
    """A BOM at byte 0 of pyproject.toml failed the 1.5.0 release before it started.

    `Set-Content -Encoding UTF8` in Windows PowerShell 5.1 prepends EF BB BF; TOML
    parsers reject it as "Invalid statement (at line 1, column 1)" and the whole
    wheel build dies. Editing files from a shell should not be able to do this twice.
    """

    def test_pyproject_has_no_bom(self):
        raw = (ROOT / "pyproject.toml").read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"),
                         "pyproject.toml starts with a UTF-8 BOM; TOML cannot parse it")

    def test_pyproject_declares_the_ocr_extra(self):
        import tomllib
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        extras = data["project"]["optional-dependencies"]
        self.assertIn("ocr", extras)
        self.assertTrue(any("rapidocr" in item for item in extras["ocr"]))
        self.assertIn("vidlens_ocr", data["tool"]["setuptools"]["py-modules"])


class RangeTests(unittest.TestCase):
    """A reversed window used to produce `sheet_20000_5000.jpg` without a word."""

    def test_reversed_range_is_rejected(self):
        with self.assertRaises(ValueError):
            C.clamp_range(20.0, 5.0)

    def test_range_past_the_end_is_clamped(self):
        self.assertEqual(C.clamp_range(0.0, 999.0, 100.0), (0.0, 100.0))

    def test_negative_start_becomes_zero(self):
        self.assertEqual(C.clamp_range(-5.0, 10.0, 100.0), (0.0, 10.0))

    def test_start_beyond_the_end_is_rejected(self):
        with self.assertRaises(ValueError):
            C.clamp_range(100.0, 110.0, 100.0)

    def test_the_mcp_layer_uses_the_same_rule(self):
        with self.assertRaises(ValueError):
            M._clamp_range({"duration": 10.0}, 10.0, 20.0)
        self.assertEqual(M._clamp_range({"duration": 10.0}, -1.0, 5.0), (0.0, 5.0))


class TimeCoercionTests(unittest.TestCase):
    """`start=90` used to reach `s.strip()` and die with an AttributeError."""

    def test_numbers_are_accepted(self):
        self.assertEqual(C.parse_t(M._t(90)), 90.0)
        self.assertEqual(C.parse_t(M._t(1.5)), 1.5)

    def test_strings_still_work(self):
        self.assertEqual(C.parse_t(M._t("1:30")), 90.0)
        self.assertEqual(C.parse_t(M._t("75")), 75.0)

    def test_bool_is_rejected(self):
        with self.assertRaises(ValueError):
            M._t(True)


class ModelDirTests(unittest.TestCase):
    """On POSIX the Windows default must never be created (it would shadow ~/.cache)."""

    def test_posix_has_no_windows_candidate(self):
        dirs = [d for d in C._model_dirs("posix") if d]
        self.assertNotIn("D:\\dev\\models\\whisper", dirs)

    def test_windows_still_prefers_the_d_drive(self):
        self.assertEqual(C._model_dirs("nt")[1], "D:\\dev\\models\\whisper")

    def test_fallback_creates_the_hf_cache_when_nothing_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            with mock.patch.object(Path, "home", return_value=home), \
                    mock.patch.object(C, "_WIN_MODEL_DIR", str(home / "gone" / "whisper")), \
                    mock.patch.dict(os.environ, {"VIDLENS_MODEL_DIR": ""}):
                got = Path(C.model_dir())
            self.assertEqual(got, home / ".cache" / "whisper")
            self.assertTrue(got.is_dir())


class SelectorTests(unittest.TestCase):
    """A single-format page has no `height`, so every height branch matches nothing."""

    def test_video_selector_has_a_last_resort(self):
        sel = W.video_selector(360)
        self.assertIn("height<=360", sel)
        self.assertTrue(sel.endswith("/bv*/b"), sel)

    def test_video_section_keeps_audio_off(self):
        args = W.section_args(1.0, 2.0, 360, False)
        self.assertNotIn("+ba", args[1])
        self.assertTrue(args[1].endswith("/b"), args[1])

    def test_audio_section_has_a_combined_fallback(self):
        args = W.section_args(1.0, 2.0, 360, True)
        self.assertIn("+ba", args[1])
        self.assertIn("/bv*+ba/b/b", args[1])


class AudioFallbackNoteTests(unittest.TestCase):
    """`ba/b` silently degrades to the whole video; the caller must hear about it."""

    def test_combined_container_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)

            def fake_run(args, timeout=900):
                (d / "audio.mp4").write_bytes(b"0" * 4096)
                return 0, "", ""

            notes = []
            with mock.patch.object(W, "run_yt", side_effect=fake_run), \
                    mock.patch.object(W, "_has_video_stream", return_value=True):
                W.download_audio("u", d, 200.0, False, expected_dur=0.0, notes=notes)
            self.assertEqual(len(notes), 1)
            self.assertIn("整段视频", notes[0])

    def test_audio_only_download_says_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)

            def fake_run(args, timeout=900):
                (d / "audio.m4a").write_bytes(b"0" * 4096)
                return 0, "", ""

            notes = []
            with mock.patch.object(W, "run_yt", side_effect=fake_run), \
                    mock.patch.object(W, "_has_video_stream", return_value=False):
                W.download_audio("u", d, 200.0, False, expected_dur=0.0, notes=notes)
            self.assertEqual(notes, [])


class DoctorNetworkTests(unittest.TestCase):
    """A WAF challenge page answers 200 too; status alone is not reachability."""

    def test_json_code_counts_as_reachable(self):
        ok, detail = E._api_reachable(200, '{"code": -101, "message": "not logged in"}')
        self.assertTrue(ok)
        self.assertIn("-101", detail)

    def test_html_challenge_is_not_reachable(self):
        ok, _ = E._api_reachable(200, "<html><body>captcha</body></html>")
        self.assertFalse(ok)

    def test_server_error_is_not_reachable(self):
        self.assertFalse(E._api_reachable(500, "")[0])


class InvisibleCharTests(unittest.TestCase):
    """Mixed payloads used to be summarised as a single stray character."""

    def test_all_kinds_are_reported(self):
        findings = S.scan("a\u200bb\u202ec")
        hits = [f for f in findings if f["kind"] in ("invisible_text", "bidi_override")]
        self.assertTrue(hits)
        self.assertIn("共 2 种", hits[0]["evidence"])

    def test_a_single_kind_stays_short(self):
        findings = S.scan("a\u200bb")
        hits = [f for f in findings if f["kind"] == "invisible_text"]
        self.assertEqual(len(hits), 1)
        self.assertNotIn("共", hits[0]["evidence"])


class CliErrorTests(unittest.TestCase):
    """Bad input should print one line, not a Python traceback."""

    def test_reversed_range_exits_with_a_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            err = io.StringIO()
            with mock.patch.dict(os.environ, {"VIDLENS_OUT": tmp}), \
                    mock.patch.object(sys, "argv",
                                      ["vidlens", "sheet", "clip.mp4",
                                       "--from", "20", "--to", "5"]), \
                    contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as caught:
                    C.main()
            self.assertEqual(caught.exception.code, 2)
            self.assertIn("end", err.getvalue())
            self.assertNotIn("Traceback", err.getvalue())


class OutputBudgetTests(unittest.TestCase):
    """A full brief is 6-9k chars and stays in context for the rest of the session.

    The default must therefore be a digest; "the whole report" has to be an
    explicit, expensive choice. Without this the agent overflows its window after
    a couple of videos and the user sees "context limit exceeded".
    """

    @staticmethod
    def _fixture():
        rows = [{"t0": float(i * 10), "t1": float(i * 10 + 9),
                 "text": f"第{i}段台词内容，用来占位。" * 6} for i in range(100)]
        chapters = [{"from": i * 100.0, "to": (i + 1) * 100.0} for i in range(10)]
        return rows, chapters

    def _digest(self):
        rows, chapters = self._fixture()
        return M._digest({"id": "BV1", "title": "标题", "extractor": "BiliBili"},
                         rows, 600.0, chapters, [], "asr(cached)", "x" * 9000,
                         Path("out/BV1"))

    def test_digest_fits_the_budget(self):
        self.assertLessEqual(len(self._digest()), M.MAX_DIGEST_CHARS)

    def test_digest_points_at_the_full_report(self):
        text = self._digest()
        self.assertIn("brief.md", text)
        self.assertIn('level="full"', text)
        self.assertIn("9000", text)

    def test_digest_is_at_least_four_times_smaller(self):
        self.assertLess(len(self._digest()), 9000 / 4)

    def test_brief_defaults_to_digest(self):
        import inspect
        default = inspect.signature(M.video_brief).parameters["level"].default
        self.assertEqual(default, "digest")

    def test_window_has_a_row_cap(self):
        self.assertGreaterEqual(M.MAX_WINDOW_LINES, 20)
        self.assertLessEqual(M.MAX_WINDOW_LINES, 200)

    def test_watch_cursor_is_per_session(self):
        # One cursor per video meant two conversations watching the same URL
        # advanced each other's position.
        d = Path("out") / "BV1"
        s1, s2, shared = M._watch_path(d, "s1"), M._watch_path(d, "s2"), M._watch_path(d, "")
        self.assertNotEqual(s1, s2)
        self.assertEqual(s1.parent, d)
        self.assertEqual(shared.name, M.WATCH_FILE)
        self.assertTrue(s1.name.startswith("watch-s1"))

    def test_watch_path_rejects_path_tricks(self):
        p = M._watch_path(Path("out") / "BV1", "../../etc/passwd")
        self.assertEqual(p.parent, Path("out") / "BV1")
        self.assertNotIn("..", p.name)

    def test_clipping_never_drops_the_how_to_continue_line(self):
        # A blind [:limit] slice could cut the line that says what to call next,
        # leaving a truncated reply with no way forward.
        lines = ["head"] + [f"body line {i} " + "x" * 80 for i in range(40)] \
            + ["tail: 全文在 brief.md", "tail: 要细节用 video_window"]
        out = M._fit(lines, 400, tail=2)
        self.assertLessEqual(len(out), 460)
        self.assertIn("brief.md", out)
        self.assertIn("video_window", out)
        self.assertIn("略去", out)


class NoSpeechTests(unittest.TestCase):
    """A musical video came back as "语音覆盖 100%" with a 1089-character transcript.

    ASR emits one row per audio window even when it heard nothing, so the rows are
    "。" with `track: speech`. Counting those as speech made the caller reason about
    a script that did not exist; the fix is a real character count, everywhere.
    """

    def test_punctuation_is_not_speech(self):
        self.assertEqual(C.speech_chars("。"), 0)
        self.assertEqual(C.speech_chars("…—、"), 0)
        self.assertEqual(C.speech_chars("哎。"), 1)
        self.assertEqual(C.speech_chars("这是一句台词"), 6)

    def _no_speech_rows(self):
        return [{"t0": float(i * 20), "t1": float(i * 20 + 20), "text": "。",
                 "track": "speech"} for i in range(11)]

    def test_digest_says_there_is_no_speech(self):
        rows = self._no_speech_rows()
        out = M._digest({"id": "BV1", "title": "纯音乐", "extractor": "BiliBili"},
                        rows, 210.234, [], [], "asr(sensevoice)",
                        "x" * 1089, Path("out/BV1"))
        self.assertIn("几乎无人声", out)
        self.assertNotIn("语音覆盖 100%", out)
        self.assertNotIn("有声窗口覆盖", out)
        self.assertIn("台词 0 字", out)
        # …and it points at the route that can actually see this video.
        self.assertIn("video_visual_scan", out)

    def test_brief_marks_a_silent_video_instead_of_a_clean_transcript(self):
        rows = self._no_speech_rows()
        text = W.build_brief({"id": "BV1", "title": "纯音乐", "extractor": "BiliBili"},
                             rows, [], [], 210.234, [], "asr(sensevoice)", "sensevoice")
        self.assertIn("未识别到语音", text)
        self.assertIn("没有有效台词", text)

    def test_punctuation_rows_do_not_print_as_transcript_lines(self):
        rows = self._no_speech_rows()
        text = W.build_brief({"id": "BV1", "title": "纯音乐", "extractor": "BiliBili"},
                             rows, [], [], 210.234, [], "asr(sensevoice)", "sensevoice")
        self.assertNotIn("`00:00.000` 。", text)


class DigestSamplingTests(unittest.TestCase):
    """Uniform sampling walked past the sentence that decided the video's meaning.

    An argument closes at the end of a section; five evenly spaced anchors gave
    the caller a table of contents that read like a summary and was wrong.
    """

    def test_a_pivot_sentence_survives_sampling(self):
        rows = []
        for i in range(40):
            text = f"第{i}段填充内容，讲一些过程性的事情。" * 2
            if i == 21:      # the line that matters: not on any uniform anchor
                text = "总之，前面那些不是重点，真正的问题在于证据链断了。"
            rows.append({"t0": float(i * 10), "t1": float(i * 10 + 9), "text": text})
        out = M._digest({"id": "BV1", "title": "t", "extractor": "x"},
                        rows, 400.0, [], [], "subs(zh)", "x" * 4000, Path("out/BV1"))
        self.assertIn("真正的问题在于证据链断了", out)

    def test_digest_admits_it_is_not_evidence(self):
        rows = [{"t0": float(i * 10), "t1": float(i * 10 + 9), "text": f"第{i}段内容" * 3}
                for i in range(30)]
        out = M._digest({"id": "BV1", "title": "t", "extractor": "x"},
                        rows, 300.0, [], [], "subs(zh)", "x" * 3000, Path("out/BV1"))
        self.assertIn("不是全文证据", out)
        self.assertIn("覆盖: 音频 ✓", out)


class InlineImageTests(unittest.TestCase):
    """An MCP image block is base64 on the wire: a 340KB sheet is ~450k characters."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.big = Path(self.dir) / "big.jpg"
        self.small = Path(self.dir) / "small.jpg"
        self.big.write_bytes(b"x" * (M.MAX_INLINE_IMAGE_BYTES + 1))
        self.small.write_bytes(b"x" * 512)

    def tearDown(self):
        for p in (self.big, self.small):
            p.unlink(missing_ok=True)
        os.rmdir(self.dir)

    def test_big_images_are_left_on_disk(self):
        with mock.patch.dict(os.environ, {"VIDLENS_INLINE_IMAGES": "auto"}):
            keep, note = M._image_blocks([self.big])
        self.assertEqual(keep, [])
        self.assertIn("未内联", note)
        self.assertIn("big.jpg", note)

    def test_small_images_still_travel(self):
        with mock.patch.dict(os.environ, {"VIDLENS_INLINE_IMAGES": "auto"}):
            keep, note = M._image_blocks([self.small])
        self.assertEqual(len(keep), 1)
        self.assertEqual(note, "")

    def test_never_means_never(self):
        with mock.patch.dict(os.environ, {"VIDLENS_INLINE_IMAGES": "never"}):
            keep, _note = M._image_blocks([self.small])
        self.assertEqual(keep, [])

    def test_the_bridge_asks_for_every_image(self):
        # The plugin converts Image -> file path, so `auto` would only lose pictures.
        src = (ROOT.parent / "vidlens-mcp-dsh" / "bridge" / "vidlens_bridge.py")
        if not src.exists():
            self.skipTest("sibling repo not present")
        self.assertIn('VIDLENS_INLINE_IMAGES", "always"', src.read_text(encoding="utf-8"))


class MetaSnapshotTests(unittest.TestCase):
    """Two tools reported 75336 and 73595 plays for the same video; neither said "snapshot"."""

    def test_brief_stamps_when_the_counts_were_taken(self):
        meta = {"id": "BV1", "title": "t", "extractor": "BiliBili",
                "view_count": 1, "like_count": 2, "_fetched_at": "2026-10-26 16:00"}
        text = W.build_brief(meta, [], [], [], 10.0, [], "subs(zh)", "zh")
        self.assertIn("抓取于: 2026-10-26 16:00", text)
        self.assertIn("快照", text)

    def test_brief_without_a_stamp_says_nothing_extra(self):
        meta = {"id": "BV1", "title": "t", "extractor": "BiliBili", "view_count": 1}
        text = W.build_brief(meta, [], [], [], 10.0, [], "subs(zh)", "zh")
        self.assertNotIn("抓取于", text)


class CostLineTests(unittest.TestCase):
    """The caller could not tell what a call would cost, so it guessed and overflowed."""

    def test_cost_line_reports_an_estimate(self):
        line = M._cost("x" * 1500)
        self.assertIn("成本", line)
        self.assertIn("tok", line)
        self.assertIn("估算", line)

    def test_digest_carries_its_own_cost(self):
        rows = [{"t0": float(i * 10), "t1": float(i * 10 + 9), "text": f"第{i}段内容" * 3}
                for i in range(20)]
        out = M._digest({"id": "BV1", "title": "t", "extractor": "x"},
                        rows, 200.0, [], [], "subs(zh)", "x" * 2000, Path("out/BV1"))
        self.assertIn("[成本]", out)


if __name__ == "__main__":
    unittest.main()
