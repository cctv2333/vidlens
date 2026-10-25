#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sound-event tagging: offline behaviour. No network; model optional.

The two inference tests skip themselves when the CED-mini files are absent, so
this file stays green on a fresh checkout.
"""

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import vidlens_audioevents as ae  # noqa: E402


class AudioEventTests(unittest.TestCase):
    def test_default_paths(self):
        model, labels = ae.model_paths()
        self.assertTrue(str(model).endswith("model.int8.onnx"), model)
        self.assertTrue(str(labels).endswith("class_labels_indices.csv"), labels)

    def test_env_override(self):
        import os
        old = os.environ.get("VIDLENS_TAGGING_MODEL")
        try:
            os.environ["VIDLENS_TAGGING_MODEL"] = r"C:\x\y.onnx"
            model, _ = ae.model_paths()
            self.assertEqual(str(model), r"C:\x\y.onnx")
        finally:
            if old is None:
                os.environ.pop("VIDLENS_TAGGING_MODEL", None)
            else:
                os.environ["VIDLENS_TAGGING_MODEL"] = old

    def test_available_is_bool(self):
        self.assertIn(ae.available(), (True, False))

    def test_install_hint_is_actionable(self):
        hint = ae.install_hint()
        for needle in ("model.int8.onnx", "class_labels_indices.csv",
                       "VIDLENS_TAGGING_MODEL", "10.4MB"):
            self.assertIn(needle, hint)

    def test_scan_empty_audio(self):
        r = ae.scan(np.zeros(0, dtype=np.float32))
        self.assertEqual(r["duration"], 0)
        self.assertEqual(r["windows"], [])
        self.assertEqual(r["segments"], [])

    @unittest.skipUnless(ae.available(), "CED-mini model not installed")
    def test_silence_is_recognised(self):
        r = ae.scan(np.zeros(16000 * 10, dtype=np.float32), window=10, hop=5, top_k=3)
        self.assertGreaterEqual(len(r["windows"]), 1)
        names = [e["name"].lower() for e in r["windows"][0]["events"]]
        self.assertTrue(any("silence" in n for n in names), names)

    @unittest.skipUnless(ae.available(), "CED-mini model not installed")
    def test_window_offsets_do_not_drift(self):
        r = ae.scan(np.zeros(int(16000 * 12.5), dtype=np.float32), window=10, hop=5)
        # 12.5 s / win 10 / hop 5 → 0–10 and 5–12.5; the trailing 10–12.5 window is
        # redundant once a window already reaches the end.
        self.assertEqual([w["t0"] for w in r["windows"]], [0.0, 5.0])
        self.assertEqual(r["windows"][-1]["t1"], 12.5)


if __name__ == "__main__":
    unittest.main()
