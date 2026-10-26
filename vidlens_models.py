#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local model catalog + hardware recommendation.

No downloads happen here. The AI should show this catalog, ask the user, and
only then download. That is deliberate: the user is tired of surprise downloads.
"""

from __future__ import annotations

import ctypes
import os
import shutil
from pathlib import Path

def default_model_root() -> Path:
    """env -> legacy checkout dir *if it exists* -> per-user data dir.

    The legacy path used to be chosen whenever a D: drive existed, which is true
    on a great many machines that have nothing to do with this project. Resolving
    it here, and only when the directory is really there, keeps this checkout's
    weights findable without handing strangers a path they never created.
    """
    env = os.environ.get("VIDLENS_MODEL_ROOT")
    if env:
        return Path(env).expanduser()
    try:
        import vidlens as core          # local import: keeps the import order free
        return core.models_root()
    except Exception:
        return Path.home() / ".cache" / "vidlens-models"


MODEL_ROOT = default_model_root()
WHISPER_ROOT = Path(os.environ.get("VIDLENS_MODEL_DIR") or (MODEL_ROOT / "whisper"))


def ram_gb() -> float:
    """Total physical RAM in GB; 0.0 if it cannot be read."""
    try:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        st = MEMORYSTATUSEX()
        st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            return round(st.ullTotalPhys / (1024 ** 3), 1)
    except Exception:
        pass
    try:
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024 ** 3), 1)
    except Exception:
        return 0.0


def disk_free_gb(path: Path | None = None) -> float:
    p = path or MODEL_ROOT
    try:
        return round(shutil.disk_usage(str(p.anchor or p)).free / (1024 ** 3), 1)
    except Exception:
        return 0.0


def _installed_whisper(name: str) -> bool:
    return any(WHISPER_ROOT.glob(f"models--Systran--faster-whisper-{name}")) or \
        any(WHISPER_ROOT.glob(f"**/{name}*/*.bin"))


def catalog() -> list[dict]:
    import vidlens_sensevoice as sv

    items = [
        {"name": "sensevoice", "size_mb": 937, "purpose": "ASR + 语种 + 情感 + 音频事件",
         "license": "上游 iic/SenseVoiceSmall", "source": "https://hf-mirror.com/FunAudioLLM/SenseVoiceSmall",
         "installed": sv.available(), "note": "当前默认；本机用 FlashVoice 自带模型"},
        {"name": "sensevoice-int8", "size_mb": 228, "purpose": "同上，体积更小",
         "license": "上游 iic/SenseVoiceSmall", "source": "sherpa-onnx SenseVoice int8 模型包",
         "installed": (MODEL_ROOT / "sensevoice" / "model.int8.onnx").is_file(),
         "note": "弱机优先；用 VIDLENS_SENSEVOICE_MODEL 指过去"},
        {"name": "whisper-small", "size_mb": 484, "purpose": "ASR 回退",
         "license": "MIT", "source": "https://hf-mirror.com/Systran/faster-whisper-small",
         "installed": _installed_whisper("small"), "note": "中文偏繁体；专名需核对"},
        {"name": "whisper-tiny", "size_mb": 75, "purpose": "弱机 ASR 回退",
         "license": "MIT", "source": "https://hf-mirror.com/Systran/faster-whisper-tiny",
         "installed": _installed_whisper("tiny"), "note": "精度低，只适合应急"},
        {"name": "ced-mini", "size_mb": 10, "purpose": "AudioSet 527 类音频事件分类（不是 ASR）",
         "license": "Apache-2.0",
         "source": "https://hf-mirror.com/k2-fsa/sherpa-onnx-ced-mini-audio-tagging-2024-04-19",
         "installed": _ced_installed(),
         "note": "int8 ONNX 10.4MB + 14.7KB 标签；已接（video_soundscape）；"
                 "无 torch 依赖，借用 sherpa-onnx 的 AudioTagging"},
    ]
    return items


def _ced_installed() -> bool:
    try:
        import vidlens_audioevents as ae
        return ae.available()
    except Exception:
        return False


def recommend() -> dict:
    ram = ram_gb()
    cores = os.cpu_count() or 0
    free = disk_free_gb()
    if ram and ram < 4:
        asr = "whisper-tiny"
    elif ram and ram < 8:
        asr = "sensevoice-int8"
    else:
        asr = "sensevoice"
    return {"ram_gb": ram, "cpu_cores": cores, "disk_free_gb": free,
            "recommended_asr": asr,
            "optional_audio": "ced-mini",
            "note": "推荐只是起点；下载前先问用户，绝不自动下。"}
