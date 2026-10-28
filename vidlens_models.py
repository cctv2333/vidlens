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


# ---------------------------------------------------------------- the registry
#
# ONE table drives both `action="list"` and `action="download"`. They used to be
# two hand-written lists, so `sensevoice-int8` appeared in the catalog yet was
# rejected as "unknown model", and `whisper-base` was downloadable yet invisible.
# A single source removes that whole class of contradiction.

WHISPER_FILES = ("model.bin", "config.json", "tokenizer.json", "vocabulary.txt")

REGISTRY: dict[str, dict] = {
    "ced-mini": {
        "size_mb": 10, "kind": "files", "small": True,
        "purpose": "AudioSet 527 类声音事件（不是 ASR）", "license": "Apache-2.0",
        "source": "https://hf-mirror.com/k2-fsa/sherpa-onnx-ced-mini-audio-tagging-2024-04-19",
        "note": "int8 ONNX 10.4MB + 14.7KB 标签；已接 video_soundscape"},
    "whisper-tiny": {
        "size_mb": 75, "kind": "hf", "repo": "Systran/faster-whisper-tiny",
        "purpose": "弱机 ASR 回退", "license": "MIT",
        "source": "https://hf-mirror.com/Systran/faster-whisper-tiny",
        "note": "精度低，只适合应急"},
    "whisper-base": {
        "size_mb": 145, "kind": "hf", "repo": "Systran/faster-whisper-base",
        "purpose": "ASR 回退（中等）", "license": "MIT",
        "source": "https://hf-mirror.com/Systran/faster-whisper-base",
        "note": "tiny 太糊、small 太大时的折中"},
    "whisper-small": {
        "size_mb": 484, "kind": "hf", "repo": "Systran/faster-whisper-small",
        "purpose": "ASR 回退（默认）", "license": "MIT",
        "source": "https://hf-mirror.com/Systran/faster-whisper-small",
        "note": "中文偏繁体；专业术语同音错字多，术语密集内容优先看画面"},
    "sensevoice": {
        "size_mb": 937, "kind": "manual",
        "purpose": "ASR + 语种 + 情感 + 音频事件", "license": "上游 iic/SenseVoiceSmall",
        "source": "https://hf-mirror.com/FunAudioLLM/SenseVoiceSmall",
        "note": "当前默认；本机用 FlashVoice 自带模型，工具不代下"},
    "sensevoice-int8": {
        "size_mb": 228, "kind": "manual",
        "purpose": "同上，体积更小", "license": "上游 iic/SenseVoiceSmall",
        "source": "sherpa-onnx SenseVoice int8 模型包",
        "note": "弱机优先；用 VIDLENS_SENSEVOICE_MODEL 指过去"},
}

# Only these can be fetched by `acquire`. `manual` entries are listed so the
# catalog never promises something the downloader refuses.
ACQUIRABLE = {k: v for k, v in REGISTRY.items() if v["kind"] in ("files", "hf")}


def whisper_dir(size: str) -> Path:
    return WHISPER_ROOT / f"models--Systran--faster-whisper-{size}"


def _files_ok(d: Path) -> bool:
    return all((d / f).is_file() and (d / f).stat().st_size > 0 for f in WHISPER_FILES)


def whisper_complete(size: str) -> bool:
    """Every file faster-whisper needs is present and non-empty.

    A half-finished download used to look installed (`models--…` existed) and then
    died at load time with LocalEntryNotFoundError. Files, not directory names.
    """
    base = whisper_dir(size)
    snaps = sorted(base.glob("snapshots/*"))
    if any(_files_ok(s) for s in snaps):
        return True
    return _files_ok(base)


def whisper_missing(size: str) -> list[str]:
    base = whisper_dir(size)
    for s in sorted(base.glob("snapshots/*")) + [base]:
        if s.is_dir():
            miss = [f for f in WHISPER_FILES if not (s / f).is_file()]
            if len(miss) < len(WHISPER_FILES):
                return miss
    return list(WHISPER_FILES)


def installed_whisper() -> list[str]:
    return [s for s in ("large-v3", "medium", "small", "base", "tiny") if whisper_complete(s)]


