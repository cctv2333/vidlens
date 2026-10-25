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


if __name__ == "__main__":
    unittest.main()
