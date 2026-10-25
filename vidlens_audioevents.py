#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sound-event tagging (AudioSet 527 classes) via sherpa-onnx + CED-mini.

This is deliberately NOT ASR: it answers "what sounds are in this window",
with probabilities and timecodes. It does not claim to identify actions —
AudioSet has no "drinking water" class, so a swallow is not something this
module can name; "Water", "Chewing, mastication", "Knock", "Tap",
"Wood block", "Chink, clink", "Scrape", "Crumpling, crinkling" are.

Design notes
------------
* Zero new dependencies: sherpa-onnx is already required for SenseVoice and
  does the feature extraction + inference. No torch, no onnxruntime plumbing.
* Lazy load, once per process (~0.15 s, 10.4 MB int8 model).
* CED is clip-level: feed it windows (default 10 s, hop 5 s) and merge the
  per-window labels into spans. Probabilities are multi-label, so keep the
  numbers visible instead of turning them into a boolean "detected".
* A single AudioTagging instance is not thread-safe: one module lock.
* Never downloads. `install_hint()` tells the caller exactly what is missing.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000
MODEL_FILE = "model.int8.onnx"
LABELS_FILE = "class_labels_indices.csv"
MODEL_SIZE_MB = 10.4

DEFAULT_WINDOW = 10.0
DEFAULT_HOP = 5.0
DEFAULT_TOP_K = 8
DEFAULT_MIN_PROB = 0.15
MIN_WINDOW = 2.0
MAX_WINDOW = 30.0
MAX_WINDOWS = 120          # ≈ 20 min of audio at 10 s / 5 s
MAX_SEGMENTS = 24

_LOCK = threading.Lock()
_TAGGER = None
_LOAD_ERROR: str | None = None
LOAD_MS: int | None = None


def model_dir() -> Path:
    """Where the two files live; override with VIDLENS_TAGGING_DIR."""
    env = os.environ.get("VIDLENS_TAGGING_DIR")
    if env:
        return Path(env).expanduser()
    root = os.environ.get("VIDLENS_MODEL_ROOT")
    base = Path(root).expanduser() if root else Path(r"D:\dev\models")
    return base / "audio-tagging" / "ced-mini"


def model_paths() -> tuple[Path, Path]:
    """(model, labels); each can be overridden on its own."""
    m = os.environ.get("VIDLENS_TAGGING_MODEL")
    lab = os.environ.get("VIDLENS_TAGGING_LABELS")
    d = model_dir()
    return (Path(m).expanduser() if m else d / MODEL_FILE,
            Path(lab).expanduser() if lab else d / LABELS_FILE)


def _sherpa():
    try:
        import sherpa_onnx  # noqa: PLC0415 - optional at import time
        return sherpa_onnx
    except Exception:
        return None


def available() -> bool:
    """True when the runtime AND both files exist. Never raises."""
    m, lab = model_paths()
    return _sherpa() is not None and m.is_file() and lab.is_file()


def install_hint() -> str:
    m, lab = model_paths()
    missing = [str(p) for p in (m, lab) if not p.is_file()]
    lines = [
        "# 未安装音频事件模型（CED-mini，约 10.4MB）",
        "",
        "这个能力不是 ASR：它给的是 AudioSet 527 类声音标签（Chewing / Knock / "
        "Wood block / Water / Chink / Scrape …）+ 概率 + 时间码。",
        "",
        f"- 期望目录: `{model_dir()}`",
        f"- 需要文件: `{MODEL_FILE}`（10.4MB）、`{LABELS_FILE}`（14.7KB）",
    ]
    if missing:
        lines.append("- 当前缺失: " + "、".join(f"`{p}`" for p in missing))
    lines += [
        "- 下载（不随包发、不自动下）: 运行 `tools/fetch_sound_model.py`"
        "（在本插件仓库里），或手动从 "
        "https://hf-mirror.com/k2-fsa/sherpa-onnx-ced-mini-audio-tagging-2024-04-19 "
        "取这两个文件",
        "- 自定义位置: `VIDLENS_TAGGING_MODEL` / `VIDLENS_TAGGING_LABELS`",
        "",
        "装好后重试；本进程会懒加载模型（约 0.15s）。",
    ]
    return "\n".join(lines)


