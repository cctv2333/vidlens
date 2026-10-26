"""画面识字（本地 OCR），专治「没有人声、文字全在画面上」的视频。

引擎：RapidOCR（Apache-2.0，https://github.com/RapidAI/RapidOCR），ONNX Runtime
CPU 推理。PP-OCRv6 的 det/rec/cls 三个模型**随 wheel 一起装**（约 30MB），
所以装好之后完全离线，运行时不再下载任何东西 —— 这对「不自动下模型」的
既有承诺很重要。

**不复制 Umi-OCR 的代码。** Umi-OCR（MIT，hiroi-sora）是 Qt 桌面程序，价值在
「离线 + 多引擎可换 + 批量」这套做法；这里借用的是这个思路，实现是独立写的。
署名与许可证见 NOTICE.md。

为什么单独一个模块：RapidOCR 的依赖（opencv / shapely / pyclipper）比 vidlens
本体重得多，装不上也不该让整个工具起不来，所以全部懒加载，并且 `available()`
先问一句再决定要不要走这条路。
"""

from __future__ import annotations

import difflib
import importlib
import logging
import os
import re
import subprocess
import sys
import sysconfig
import threading
import time
from pathlib import Path

_LOCK = threading.Lock()
_ENGINE = None
_IMPORT_ERROR = ""
_ENGINE_NAME = "rapidocr"

# One `pip install rapidocr` pulls opencv-python-headless with it; measured on
# Windows: ~80MB down, ~150MB on disk (cv2 alone is 112MB). The number is shown
# before downloading, because "80MB到C盘" is something a user may want to refuse.
OCR_PACKAGE = "rapidocr"
OCR_DOWNLOAD_MB = 80
OCR_DISK_MB = 220            # measured: 150MB next to an existing numpy, 220MB
                             # when a custom --target has to carry its own copy
INSTALL_TIMEOUT_S = 900

MIN_SCORE = 0.40           # below this the box is usually texture, not text
MIN_CHARS = 2              # a single character is a icon/logo more often than not
SAME_RATIO = 0.92          # captions differ by a character while they animate in

# Site watermarks and burned-in clocks are text, but not content.
_PLATFORM = re.compile(r"(bilibili|哔哩哔哩|b站|抖音|快手|小红书|西瓜视频|youtube|tiktok)",
                       re.IGNORECASE)
_NOISE = re.compile(
    r"^\d{1,3}:\d{2}(:\d{2})?$"
    r"|^[-—·|/\\]+$",
    re.IGNORECASE,
)
_PUNCT = re.compile(r"[\s\u3000。，、！？；：·…—–\-~,\.!?;:\"'“”‘’()（）\[\]【】《》<>]+")
OVERLAY_MAX_CHARS = 24      # a watermark is short; a caption that repeats is rare
OVERLAY_MIN_FRAMES = 3
OVERLAY_SHARE = 0.4         # …and has to show up in most sampled frames
DIAGRAM_MIN_LINES = 6       # a dense frame: chart legend, UI panel, diagram
DIAGRAM_MAX_CJK = 0.45      # …and mostly not Chinese, unlike a caption
DIAGRAM_MIN_CAPTION_CHARS = 6   # a real sentence among the labels is this long
DIAGRAM_MIN_CAPTION_CJK = 4     # …and carries actual Chinese words


def available() -> tuple[bool, str]:
    """(是否可用, 原因)。原因在装不上时给人看，不要抛异常。"""
    global _IMPORT_ERROR
    try:
        import rapidocr  # noqa: F401
    except Exception as e:              # noqa: BLE001 - any failure means "unavailable"
        _IMPORT_ERROR = f"{type(e).__name__}: {e}"
        return False, _IMPORT_ERROR
    return True, ""


def install_target() -> str:
    """Where a `pip install` would put it. Override with VIDLENS_OCR_TARGET.

    Default is this interpreter's own site-packages — on Windows that is usually
    the C: drive, which is exactly the thing a user may want to move. Setting
    VIDLENS_OCR_TARGET installs into that directory instead and puts it on
    sys.path, so nothing else has to change.
    """
    custom = (os.environ.get("VIDLENS_OCR_TARGET") or "").strip()
    if custom:
        return str(Path(custom).expanduser())
    try:
        return sysconfig.get_paths().get("purelib") or ""
    except Exception:
        return ""


def install_where() -> str:
    """The directory the engine is actually importable from (after a successful install)."""
    try:
        import rapidocr
        return str(Path(rapidocr.__file__).resolve().parent)
    except Exception:
        return ""


