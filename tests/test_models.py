#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Model registry / whisper completeness / download gate.

These are the failures reported from another machine (2026-10-27): a catalog that
contradicted the downloader, a half-downloaded model that looked installed, and a
second download queuing behind a lock for eight minutes.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import vidlens_models as M  # noqa: E402


class RegistryTests(unittest.TestCase):
    def test_catalog_and_downloader_read_the_same_table(self):
        items = M.catalog()
        self.assertEqual({i["name"] for i in items}, set(M.REGISTRY))
        for item in items:
            kind = M.REGISTRY[item["name"]]["kind"]
            self.assertEqual(item["downloadable"], kind in ("files", "hf"), item["name"])
            self.assertEqual(item["size_mb"], M.REGISTRY[item["name"]]["size_mb"])

    def test_nothing_acquirable_is_manual(self):
        manual = {n for n, v in M.REGISTRY.items() if v["kind"] == "manual"}
        self.assertEqual(set(M.ACQUIRABLE), set(M.REGISTRY) - manual)
        self.assertFalse(set(M.ACQUIRABLE) & manual)

    def test_whisper_base_is_visible_and_acquirable(self):
        names = {i["name"] for i in M.catalog()}
        self.assertIn("whisper-base", names)
        self.assertIn("whisper-base", M.ACQUIRABLE)

    def test_sensevoice_int8_is_listed_and_not_a_download_target(self):
        self.assertIn("sensevoice-int8", {i["name"] for i in M.catalog()})
        self.assertNotIn("sensevoice-int8", M.ACQUIRABLE)
        ok, why = M.acquire("sensevoice-int8", confirm=True)
        self.assertFalse(ok)
        self.assertIn("不由本工具下载", why)


class WhisperFilesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="vl-models-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self._old = M.WHISPER_ROOT
        M.WHISPER_ROOT = self.tmp
        self.addCleanup(lambda: setattr(M, "WHISPER_ROOT", self._old))

    def _make(self, size, files=M.WHISPER_FILES):
        d = M.whisper_dir(size) / "snapshots" / "abc123"
        d.mkdir(parents=True, exist_ok=True)
        for f in files:
            (d / f).write_bytes(b"x" * 8)
        return d

    def test_one_file_is_not_installed(self):
        self._make("tiny", files=("model.bin",))
        self.assertFalse(M.whisper_complete("tiny"))
        self.assertEqual(len(M.whisper_missing("tiny")), 3)

    def test_four_files_is_installed(self):
        self._make("tiny")
        self.assertTrue(M.whisper_complete("tiny"))
        self.assertEqual(M.whisper_missing("tiny"), [])

    def test_empty_file_does_not_count(self):
        d = self._make("tiny", files=("config.json", "tokenizer.json", "vocabulary.txt"))
        (d / "model.bin").write_bytes(b"")
        self.assertFalse(M.whisper_complete("tiny"))

    def test_resolve_falls_back_to_what_is_installed(self):
        self._make("small")
        self.assertEqual(M.resolve_whisper("tiny"), "small")

    def test_resolve_keeps_the_requested_model_when_present(self):
        self._make("tiny")
        self._make("small")
        self.assertEqual(M.resolve_whisper("tiny"), "tiny")

    def test_env_override_is_honoured(self):
        self._make("tiny")
        os.environ["VIDLENS_WHISPER_MODEL"] = "tiny"
        self.addCleanup(os.environ.pop, "VIDLENS_WHISPER_MODEL", None)
        self.assertEqual(M.resolve_whisper(""), "tiny")

    def test_installed_list_is_sorted_largest_first(self):
        self._make("tiny")
        self._make("small")
        self.assertEqual(M.installed_whisper()[:2], ["small", "tiny"])


class DownloadGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="vl-state-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self._old = M.MODEL_ROOT
        M.MODEL_ROOT = self.tmp
        self.addCleanup(lambda: setattr(M, "MODEL_ROOT", self._old))

    def test_second_download_is_refused_instead_of_queued(self):
        lock = M._acquire_lock()
        self.assertTrue(lock.acquire(blocking=False))
        try:
            ok, why = M.acquire("ced-mini", confirm=True)
        finally:
            lock.release()
        self.assertFalse(ok)
        self.assertIn("已有一个下载在进行中", why)
        self.assertIn("status", why)

    def test_state_is_interrupted_when_the_pid_is_gone(self):
        (self.tmp / M.STATE_FILE_NAME).write_text(json.dumps(
            {"status": "running", "name": "whisper-small", "pid": 999_999,
             "updated": "2026-10-27 01:52:50"}), encoding="utf-8")
        st = M.download_state()
        self.assertFalse(st["process_alive"])
        self.assertEqual(st["status"], "interrupted")
        self.assertEqual(st["name"], "whisper-small")

    def test_state_is_idle_without_a_file(self):
        self.assertEqual(M.download_state()["status"], "idle")

    def test_pid_liveness_never_kills_anything(self):
        # On Windows os.kill(pid, 0) TERMINATES the process; the helper must not use it.
        self.assertTrue(M._pid_alive(os.getpid()))
        self.assertFalse(M._pid_alive(0))
        self.assertFalse(M._pid_alive(-1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