def _load():
    global _TAGGER, _LOAD_ERROR, LOAD_MS
    if _TAGGER is not None or _LOAD_ERROR is not None:
        return _TAGGER
    so = _sherpa()
    if so is None:
        _LOAD_ERROR = "sherpa-onnx 未安装（pip install sherpa-onnx）"
        return None
    m, lab = model_paths()
    try:
        t0 = time.time()
        threads = max(1, min(4, os.cpu_count() or 2))
        cfg = so.AudioTaggingConfig(
            model=so.AudioTaggingModelConfig(ced=str(m), num_threads=threads),
            labels=str(lab),
            top_k=DEFAULT_TOP_K,
        )
        _TAGGER = so.AudioTagging(cfg)
        LOAD_MS = int((time.time() - t0) * 1000)
    except Exception as exc:  # noqa: BLE001 - report, never crash the caller
        _LOAD_ERROR = f"{type(exc).__name__}: {exc}"
    return _TAGGER


def tag(samples, top_k: int = DEFAULT_TOP_K) -> list[dict]:
    """Top-k labels for one clip. samples: 16 kHz mono float32 in [-1, 1]."""
    if not available():
        raise RuntimeError(install_hint())
    with _LOCK:
        tagger = _load()
        if tagger is None:
            raise RuntimeError(_LOAD_ERROR or "音频事件模型加载失败")
        stream = tagger.create_stream()
        stream.accept_waveform(SAMPLE_RATE, np.asarray(samples, dtype=np.float32))
        events = tagger.compute(stream, int(top_k))
    return [{"name": str(e.name), "prob": round(float(e.prob), 4), "index": int(e.index)}
            for e in events]


def _segments(windows: list[dict], min_prob: float, hop: float = DEFAULT_HOP) -> list[dict]:
    """Merge windows carrying the same label into spans (gap <= 1.2 × hop)."""
    by_label: dict[str, list[tuple[float, float, float]]] = {}
    for w in windows:
        for ev in w["events"]:
            if ev["prob"] < min_prob:
                continue
            by_label.setdefault(ev["name"], []).append((w["t0"], w["t1"], ev["prob"]))
    spans: list[dict] = []
    gap = max(0.5, float(hop) * 1.2)
    for name, items in by_label.items():
        items.sort()
        cur = None
        for t0, t1, prob in items:
            if cur is not None and t0 <= cur["t1"] + gap:
                cur["t1"] = max(cur["t1"], t1)
                cur["peak"] = max(cur["peak"], prob)
                cur["n"] += 1
            else:
                if cur is not None:
                    spans.append(cur)
                cur = {"label": name, "t0": t0, "t1": t1, "peak": prob, "n": 1}
        if cur is not None:
            spans.append(cur)
    spans.sort(key=lambda s: (-s["peak"], s["t0"]))
    return spans[:MAX_SEGMENTS]


def scan(samples, window: float = DEFAULT_WINDOW, hop: float = DEFAULT_HOP,
         top_k: int = DEFAULT_TOP_K, min_prob: float = DEFAULT_MIN_PROB) -> dict:
    """Slide over the audio, tag each window, merge labels into spans."""
    x = np.asarray(samples, dtype=np.float32)
    duration = len(x) / SAMPLE_RATE if len(x) else 0.0
    win = max(MIN_WINDOW, min(MAX_WINDOW, float(window or DEFAULT_WINDOW)))
    hop = max(1.0, min(win, float(hop or DEFAULT_HOP)))
    result = {
        "duration": round(duration, 3),
        "window": win,
        "hop": hop,
        "min_prob": round(float(min_prob), 3),
        "model": str(model_paths()[0]),
        "load_ms": LOAD_MS,
        "windows": [],
        "segments": [],
        "truncated": False,
    }
    if duration <= 0:
        return result

    # Index-based offsets: accumulating `t += hop` drifts (…, 45.001) and the
    # timecodes are the product, so keep them exact.
    i = 0
    while True:
        t = round(i * hop, 3)
        if t >= duration or len(result["windows"]) >= MAX_WINDOWS:
            if t < duration:
                result["truncated"] = True
            break
        end = round(min(duration, t + win), 3)
        chunk = x[int(t * SAMPLE_RATE): int(end * SAMPLE_RATE)]
        if len(chunk) >= int(0.5 * SAMPLE_RATE):
            events = tag(chunk, top_k)
            kept = [e for e in events if e["prob"] >= min_prob] or events[:1]
            result["windows"].append({"t0": t, "t1": end, "events": kept})
        if end >= duration:
            break
        i += 1

    result["segments"] = _segments(result["windows"], float(min_prob), hop)
    return result