def install(auto: bool = False) -> tuple[bool, str]:
    """Run pip for the optional engine. Returns (ok, human readable report).

    Never raises and never writes to stdout: this runs inside a stdio MCP server.
    `auto` only affects the wording (whether a person asked or a caller passed
    install=true) — the decision to call this at all is made by the caller.
    """
    target = install_target()
    custom = bool((os.environ.get("VIDLENS_OCR_TARGET") or "").strip())
    cmd = [sys.executable, "-m", "pip", "install", "--no-input",
           "--disable-pip-version-check", "-q", OCR_PACKAGE]
    if custom and target:
        cmd += ["--target", target]
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=INSTALL_TIMEOUT_S)
    except Exception as e:              # no pip, no network, timeout
        return False, f"下载失败：{type(e).__name__}: {e}"
    took = time.time() - t0
    if proc.returncode != 0:
        tail = ((proc.stderr or "") + (proc.stdout or "")).strip().splitlines()[-3:]
        return False, f"pip 退出码 {proc.returncode}：{' / '.join(tail)[:400]}"
    if custom and target:
        if target not in sys.path:
            sys.path.insert(0, target)
        importlib.invalidate_caches()
    ok, why = available()
    if not ok:
        return False, f"装完了但导入仍然失败：{why[:200]}"
    return True, (f"已装 {OCR_PACKAGE} 到 {install_where() or target}"
                  f"（下载约 {OCR_DOWNLOAD_MB}MB，用掉 {took:.0f}s）")


def auto_mode() -> str:
    """ask (default) | auto | off — how far `video_ocr` may go on its own."""
    mode = (os.environ.get("VIDLENS_OCR_AUTO_INSTALL") or "ask").strip().lower()
    return mode if mode in ("ask", "auto", "off") else "ask"


def notice(python: str | None = None) -> str:
    """Everything a person needs before deciding: size, location, how to move it."""
    target = install_target() or "（本解释器的 site-packages）"
    py = python or sys.executable
    mode = auto_mode()
    lines = [
        f"本地 OCR 还没装（可选功能：下载约 {OCR_DOWNLOAD_MB}MB，占盘 150–{OCR_DISK_MB}MB，"
        "自选目录要自带 numpy 时偏大）。",
        f"- **会装到**：{target}",
        "- **要换盘/换目录**：设环境变量 `VIDLENS_OCR_TARGET=D:\\vidlens\\ocr` 再调用一次，"
        "就装到那里（该目录会自动加入 import 路径，不写系统目录）",
    ]
    if mode == "off":
        lines.append(f"- **当前是 off 模式**：自己装 `\"{py}\" -m pip install {OCR_PACKAGE}`")
    else:
        lines.append("- **让我装**：再调用一次 `video_ocr(..., install=true)`，"
                     f"我会先复述这句话再开始下载（约 {OCR_DOWNLOAD_MB}MB，几十秒）")
        lines.append(f"- **想以后自动装**：设 `VIDLENS_OCR_AUTO_INSTALL=auto`"
                     f"（现在是 {mode}）；自己装也行：`\"{py}\" -m pip install {OCR_PACKAGE}`")
    return "\n".join(lines)


def engine_name() -> str:
    return _ENGINE_NAME


def _engine():
    """Lazy, once. Model load is ~1s; keeping it warm matters for batch frames."""
    global _ENGINE
    with _LOCK:
        if _ENGINE is None:
            # RapidOCR logs INFO per call to stderr. Harmless for stdio MCP, but it
            # pollutes the bridge log on every frame; ask for errors only.
            for name in ("RapidOCR", "rapidocr"):
                logging.getLogger(name).setLevel(logging.ERROR)
            from rapidocr import RapidOCR
            _ENGINE = RapidOCR()
        return _ENGINE


def normalize(text: str) -> str:
    return _PUNCT.sub("", text or "").lower()


def is_noise(text: str, score: float = 1.0) -> bool:
    if score < MIN_SCORE:
        return True
    t = (text or "").strip()
    if not t or len(normalize(t)) < MIN_CHARS:
        return True
    if _NOISE.search(t):
        return True
    # "折光AI1996 bilibili" — a platform name inside a short line is the watermark,
    # not the caption; a long line that merely mentions B 站 is real content.
    return bool(_PLATFORM.search(t)) and len(normalize(t)) <= OVERLAY_MAX_CHARS


def overlay_texts(frames: list[dict]) -> set[str]:
    """Short strings that appear in most frames: watermarks, logos, static UI.

    A caption moves; an overlay does not. Counting occurrences across the sample
    separates them without needing a per-site template.
    """
    if not frames:
        return set()
    from collections import Counter
    counts: Counter = Counter()
    for f in frames:
        seen = {normalize(line["text"]) for line in f.get("lines") or []}
        for key in seen:
            if key:
                counts[key] += 1
    need = max(OVERLAY_MIN_FRAMES, int(OVERLAY_SHARE * len(frames)))
    return {k for k, c in counts.items() if c >= need and len(k) <= OVERLAY_MAX_CHARS}


def ocr_image(path: str | Path) -> list[dict]:
    """One picture -> [{"text","score"}] in the engine's reading order."""
    res = _engine()(str(path))
    txts = getattr(res, "txts", None) or ()
    scores = getattr(res, "scores", None) or ()
    out: list[dict] = []
    for i, raw in enumerate(txts):
        text = " ".join(str(raw).split())
        if not text:
            continue
        score = float(scores[i]) if i < len(scores) else 0.0
        out.append({"text": text, "score": round(score, 3)})
    return out


