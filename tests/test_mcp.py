#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MCP-level regression tests: real handshake over stdio, no network needed.

Network-dependent assertions are skipped unless VIDLENS_NET_TESTS=1.
"""

import asyncio
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# `mcp` is a hard dependency of the server but an OPTIONAL one for the test run:
# a machine that only has yt-dlp + ffmpeg should still be able to run the other
# 200+ tests instead of dying on this import.
try:
    from mcp import Client, StdioServerParameters  # noqa: E402
    HAVE_MCP = True
except Exception as _e:  # pragma: no cover - depends on the environment
    Client = StdioServerParameters = None
    HAVE_MCP = False
    print(f"[skip] mcp SDK not installed ({_e}); MCP tests will be skipped",
          file=sys.stderr)

NEEDS_MCP = unittest.skipUnless(HAVE_MCP, "需要 mcp SDK：pip install mcp")

PY = sys.executable
SRV = str(ROOT / "vl_mcp.py")
EXPECTED = {"video_meta", "video_plan", "video_subs", "video_brief", "video_window",
            "video_watch", "video_audio", "video_soundscape", "video_sheet",
            "video_frames", "video_full", "video_job_start", "video_job",
            "video_visual_scan", "video_ocr", "video_comments", "vidlens_models",
            "vidlens_doctor"}


def text_of(result) -> str:
    parts = []
    for item in (getattr(result, "content", None) or []):
        t = getattr(item, "text", None)
        if t:
            parts.append(t)
    return "\n".join(parts)


def run(coro_fn, timeout=180):
    return asyncio.run(asyncio.wait_for(coro_fn(), timeout=timeout))


@NEEDS_MCP
class McpTests(unittest.TestCase):
    def _client(self):
        env = dict(os.environ)
        env.update({"PYTHONIOENCODING": "utf-8", "HF_HUB_DISABLE_XET": "1"})
        return Client(StdioServerParameters(command=PY, args=[SRV], env=env))

    def test_handshake_lists_all_tools(self):
        async def go():
            async with self._client() as c:
                tools = await c.list_tools()
                return sorted(t.name for t in tools.tools)
        names = run(go)
        self.assertEqual(set(names), EXPECTED, f"got {names}")

    def test_tool_schemas_have_descriptions(self):
        async def go():
            async with self._client() as c:
                return await c.list_tools()
        tools = run(go)
        for t in tools.tools:
            self.assertTrue(t.description and len(t.description) > 10, t.name)
            dump = t.model_dump() if hasattr(t, "model_dump") else {}
            schema = dump.get("input_schema") or dump.get("inputSchema") or {}
            self.assertEqual(schema.get("type"), "object", t.name)

    def test_full_fetch_is_guarded(self):
        async def go():
            async with self._client() as c:
                return await c.call_tool("video_full", {"url": "https://example.com/x"})
        r = run(go)
        self.assertIn("拒绝", text_of(r))

    def test_bad_url_returns_error_not_crash(self):
        async def go():
            async with self._client() as c:
                return await c.call_tool("video_meta", {"url": "https://example.com/"})
        r = run(go)
        self.assertIn("ERROR", text_of(r))

    def test_frames_requires_at_least_one_time(self):
        async def go():
            async with self._client() as c:
                return await c.call_tool("video_frames", {"url": "https://example.com/x", "at": []})
        r = run(go)
        self.assertIn("ERROR", text_of(r))

    def test_comments_rejects_non_bilibili(self):
        async def go():
            async with self._client() as c:
                return await c.call_tool("video_comments",
                                         {"url": "https://youtube.com/watch?v=abc"})
        r = run(go)
        self.assertIn("B 站", text_of(r))

    @unittest.skipUnless(os.environ.get("VIDLENS_NET_TESTS") == "1", "set VIDLENS_NET_TESTS=1")
    def test_real_meta_over_mcp(self):
        async def go():
            async with self._client() as c:
                return await c.call_tool("video_meta",
                                         {"url": "https://www.bilibili.com/video/BV1cVn86BEwd/"})
        txt = text_of(run(go))
        self.assertIn("时长", txt)
        self.assertNotIn("ERROR", txt)


DEMO = ROOT / "demo" / "meeting.mp4"


@NEEDS_MCP
class LocalFileTests(unittest.TestCase):
    """本地路径要能穿过 MCP：不是 URL，也不该被当成 URL。"""

    def _client(self):
        env = dict(os.environ)
        env.update({"PYTHONIOENCODING": "utf-8", "HF_HUB_DISABLE_XET": "1"})
        return Client(StdioServerParameters(command=PY, args=[SRV], env=env))

    @unittest.skipUnless(DEMO.is_file(), "demo/meeting.mp4 不在")
    def test_local_meta_over_mcp(self):
        async def go():
            async with self._client() as c:
                return await c.call_tool("video_meta", {"url": str(DEMO)})
        txt = text_of(run(go))
        self.assertIn("本地文件", txt)
        self.assertNotIn("ERROR", txt)
        self.assertNotIn("url scheme", txt)

    @unittest.skipUnless(DEMO.is_file(), "demo/meeting.mp4 不在")
    def test_local_subs_says_no_platform_captions(self):
        async def go():
            async with self._client() as c:
                return await c.call_tool("video_subs", {"url": str(DEMO)})
        self.assertIn("本地文件", text_of(run(go)))

    def test_subs_output_is_capped(self):
        import shutil
        import tempfile
        from unittest import mock
        sys.path.insert(0, str(ROOT))
        import vl_mcp  # noqa: E402
        d = Path(tempfile.mkdtemp(prefix="vl-subs-"))
        self.addCleanup(shutil.rmtree, d, True)
        rows = [{"t0": float(i), "t1": float(i) + 1, "text": "字" * 300} for i in range(200)]
        with mock.patch.object(vl_mcp, "_dir", lambda url: ({"duration": 300.0}, d)), \
                mock.patch.object(vl_mcp.web, "download_subs", lambda *a, **k: (rows, "human.zh.vtt")):
            out = vl_mcp.video_subs("https://example.com/x", limit=200)
        self.assertLessEqual(len(out), vl_mcp.MAX_SUB_CHARS + 1200, len(out))
        self.assertIn("另有", out)

    def test_drop_temp_never_deletes_the_source(self):
        import shutil
        import tempfile
        sys.path.insert(0, str(ROOT))
        import vl_mcp  # noqa: E402
        tmp = Path(tempfile.mkdtemp(prefix="vl-drop-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        work = tmp / "work.mp4"
        src = tmp / "src.mp4"
        work.write_bytes(b"x" * 16)
        src.write_bytes(b"x" * 16)
        vl_mcp._drop_temp(work)             # 工作副本：删
        vl_mcp._drop_temp(src, str(src))    # 用户文件：留
        self.assertFalse(work.exists())
        self.assertTrue(src.exists())


@NEEDS_MCP
class OutputBudgetTests(unittest.TestCase):
    """Caps must actually cap. `tail=0` used to mean "return everything unchanged"."""

    def _mcp(self):
        sys.path.insert(0, str(ROOT))
        import vl_mcp  # noqa: E402
        return vl_mcp

    def test_fit_with_zero_tail_still_truncates(self):
        m = self._mcp()
        self.assertEqual(len(m._fit(["x" * 5000], 100, tail=0)), 100)

    def test_fit_keeps_the_last_line(self):
        m = self._mcp()
        out = m._fit(["x" * 5000, "COST LINE"], 600, tail=1)
        self.assertTrue(out.endswith("COST LINE"), out[-40:])
        self.assertLessEqual(len(out), 700)

    def test_ocr_budget_really_bounds_the_output(self):
        m = self._mcp()
        lines = ["- `00:00.000` " + "字" * 200 for _ in range(60)]
        lines.append("COST")
        out = m._fit(lines, m.MAX_OCR_CHARS, tail=1)
        self.assertLessEqual(len(out), m.MAX_OCR_CHARS + 60)
        self.assertIn("略去", out)

    def test_full_download_failure_explains_itself(self):
        import shutil
        import tempfile
        from unittest import mock
        m = self._mcp()
        d = Path(tempfile.mkdtemp(prefix="vl-full-"))
        self.addCleanup(shutil.rmtree, d, True)
        with mock.patch.object(m, "_dir", lambda url: ({"duration": 10.0}, d)), \
                mock.patch.object(m.web, "run_yt",
                                  lambda *a, **k: (1, "", "ERROR: Video unavailable in your country")):
            out = m.video_full("https://example.com/x", confirm=True)
        self.assertIn("Video unavailable", out)


    def test_error_codes_are_stable(self):
        m = self._mcp()
        cases = {
            "could not find chrome cookies database": "E_AUTH",
            "No module named 'tokenizers'": "E_DEP",
            'Unsupported url scheme: "d"': "E_URL",
            "[iqiyi] Can't find any video": "E_SOURCE",
            "Connection timed out": "E_TIMEOUT",
            "读不出时长：a.mp4": "E_MEDIA",
            "something odd": "E_OTHER",
        }
        for msg, want in cases.items():
            self.assertEqual(m._code(msg), want, msg)
            self.assertTrue(m._fail(msg).startswith(f"ERROR[{want}]"), msg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
