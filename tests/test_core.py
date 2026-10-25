#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for the vidlens core. No network required."""

import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import vidlens as C  # noqa: E402


def make_media(dirpath: Path) -> Path:
    """4s clip: 2s red + 2s blue. Audio: 1s tone, 1.2s silence, 1s tone."""
    out = dirpath / "t.mp4"
    ff = C.ffmpeg_exe()
    cmd = [ff, "-hide_banner", "-loglevel", "error",
           "-f", "lavfi", "-i", "color=c=red:s=320x180:d=2:r=25",
           "-f", "lavfi", "-i", "color=c=blue:s=320x180:d=2:r=25",
           "-f", "lavfi", "-i", "sine=frequency=440:duration=1:sample_rate=16000",
           "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono:d=1.2",
           "-f", "lavfi", "-i", "sine=frequency=440:duration=1:sample_rate=16000",
           "-filter_complex",
           "[0:v][1:v]concat=n=2:v=1:a=0[v];[2:a][3:a][4:a]concat=n=3:v=0:a=1[a]",
           "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-t", "4", "-y", str(out)]
    subprocess.run(cmd, check=True)
    return out


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        cls.video = make_media(cls.dir)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_probe(self):
        a = types.SimpleNamespace(video=str(self.video), out=None, json=True)
        info = C.cmd_probe(a)
        self.assertAlmostEqual(info["duration_s"], 4.0, delta=0.3)
        self.assertEqual(info["width"], 320)
        self.assertTrue(info["has_audio"])

    def test_time_helpers_roundtrip(self):
        for t in (0.0, 5.5, 92.25, 3723.125):
            s = C.hms(t)
            self.assertAlmostEqual(C.parse_t(s), t, places=2)
        self.assertAlmostEqual(C.parse_t("02:00"), 120.0)
        self.assertAlmostEqual(C.parse_t("1:02:03.5"), 3723.5)

    def test_shots_finds_hard_cut(self):
        cuts = C.detect_cuts(str(self.video), 0.15)
        self.assertTrue(any(1.7 <= c <= 2.3 for c in cuts), f"cuts={cuts}")

    def test_frames_at_names_by_timestamp(self):
        d = self.dir / "frames"
        d.mkdir(exist_ok=True)
        a = types.SimpleNamespace(video=str(self.video), out=str(d), at="0.5,3.0",
                                  start="0", end="4", fps=1.0, width=320, q=5, json=False)
        made = C.cmd_frames(a)
        names = sorted(Path(p).name for _, p in made)
        self.assertEqual(names, ["t000000500ms.jpg", "t000003000ms.jpg"])
        for _, p in made:
            self.assertGreater(Path(p).stat().st_size, 100)

    def test_sheet_offset_is_applied_to_filename(self):
        """Regression: -ss resets pts to 0; offset must be added back."""
        d = self.dir / "sheet"
        d.mkdir(exist_ok=True)
        a = types.SimpleNamespace(video=str(self.video), out=str(d), start="0", end="4",
                                  cols=2, rows=2, width=160, fs=12, offset=100.0)
        C.cmd_sheet(a)
        self.assertTrue((d / "sheet_100000_104000.jpg").exists(),
                        "offset not applied to output name")

    def test_pauses_finds_silence_gap(self):
        d = self.dir / "pause"
        d.mkdir(exist_ok=True)
        a = types.SimpleNamespace(video=str(self.video), out=str(d), json=True,
                                  dbfs=-32.0, min_dur=0.45)
        C.cmd_pauses(a)
        gaps = json.loads((d / "pauses.json").read_text(encoding="utf-8"))["gaps"]
        self.assertTrue(any(0.9 <= g["dur"] <= 1.6 for g in gaps), f"gaps={gaps}")

    def test_srt_format(self):
        rows = [{"t0": 0.0, "t1": 1.5, "text": "hello"},
                {"t0": 3661.25, "t1": 3662.0, "text": "world"}]
        srt = C.to_srt(rows)
        self.assertIn("00:00:00,000 --> 00:00:01,500", srt)
        self.assertIn("01:01:01,250 --> 01:01:02,000", srt)

    def test_model_dir_is_on_d(self):
        d = C.model_dir()
        self.assertTrue(d)
        if Path("D:/dev/models/whisper").exists():
            self.assertTrue(d.startswith("D:"), d)

    def test_load_audio_shape(self):
        arr = C.load_audio(str(self.video))
        self.assertEqual(arr.ndim, 1)
        self.assertGreater(len(arr), 16000 * 3)
        self.assertLess(float(abs(arr).max()), 1.001)


if __name__ == "__main__":
    unittest.main(verbosity=2)
