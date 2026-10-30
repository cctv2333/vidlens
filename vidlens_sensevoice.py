#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SenseVoice backend (sherpa-onnx): local ASR + language + emotion + audio events.

Why this file exists
--------------------
A SenseVoice ONNX model may already be on the machine (the FlashVoice desktop app
ships one; sherpa-onnx models work too). It is the official sherpa-onnx float32
SenseVoiceSmall export: metadata says `sense_voice_ctc`, vocab 25055,
`iic/SenseVoiceSmall`. sherpa-onnx gives us feature extraction + CTC decoding for
free, and one pass returns:

    text, lang, emotion, event, timestamps, tokens

No cloud, no API key, no second model download.

Environment:
    VIDLENS_SENSEVOICE_MODEL   explicit .onnx path (wins)
    VIDLENS_SENSEVOICE_TOKENS  explicit tokens.txt path (wins)
    VIDLENS_MODEL_ROOT         where weights live (see vidlens.models_root)
    VIDLENS_ASR=whisper        force the old faster-whisper backend

No personal path is compiled in. Earlier versions pointed at one developer's
`C:\\Users\\<name>\\AppData\\...`; on any other machine that is just a missing
file, so candidates are probed in order and the first one that exists is used.
"""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path


def candidate_models() -> list:
    """Model paths to probe, best first. Only existing files are ever returned."""
    out: list = []
    env = os.environ.get("VIDLENS_SENSEVOICE_MODEL")
    if env:
        out.append(Path(env).expanduser())
    try:
        import vidlens as core
        root = core.models_root()
    except Exception:
        root = Path(os.environ.get("VIDLENS_MODEL_ROOT") or
                    (Path.home() / ".cache" / "vidlens-models"))
    out += [root / "sensevoice" / "sense-voice-large.onnx",
            root / "sensevoice" / "model.onnx"]
    # The FlashVoice app keeps its copy here on Windows; use it if it is there.
    if os.name == "nt" and os.environ.get("APPDATA"):
        out.append(Path(os.environ["APPDATA"]) / "com.flashvoices" / "models"
                   / "sense-voice-large.onnx")
    return out


def candidate_tokens() -> list:
    out: list = []
    env = os.environ.get("VIDLENS_SENSEVOICE_TOKENS")
    if env:
        out.append(Path(env).expanduser())
    for m in candidate_models():
        out.append(m.parent / "tokens.txt")
    return out


def _first_existing(cands: list, fallback: Path) -> Path:
    for c in cands:
        if c.is_file():
            return c
    return fallback


CHUNK_SECONDS = 20.0
LANGS = ("auto", "zh", "en", "ja", "ko", "yue")

# Sentence terminators and soft breakers. SenseVoice returns one token per CJK
# character, and the token timestamps are the time of that character -- which is
# what lets a 20s chunk become several sentence rows WITHOUT a second decode.
SENT_END = "。！？!?…"
SOFT_END = "，、,;；：:"
MAX_ROW_CHARS = 60

_RECS: dict[str, object] = {}


def _model_path() -> Path:
    return _first_existing(candidate_models(), candidate_models()[0])


def _tokens_path() -> Path:
    return _first_existing(candidate_tokens(), candidate_tokens()[0])


def available() -> bool:
    """True only when sherpa-onnx, the model and the token table all exist."""
    try:
        import sherpa_onnx  # noqa: F401
    except Exception:
        return False
    return _model_path().is_file() and _tokens_path().is_file()


def status() -> dict:
    return {"available": available(), "model": str(_model_path()),
            "tokens": str(_tokens_path())}


def _label(value) -> str:
    return (value or "").strip("<|>").strip()


def _recognizer(lang: str = "auto"):
    """Cache one recognizer per language. Load is ~1.5s; decode is ~0.02 RTF."""
    import sherpa_onnx

    lang = lang if lang in LANGS else "auto"
    if lang in _RECS:
        return _RECS[lang]
    if lang == "auto":
        # from_sense_voice(language="auto") maps to the model's auto token.
        language = "auto"
    else:
        language = lang
    rec = sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=str(_model_path()),
        tokens=str(_tokens_path()),
        num_threads=max(1, min(4, (os.cpu_count() or 4) - 1)),
        sample_rate=16000,
        feature_dim=80,
        language=language,
        use_itn=True,
        debug=False,
        provider="cpu",
    )
    _RECS[lang] = rec
    return rec


def decode_samples(samples, lang: str = "auto") -> dict:
    """Decode a float32 16 kHz mono array into text + rich labels."""
    import numpy as np

    rec = _recognizer(lang)
    stream = rec.create_stream()
    stream.accept_waveform(16000, np.asarray(samples, dtype=np.float32))
    rec.decode_stream(stream)
    r = stream.result
    return {
        "text": (getattr(r, "text", "") or "").strip(),
        "lang": _label(getattr(r, "lang", "")),
        "emotion": _label(getattr(r, "emotion", "")),
        "event": _label(getattr(r, "event", "")),
        "timestamps": list(getattr(r, "timestamps", []) or []),
        "tokens": list(getattr(r, "tokens", []) or []),
    }


def split_sentences(text: str, tokens, ts, base_t0: float, base_t1: float) -> list:
    """Cut one chunk into sentences, timed by per-token timestamps.

    Why this exists: the decoder works in 20-second blocks, so a row used to be
    "whatever was said between 08:00 and 08:20" -- sentences were cut in half at
    block edges and every timecode had 20s granularity. For CJK, SenseVoice emits
    one token per character WITH a timestamp, so the boundary of a sentence is
    known to the character.

    Falls back to the whole chunk when tokens and text do not line up (English BPE,
    or ITN rewriting digits), because a wrong split is worse than a coarse one.
    """
    text = (text or "").strip()
    if not text:
        return []
    usable = (tokens and len(tokens) == len(ts) == len(text)
              and "".join(tokens) == text)
    if not usable:
        return [{"t0": base_t0, "t1": base_t1, "text": text}]

    bounds, start = [], 0
    for i, ch in enumerate(text):
        if ch in SENT_END:
            bounds.append((start, i + 1))
            start = i + 1
        elif ch in SOFT_END and i - start >= MAX_ROW_CHARS:
            bounds.append((start, i + 1))
            start = i + 1
        elif i - start >= MAX_ROW_CHARS * 2:
            bounds.append((start, i + 1))
            start = i + 1
    if start < len(text):
        bounds.append((start, len(text)))

    out = []
    for a, b in bounds:
        seg = text[a:b].strip()
        if not seg:
            continue
        t0 = base_t0 + float(ts[a])
        t1 = base_t0 + float(ts[b]) if b < len(ts) else base_t1
        t1 = min(t1, base_t1)
        out.append({"t0": round(t0, 3), "t1": round(max(t1, t0 + 0.2), 3), "text": seg})
    return out


def _join_rows(rows: list) -> list:
    """Glue a row that ended mid-sentence onto the next one.

    Sentence splitting is per chunk, so the last sentence of a chunk still stops at
    the block edge. One pass over the finished list closes those seams.
    """
    out: list = []
    for r in rows:
        prev_text = (out[-1]["text"] if out else "").strip()
        if prev_text and not prev_text.rstrip().endswith(tuple(SENT_END)):
            prev = out[-1]
            prev["text"] = (prev["text"].rstrip() + (r["text"] or "").lstrip())
            prev["t1"] = max(prev["t1"], r["t1"])
            continue
        out.append(dict(r))
    return out


def transcribe(path, lang: str = "zh", chunk_seconds: float = CHUNK_SECONDS,
               on_progress=None):
    """Return (rows, info) in the same shape as vidlens_web.transcribe.

    Long audio is cut into non-overlapping chunks. A chunk can be a music-only
    segment: its row carries event/emotion even if text is empty, so the brief
    can report BGM/applause/laughter without inventing speech.
    """
    import vidlens as core

    samples = core.load_audio(str(path))
    sr = 16000
    duration = len(samples) / sr
    chunk_seconds = max(5.0, float(chunk_seconds or CHUNK_SECONDS))
    rows = []
    results = []
    if len(samples) == 0:
        return [], {"backend": "sensevoice", "duration": 0.0, "segments": 0,
                    "language": "", "emotion_counts": {}, "event_counts": {}}

    step = max(1, int(chunk_seconds * sr))
    for start in range(0, len(samples), step):
        part = samples[start:start + step]
        if len(part) < sr // 4:  # less than 0.25s: not worth decoding
            break
        r = decode_samples(part, lang=lang)
        results.append(r)
        start_s = round(start / sr, 3)
        end_s = round(min(duration, (start + len(part)) / sr), 3)
        pieces = split_sentences(r["text"], r.get("tokens"), r.get("timestamps"),
                                 start_s, end_s)
        if not pieces:
            pieces = [{"t0": start_s, "t1": end_s, "text": ""}]
        for piece in pieces:
            rows.append({"t0": piece["t0"], "t1": piece["t1"], "text": piece["text"],
                         "track": "speech", "words": [],
                         "lang": r["lang"], "emotion": r["emotion"],
                         "event": r["event"]})
        if on_progress:
            try:
                on_progress(end_s, duration)
            except Exception:
                pass

    langs = Counter(r["lang"] for r in results if r["lang"] and r["lang"] != "nospeech")
    emos = Counter(r["emotion"] for r in results if r["emotion"])
    events = Counter(r["event"] for r in results if r["event"])
    rows = _join_rows(rows)
    info = {
        "backend": "sensevoice",
        "model": str(_model_path()),
        "duration": round(duration, 3),
        "segments": len([r for r in rows if (r.get("text") or "").strip()]),
        "sentences": len(rows),
        "chunks": len(results),
        "chunk_seconds": chunk_seconds,
        "row_format": "sentence",
        "language": langs.most_common(1)[0][0] if langs else "",
        "language_counts": dict(langs),
        "emotion_counts": dict(emos),
        "event_counts": dict(events),
    }
    return rows, info
