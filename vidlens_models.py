#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local model catalog, hardware recommendation, and the download link.

Nothing here downloads by itself. Every acquisition is the same shape as the OCR
engine (vidlens_ocr): say the size and the exact directory first, download only
when the caller confirms or has opted into `auto`, and report the resolved path
afterwards. That is deliberate: the user is tired of surprise downloads, and a
caller on another machine cannot guess where this one keeps its weights.

    acquire("ced-mini")                 -> False + a notice (size, dir, how to move)
    acquire("ced-mini", confirm=True)   -> downloads 10MB and says where it landed
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


# --------------------------------------------------------------- acquisition

CED_REPO = "k2-fsa/sherpa-onnx-ced-mini-audio-tagging-2024-04-19"
CED_FILES = (("model.int8.onnx", 10_451_715), ("class_labels_indices.csv", 14_675))
CED_MIRRORS = (f"https://huggingface.co/{CED_REPO}/resolve/main",
               f"https://hf-mirror.com/{CED_REPO}/resolve/main")

# Sizes in MB, measured from the published files. `small` may be fetched without
# a second question when VIDLENS_MODEL_AUTO_DOWNLOAD=auto; a 484MB whisper does
# not get that privilege.
ACQUIRABLE = {
    "ced-mini": {"size_mb": 10, "small": True,
                 "purpose": "AudioSet 527 类声音事件（不是 ASR）"},
    "whisper-tiny": {"size_mb": 75, "small": False, "purpose": "弱机 ASR 回退"},
    "whisper-base": {"size_mb": 145, "small": False, "purpose": "ASR 回退（中等）"},
    "whisper-small": {"size_mb": 484, "small": False, "purpose": "ASR 回退（默认 small）"},
    "sensevoice": {"size_mb": 937, "small": False, "purpose": "ASR + 语种 + 情感（需自带）"},
}


def auto_mode() -> str:
    """ask (default) | auto | off — how far a missing model may be fetched alone."""
    mode = (os.environ.get("VIDLENS_MODEL_AUTO_DOWNLOAD") or "ask").strip().lower()
    return mode if mode in ("ask", "auto", "off") else "ask"


def install_dir(name: str) -> Path:
    """Where `acquire(name)` would write. Derived, never hardcoded."""
    if name == "ced-mini":
        import vidlens_audioevents as ae
        return ae.model_dir()
    if name.startswith("whisper"):
        return WHISPER_ROOT
    return MODEL_ROOT / "sensevoice"


def install_notice(name: str) -> str:
    spec = ACQUIRABLE.get(name)
    if not spec:
        return (f"未知模型 {name!r}。可下载的: " + ", ".join(sorted(ACQUIRABLE)))
    dst = install_dir(name)
    root = MODEL_ROOT
    lines = [
        f"模型 `{name}` 不在本地（{spec['purpose']}；下载约 {spec['size_mb']}MB）。",
        f"- **会装到**：{dst}",
        f"- **要换位置**：设 `VIDLENS_MODEL_ROOT={root.anchor or ''}vidlens-models` "
        "（所有模型一起搬；单个可用 VIDLENS_MODEL_DIR / VIDLENS_TAGGING_DIR 覆盖）",
    ]
    if spec["size_mb"] > 200:
        lines.append("- 这个模型比较大，建议自己决定下不下：`pip install faster-whisper` "
                     "后由它下载，或手动放到上面的目录")
    if name != "sensevoice":
        lines.append(f"- **让我下**：`vidlens_models(action=\"download\", name=\"{name}\", "
                     "confirm=true)`")
        lines.append(f"- **想以后自动下**：设 `VIDLENS_MODEL_AUTO_DOWNLOAD=auto`"
                     f"（现在是 {auto_mode()}；只对 ≤20MB 的模型生效）")
    return "\n".join(lines)


def _download_file(urls, dst: Path, expect: int = 0, progress=None) -> int:
    import urllib.request
    tmp = dst.with_suffix(dst.suffix + ".part")
    last = None
    for base in urls:
        try:
            with urllib.request.urlopen(f"{base}/{dst.name}", timeout=60) as r, \
                    open(tmp, "wb") as f:
                total = int(r.headers.get("Content-Length") or expect or 0)
                done = 0
                while True:
                    chunk = r.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(dst.name, done, total)
            if done == 0:
                raise IOError("empty response")
            tmp.replace(dst)
            return done
        except Exception as e:      # try the next mirror
            last = e
            tmp.unlink(missing_ok=True)
    raise IOError(f"{dst.name}: {type(last).__name__}: {last}")


def acquire(name: str, confirm: bool = False, progress=None) -> tuple[bool, str]:
    """Fetch one model, but only after `confirm` (or the auto policy allows it).

    The gate lives here, not in the caller: a 484MB whisper must not slip through
    because some future tool forgot to ask. `auto` only waives the question for
    small models (≤20MB), which is where surprise downloads are harmless.
    """
    spec = ACQUIRABLE.get(name)
    if not spec:
        return False, f"未知模型 {name!r}。可下载的: " + ", ".join(sorted(ACQUIRABLE))
    allowed = confirm or (auto_mode() == "auto" and spec["small"])
    if not allowed:
        return False, install_notice(name)
    dst_dir = install_dir(name)
    try:
        dst_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return False, f"建目录失败 {dst_dir}: {e}"

    if name == "ced-mini":
        if _ced_installed():
            return True, f"ced-mini 已就绪：{dst_dir}"
        done = 0
        for fname, expect in CED_FILES:
            target = dst_dir / fname
            if target.is_file() and target.stat().st_size > 0:
                done += target.stat().st_size
                continue
            try:
                done += _download_file(CED_MIRRORS, target, expect, progress)
            except Exception as e:
                return False, f"下载失败 {fname}: {e}"
        return True, (f"已下载 ced-mini 到 {dst_dir}（{done / 1048576:.1f}MB，"
                      f"占盘约 {spec['size_mb']}MB）")

    if name.startswith("whisper"):
        size = name.split("-", 1)[1]
        try:
            from faster_whisper import WhisperModel
        except Exception:
            return False, "没有 faster-whisper：`pip install faster-whisper` 后再试"
        try:
            WhisperModel(size, device="cpu", compute_type="int8",
                         download_root=str(WHISPER_ROOT), local_files_only=False)
        except Exception as e:
            return False, f"whisper 下载失败：{type(e).__name__}: {e}"
        return True, f"已下载 whisper-{size} 到 {WHISPER_ROOT}"

    return False, install_notice(name)