def resolve_whisper(preferred: str = "") -> str:
    """Pick a model that is actually on disk.

    Order: explicit argument → VIDLENS_WHISPER_MODEL → "small"; if that one is not
    installed, fall back to whatever is (small → base → tiny) instead of failing
    with `LocalEntryNotFoundError` while a perfectly good model sits next door.
    """
    want = (preferred or "").strip().lower()
    if not want or want == "auto":
        want = (os.environ.get("VIDLENS_WHISPER_MODEL") or "small").strip().lower()
    if want in ("tiny", "base", "small", "medium", "large-v3") and whisper_complete(want):
        return want
    chain = [want] + [s for s in ("small", "base", "tiny") if s != want]
    for s in chain:
        if s in ("tiny", "base", "small", "medium", "large-v3") and whisper_complete(s):
            return s
    return want


def _installed_whisper(name: str) -> bool:
    return whisper_complete(name)


def catalog() -> list[dict]:
    import vidlens_sensevoice as sv

    items = []
    for name, spec in REGISTRY.items():
        if name.startswith("whisper"):
            installed = whisper_complete(name.split("-", 1)[1])
        elif name == "ced-mini":
            installed = _ced_installed()
        elif name == "sensevoice":
            installed = sv.available()
        else:                       # sensevoice-int8
            installed = (MODEL_ROOT / "sensevoice" / "model.int8.onnx").is_file()
        items.append({"name": name, "size_mb": spec["size_mb"],
                      "purpose": spec["purpose"], "license": spec["license"],
                      "source": spec["source"], "installed": installed,
                      "downloadable": spec["kind"] in ("files", "hf"),
                      "note": spec["note"]})
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
    spec = REGISTRY.get(name)
    if not spec:
        return (f"未知模型 {name!r}。清单里的: " + ", ".join(sorted(REGISTRY)))
    dst = install_dir(name)
    root = MODEL_ROOT
    if spec["kind"] == "manual":
        return "\n".join([
            f"`{name}`（{spec['purpose']}，约 {spec['size_mb']}MB）**不由本工具下载**。",
            f"- 上游：{spec['source']}",
            f"- 装到：{dst}",
            f"- 装好后可指向它：`VIDLENS_SENSEVOICE_MODEL=<模型文件>` "
            "`VIDLENS_SENSEVOICE_TOKENS=<tokens.txt>`",
            f"- 说明：{spec['note']}",
        ])
    lines = [
        f"模型 `{name}` 不在本地（{spec['purpose']}；下载约 {spec['size_mb']}MB）。",
        f"- **会装到**：{dst}",
        f"- **要换位置**：设 `VIDLENS_MODEL_ROOT={root.anchor or ''}vidlens-models` "
        "（所有模型一起搬；单个可用 `VIDLENS_MODEL_DIR` 覆盖 whisper）",
    ]
    if spec["size_mb"] > 200:
        lines.append("- 这个模型比较大，建议自己决定下不下")
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


STATE_FILE_NAME = "download.state.json"


def _state_path() -> Path:
    try:
        MODEL_ROOT.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return MODEL_ROOT / STATE_FILE_NAME


def _write_state(**kw) -> None:
    try:
        import json
        import time
        kw.setdefault("pid", os.getpid())
        kw.setdefault("updated", time.strftime("%Y-%m-%d %H:%M:%S"))
        _state_path().write_text(json.dumps(kw, ensure_ascii=False, indent=1),
                                 encoding="utf-8")
    except Exception:
        pass


def _pid_alive(pid: int) -> bool:
    """Is that process still running?

    NOT `os.kill(pid, 0)`: on Windows that call is TerminateProcess, i.e. asking
    "are you alive?" would kill the download it was asking about.
    """
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            SYNCHRONIZE = 0x00100000
            h = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
            if not h:
                return False
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def download_state() -> dict:
    """What the last/current download is doing. Survives a client timeout.

    A client that gives up after 30s used to leave the caller with nothing but
    "timeout" while a 484MB fetch was still running and holding a lock. The state
    file answers "is it still going?" without asking the network.
    """
    import json
    p = _state_path()
    if not p.exists():
        return {"status": "idle"}
    try:
        st = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "unknown", "path": str(p)}
    alive = _pid_alive(st.get("pid"))
    st["process_alive"] = alive
    if st.get("status") == "running" and not alive:
        st["status"] = "interrupted"
    return st


_ACQUIRE_LOCK = None


def _acquire_lock():
    """One download at a time, and never block: a second caller gets told why.

    The old behaviour queued behind the Hugging Face file lock for minutes, which
    looked exactly like "network is slow" and produced two parallel downloads of
    the same blob (WinError 32) whenever the caller gave up and retried.
    """
    global _ACQUIRE_LOCK
    if _ACQUIRE_LOCK is None:
        import threading
        _ACQUIRE_LOCK = threading.Lock()
    return _ACQUIRE_LOCK


