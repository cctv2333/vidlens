#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SenseVoice backend (sherpa-onnx): local ASR + language + emotion + audio events.

Why this file exists
--------------------
The user already has a SenseVoice ONNX model (937 MB, from FlashVoice). It is
the official sherpa-onnx float32 SenseVoiceSmall export: metadata says
`sense_voice_ctc`, vocab 25055, `iic/SenseVoiceSmall`. sherpa-onnx gives us
feature extraction + CTC decoding for free, and one pass returns:

    text, lang, emotion, event, timestamps, tokens

No cloud, no API key, no second model download. The only extra file is
tokens.txt (308 KB), stored under D:\\dev\\models\\sensevoice.

Environment:
    VIDLENS_SENSEVOICE_MODEL   default: FlashVoice model path
    VIDLENS_SENSEVOICE_TOKENS  default: D:\\dev\\models\\sensevoice\\tokens.txt
    VIDLENS_ASR=whisper        force the old faster-whisper backend
"""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

DEFAULT_MODEL = (os.environ.get("VIDLENS_SENSEVOICE_MODEL")
                 or r"C:\Users\yu\AppData\Roaming\com.flashvoices\models\sense-voice-large.onnx")
DEFAULT_TOKENS = (os.environ.get("VIDLENS_SENSEVOICE_TOKENS")
                  or r"D:\dev\models\sensevoice\tokens.txt")
CHUNK_SECONDS = 20.0
LANGS = ("auto", "zh", "en", "ja", "ko", "yue")

_RECS: dict[str, object] = {}


def _model_path() -> Path:
    return Path(os.environ.get("VIDLENS_SENSEVOICE_MODEL") or DEFAULT_MODEL)


def _tokens_path() -> Path:
    return Path(os.environ.get("VIDLENS_SENSEVOICE_TOKENS") or DEFAULT_TOKENS)


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
        rows.append({"t0": start_s, "t1": end_s, "text": r["text"],
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
    info = {
        "backend": "sensevoice",
        "model": str(_model_path()),
        "duration": round(duration, 3),
        "segments": len([r for r in rows if (r.get("text") or "").strip()]),
        "chunks": len(results),
        "chunk_seconds": chunk_seconds,
        "language": langs.most_common(1)[0][0] if langs else "",
        "language_counts": dict(langs),
        "emotion_counts": dict(emos),
        "event_counts": dict(events),
    }
    return rows, info
