#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lightweight audio rhythm/energy analysis (numpy only, no extra deps).

This is a *rough* tempo estimate, not a professional MIR beat tracker. It is
useful for "is this cut fast/slow, is there music, is the energy rising?" and
is always labelled as heuristic in reports.
"""

from __future__ import annotations

import numpy as np

FRAME = 1024
HOP = 256
MIN_BPM = 40.0
MAX_BPM = 200.0
MAX_SECONDS = 120.0


def analyze_samples(samples, sr: int = 16000, max_seconds: float = MAX_SECONDS) -> dict:
    x = np.asarray(samples, dtype=np.float32).reshape(-1)
    if x.size == 0:
        return {"duration": 0.0, "bpm": 0.0, "confidence": 0.0,
                "energy_db": -120.0, "dynamic_db": 0.0, "silence_ratio": 1.0}
    limit = int(max(1.0, float(max_seconds)) * sr)
    if x.size > limit:
        x = x[:limit]
    duration = x.size / sr
    if x.size < FRAME:
        x = np.pad(x, (0, FRAME - x.size))
    n = 1 + (x.size - FRAME) // HOP
    idx = np.arange(FRAME)[None, :] + HOP * np.arange(n)[:, None]
    frames = x[idx] * np.hanning(FRAME).astype(np.float32)
    spec = np.abs(np.fft.rfft(frames, axis=1))
    # spectral flux: positive changes = onsets
    flux = np.maximum(0.0, np.diff(spec, axis=0)).sum(axis=1)
    env = flux - np.median(flux) if flux.size else flux
    env = np.maximum(env, 0.0)
    if env.size and env.max() > 0:
        env = env / env.max()

    bpm, confidence = 0.0, 0.0
    fps = sr / HOP
    min_lag = max(1, int(round(fps * 60.0 / MAX_BPM)))
    max_lag = max(min_lag + 1, int(round(fps * 60.0 / MIN_BPM)))
    if env.size > max_lag + 2:
        ac = np.correlate(env, env, mode="full")[env.size - 1:]
        region = ac[min_lag:max_lag + 1]
        lags = np.arange(min_lag, max_lag + 1)
        bpms = 60.0 * fps / lags
        if region.size and region.max() > 0:
            # mild prior around 110 BPM; avoids always picking 60/2x tempo
            prior = np.exp(-0.5 * (np.log2(bpms / 110.0) / 0.45) ** 2)
            k = int(np.argmax(region * prior))
            bpm = float(bpms[k])
            confidence = float(region[k] / (np.median(region) + 1e-9))

    rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)
    db = 20.0 * np.log10(rms + 1e-9)
    p10, p90 = np.percentile(db, [10, 90])
    return {
        "duration": round(float(duration), 2),
        "bpm": round(bpm, 1),
        "confidence": round(min(confidence, 99.0), 2),
        "energy_db": round(float(np.mean(db)), 1),
        "dynamic_db": round(float(p90 - p10), 1),
        "silence_ratio": round(float(np.mean(db < -40.0)), 3),
    }


def analyze_file(path, sr: int = 16000) -> dict:
    import vidlens as core

    return analyze_samples(core.load_audio(str(path), sr=sr), sr=sr)
