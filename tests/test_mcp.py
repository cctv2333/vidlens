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
from mcp import Client, StdioServerParameters  # noqa: E402

PY = sys.executable
SRV = str(ROOT / "vl_mcp.py")
EXPECTED = {"video_meta", "video_plan", "video_subs", "video_brief", "video_window",
            "video_audio", "video_soundscape", "video_sheet", "video_frames", "video_full",
            "video_job_start", "video_job", "video_visual_scan", "video_comments",
            "vidlens_models", "vidlens_doctor"}


def text_of(result) -> str:
    parts = []
    for item in (getattr(result, "content", None) or []):
        t = getattr(item, "text", None)
        if t:
            parts.append(t)
    return "\n".join(parts)


def run(coro_fn, timeout=180):
    return asyncio.run(asyncio.wait_for(coro_fn(), timeout=timeout))


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
