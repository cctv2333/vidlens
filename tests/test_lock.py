#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cross-process media lock: one out/ directory, several Python processes.

No network. The child process holds the lock while the parent proves it is
refused, then the parent proves it succeeds once the child exits.
"""

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import vidlens_web as web  # noqa: E402

CHILD = textwrap.dedent(
    """
    import sys, time
    from pathlib import Path
    sys.path.insert(0, sys.argv[1])
    from vidlens_web import media_lock
    with media_lock(Path(sys.argv[2]), timeout=15):
        print("locked", flush=True)
        time.sleep(float(sys.argv[3]))
    """
)


class LockTests(unittest.TestCase):
    def test_reentrant_same_thread(self):
        with tempfile.TemporaryDirectory() as td:
            lock = web.media_lock(Path(td), timeout=5)
            with lock:
                with lock:          # same thread: must not deadlock
                    pass
            with lock:              # and it must be released afterwards
                pass

    def test_second_process_is_refused_then_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            child = subprocess.Popen(
                [sys.executable, "-c", CHILD, str(ROOT), td, "2.5"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            try:
                line = child.stdout.readline().strip()
                if line != "locked":          # read stderr only on failure (it blocks)
                    self.fail(child.stderr.read()[-800:])
                with self.assertRaises(TimeoutError):
                    with web.media_lock(Path(td), timeout=1.2):
                        pass
            finally:
                child.wait(timeout=30)
                for stream in (child.stdout, child.stderr):
                    try:
                        stream.close()
                    except Exception:
                        pass
            # child is gone → the lock is free again
            with web.media_lock(Path(td), timeout=5):
                pass

    def test_lock_file_is_inside_the_directory(self):
        with tempfile.TemporaryDirectory() as td:
            with web.media_lock(Path(td), timeout=5):
                self.assertTrue((Path(td) / ".media.lock").exists())


if __name__ == "__main__":
    unittest.main()