def same_caption(a: str, b: str) -> bool:
    """Two frames of the same caption, possibly mid-animation."""
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if abs(len(na) - len(nb)) > 2:
        return False
    return difflib.SequenceMatcher(None, na, nb).ratio() >= SAME_RATIO


def merge_captions(frames: list[dict], *, gap_tolerance: float = 0.0) -> list[dict]:
    """Collapse a caption that persists over several frames into one timed block.

    `frames` is [{"t": seconds, "lines": [{"text","score"}]}]. Static text stays on
    screen for many sampled frames; printing it once per frame would turn a 12-frame
    sample into 40 near-identical lines and hide the ones that actually changed.
    """
    blocks: list[dict] = []
    for f in frames:
        t = float(f.get("t") or 0.0)
        for line in f.get("lines") or []:
            text = line["text"]
            if blocks and same_caption(blocks[-1]["text"], text) \
                    and t - blocks[-1]["t1"] <= gap_tolerance + 1e-9:
                b = blocks[-1]
                b["t1"] = max(b["t1"], t)
                b["frames"] += 1
                b["score"] = max(b["score"], line["score"])
            elif blocks and same_caption(blocks[-1]["text"], text):
                # Same words but a gap in between: the caption came back.
                blocks[-1]["t1"] = max(blocks[-1]["t1"], t)
                blocks[-1]["frames"] += 1
            else:
                blocks.append({"text": text, "t0": t, "t1": t,
                               "frames": 1, "score": line["score"]})
    return blocks


def cjk_count(text: str) -> int:
    return sum(1 for ch in normalize(text) if "\u4e00" <= ch <= "\u9fff")


def cjk_ratio(text: str) -> float:
    core = normalize(text)
    if not core:
        return 0.0
    cjk = sum(1 for ch in core if "\u4e00" <= ch <= "\u9fff")
    return cjk / len(core)


def looks_like_diagram(lines: list[dict]) -> bool:
    """Many short boxes and little Chinese = a chart, a UI panel, a diagram.

    The Transformer diagram in the test video produced 15 boxes ("Softmax",
    "Add & Norm", …). They are real on-screen text, but they are not narration and
    must not be merged into the caption list as if the video had said them.
    """
    if len(lines) < DIAGRAM_MIN_LINES:
        return False
    joined = " ".join(line["text"] for line in lines)
    return cjk_ratio(joined) < DIAGRAM_MAX_CJK


def ocr_frames(frames: list[dict]) -> dict:
    """OCR each {"t","path"} frame and merge. Returns blocks + dropped count."""
    done: list[dict] = []
    dropped = 0
    for f in frames:
        p = f.get("path")
        if not p or not Path(p).exists():
            continue
        lines = ocr_image(p)
        done.append({"t": float(f.get("t") or 0.0), "lines": lines})

    # Two-pass: the second pass knows which short strings repeat in most frames,
    # which is what a watermark is and what a caption is not.
    overlay = overlay_texts(done)
    kept: list[dict] = []
    for f in done:
        keep = []
        for line in f["lines"]:
            if normalize(line["text"]) in overlay or is_noise(line["text"], line["score"]):
                dropped += 1
            else:
                keep.append(line)
        kept.append({"t": f["t"], "lines": keep})

    captions, diagram = [], []
    for f in kept:
        if not looks_like_diagram(f["lines"]):
            if f["lines"]:
                captions.append(f)
            continue
        # A busy frame can still carry one real caption ("重建巴别塔的图" next to a
        # diagram's labels), so split line by line instead of discarding the frame.
        cap = [ln for ln in f["lines"]
               if cjk_count(ln["text"]) >= DIAGRAM_MIN_CAPTION_CJK
               and len(normalize(ln["text"])) >= DIAGRAM_MIN_CAPTION_CHARS]
        rest = [ln for ln in f["lines"] if ln not in cap]
        if cap:
            captions.append({"t": f["t"], "lines": cap})
        if rest:
            diagram.append({"t": f["t"],
                            "text": " · ".join(ln["text"] for ln in rest)})
    return {"frames": captions, "blocks": merge_captions(captions),
            "diagram": diagram, "dropped": dropped, "overlay": len(overlay),
            "recognized": sum(len(f["lines"]) for f in done)}


def timestamps(dur: float, n: int, t0: float = 0.0, t1: float | None = None) -> list[float]:
    """n evenly spread points inside [t0, t1) — slides need the whole window."""
    lo = max(0.0, float(t0))
    hi = float(t1 if t1 is not None else dur) or 0.0
    n = max(1, int(n))
    if hi <= lo:
        return [lo]
    span = hi - lo
    step = span / n
    return [round(lo + step * (i + 0.5), 2) for i in range(n)]