def acquire(name: str, confirm: bool = False, progress=None) -> tuple[bool, str]:
    """Fetch one model, but only after `confirm` (or the auto policy allows it).

    The gate lives here, not in the caller: a 484MB whisper must not slip through
    because some future tool forgot to ask. `auto` only waives the question for
    small models (≤20MB), which is where surprise downloads are harmless.
    """
    spec = REGISTRY.get(name)
    if not spec:
        return False, f"未知模型 {name!r}。清单里的: " + ", ".join(sorted(REGISTRY))
    if spec["kind"] == "manual":
        return False, install_notice(name)
    allowed = confirm or (auto_mode() == "auto" and spec.get("small"))
    if not allowed:
        return False, install_notice(name)

    lock = _acquire_lock()
    if not lock.acquire(blocking=False):
        st = download_state()
        who = f"{st.get('name')}，pid {st.get('pid')}，{st.get('updated')}" \
            if st.get("status") == "running" else (st.get("name") or "上一次下载")
        return False, (f"已有一个下载在进行中（{who}）。不要并行开第二个——那会把同一个"
                       "文件下两遍、抢同一个锁。等它结束，或先 `vidlens_models(action=\"status\")`"
                       " 看清状态。")
    dst_dir = install_dir(name)
    _write_state(status="running", name=name, dir=str(dst_dir), started=None)
    try:
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
            # Verify the files, not the runtime: sherpa-onnx being absent is a
            # different problem and must not turn a good download into "failed".
            missing = [f for f, _ in CED_FILES
                       if not (dst_dir / f).is_file() or (dst_dir / f).stat().st_size == 0]
            if missing:
                return False, f"下载完成但文件不全：缺 {', '.join(missing)}（{dst_dir}）"
            warn = "" if _ced_installed() else "；注意 sherpa-onnx 未装，分类还跑不了"
            return True, (f"已下载 ced-mini 到 {dst_dir}（{done / 1048576:.1f}MB，"
                          f"占盘约 {spec['size_mb']}MB{warn}）")

        if name.startswith("whisper"):
            return _acquire_whisper(name.split("-", 1)[1], spec, dst_dir)
        return False, install_notice(name)
    finally:
        _write_state(status="done", name=name, dir=str(dst_dir))
        lock.release()


def _acquire_whisper(size: str, spec: dict, dst_dir: Path) -> tuple[bool, str]:
    """Download only the four files faster-whisper reads, into OUR cache dir.

    Two things this deliberately does not do: construct `WhisperModel` (that would
    import av and load half a gigabyte just to fetch files) and accept a partial
    result as success (a directory with one file in it used to count as installed).
    """
    if os.name == "nt":
        # Symlinks need developer mode / admin on Windows. When they fail, the hub
        # writes blobs AND snapshots: double the disk for the same model.
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
    if whisper_complete(size):
        return True, f"whisper-{size} 已就绪：{whisper_dir(size)}"
    try:
        from huggingface_hub import snapshot_download
    except Exception:
        return False, ("没有 huggingface_hub：`pip install huggingface_hub` 后再试"
                       "（faster-whisper 会带它，说明当前环境不完整）")
    try:
        snapshot_download(
            repo_id=spec["repo"],
            cache_dir=str(dst_dir),          # our dir, not HF_HUB_CACHE
            allow_patterns=[f for f in WHISPER_FILES] + ["preprocessor_config.json"],
            max_workers=2,
        )
    except Exception as e:
        miss = whisper_missing(size)
        return False, (f"whisper-{size} 下载失败：{type(e).__name__}: {e}\n"
                       f"- 缓存目录：{dst_dir}\n"
                       f"- 缺文件：{', '.join(miss)}\n"
                       "- 常见原因：网络中断、HF_HUB_CACHE 指到了别的盘、"
                       "或第二个下载在抢同一个锁")
    miss = whisper_missing(size)
    if miss:
        return False, (f"下载结束但**不完整**：缺 {', '.join(miss)}（{dst_dir}）。"
                       "重跑一次同一条命令即可续传；不要手动搬目录充当已安装。")
    total = sum((p.stat().st_size for p in dst_dir.rglob("*") if p.is_file()), 0)
    return True, (f"已下载 whisper-{size} 到 {dst_dir}"
                  f"（{total / 1048576:.1f}MB，4 个必需文件齐全）")
