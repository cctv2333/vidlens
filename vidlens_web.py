#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vidlens_web - fetch the minimum bytes needed to understand a public video.

Rules baked in (do not remove):
  1. PUBLIC ONLY. No login walls, no paywalls, no captcha solving, no cookie theft.
     If the site says "sign in", we stop and say so.
  2. MINIMUM BYTES. metadata (0) -> platform subtitles (0) -> audio only (~7MB/7min)
     -> 20s sections (0.9MB) -> full file only with --full.
  3. POLITE PACING. sleep between requests, retries with backoff, one video per call.
     We are not a crawler. We look like a person who waits.
  4. HOSTILE TEXT. Titles/descriptions/subtitles go through vidlens_sanitize before
     they touch a file or a summary.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import types
from collections import Counter
from pathlib import Path

import vidlens_ads as ads_mod
import vidlens_sanitize as S

POLITE = [
    "--no-warnings", "--no-color", "--no-playlist", "--no-progress",
    "--socket-timeout", "20", "--retries", "2", "--fragment-retries", "2",
    "--sleep-requests", "0.6", "--sleep-interval", "1.0", "--max-sleep-interval", "3.0",
]

# Chinese first, then English. `zh.*` also catches zh-Hans / zh-Hant / ai-zh.
DEFAULT_SUB_LANGS = ("zh-Hans,zh-CN,zh,zh-Hant,en,en-orig,zh.*,en.*,"
                     "ai-zh,ai-en,ai-ja,ai-ko,ai-yue,ai-.*")
MIN_AUDIO_BYTES = 100 * 1024
MAX_AUDIO_MB = 200.0
BYTES_PER_MB = 1024 * 1024
DEFAULT_CHAPTER_WINDOW = 300.0
MAX_BRIEF_CHAPTERS = 12
MAX_LOW_WORDS = 25
MAX_TRANSCRIPT_LINES = 500


def cookie_args() -> list[str]:
    """Optional cookie source for sites that need anonymous/login cookies.

    We never bundle or steal cookies. The user opts in through the environment:
      VIDLENS_COOKIES=/path/to/cookies.txt
      VIDLENS_COOKIES_FROM_BROWSER=chrome   (or edge / firefox / chromium)
    """
    path = os.environ.get("VIDLENS_COOKIES")
    browser = os.environ.get("VIDLENS_COOKIES_FROM_BROWSER")
    if path:
        return ["--cookies", path]
    if browser:
        return ["--cookies-from-browser", browser]
    return []


def cookie_hint(err: str) -> str:
    """Append an actionable hint when yt-dlp says cookies are required."""
    low = (err or "").lower()
    if "fresh cookies" in low or "cookies are needed" in low or "cookies-from-browser" in low:
        return ("；此站需要 cookie（匿名或登录）。可设 "
                "VIDLENS_COOKIES_FROM_BROWSER=chrome（或 edge/firefox），"
                "或 VIDLENS_COOKIES=path\\cookies.txt 后重试")
    return ""


def sub_langs_for(lang: str) -> str:
    """Subtitle language preference for the requested ASR language."""
    lang = (lang or "").strip()
    if lang and lang not in ("zh", "auto"):
        return f"{lang},{lang}.*,{DEFAULT_SUB_LANGS}"
    return DEFAULT_SUB_LANGS


def core():
    import vidlens as c
    return c


def out_root() -> Path:
    env = os.environ.get("VIDLENS_OUT")
    if env:
        return Path(env)
    return core().project_root() / "out"


# ------------------------------------------------------- cross-process serialisation
#
# One DSH session, the MCP server and a plugin bridge are SEPARATE Python
# processes. threading.Lock cannot see across them, so two of them could write
# the same out/<id>/ at once. This adds one machine-wide advisory file lock on
# top of a re-entrant in-process lock; the project already serialises every
# download through one "media mouth", so the same rule now holds across
# processes.

DEFAULT_LOCK_TIMEOUT = 900.0


class CrossProcessLock:
    """Re-entrant in-process lock plus one exclusive file lock per path."""

    def __init__(self, path: Path, timeout: float | None = None):
        self.path = Path(path)
        self.timeout = (float(os.environ.get("VIDLENS_LOCK_TIMEOUT", DEFAULT_LOCK_TIMEOUT))
                        if timeout is None else float(timeout))
        self._rlock = threading.RLock()
        self._depth = 0
        self._fh = None

    def _acquire_file(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+b")
        if os.name == "nt" and fh.tell() == 0 and self.path.stat().st_size == 0:
            fh.write(b"0")
            fh.flush()
        deadline = time.time() + max(1.0, self.timeout)
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._fh = fh
                return
            except OSError:
                if time.time() >= deadline:
                    fh.close()
                    raise TimeoutError(
                        f"另一个 vidlens 进程正在处理媒体（锁 {self.path}），"
                        f"等了 {int(self.timeout)}s。可设 VIDLENS_LOCK_TIMEOUT 调整。")
                time.sleep(0.25)

    def _release_file(self) -> None:
        fh, self._fh = self._fh, None
        if fh is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            fh.close()
        except Exception:
            pass

    def __enter__(self):
        self._rlock.acquire()
        if self._depth == 0:
            try:
                self._acquire_file()
            except BaseException:
                self._rlock.release()
                raise
        self._depth += 1
        return self

    def __exit__(self, *exc):
        self._depth -= 1
        if self._depth == 0:
            self._release_file()
        self._rlock.release()
        return False


def media_lock(root: Path | None = None, timeout: float | None = None) -> CrossProcessLock:
    return CrossProcessLock((root or out_root()) / ".media.lock", timeout=timeout)


def _ytdlp_bin():
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        sys.exit("yt-dlp not installed: pip install yt-dlp")
    return [sys.executable, "-m", "yt_dlp"]


def run_yt(args, timeout=900):
    cmd = _ytdlp_bin() + POLITE + cookie_args() + args
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    return p.returncode, p.stdout or "", p.stderr or ""


def is_login_wall(err: str) -> bool:
    low = (err or "").lower()
    keys = ("login", "sign in", "signin", "premium", "members only", "需要登录",
            "大会员", "付费", "captcha", "verify you are human", "not available in your country")
    return any(k in low for k in keys)


# ------------------------------------------------------------------ metadata

def check_meta(raw) -> str | None:
    """Return an error string if the extractor gave us a useless page.
    yt-dlp can 'succeed' on a deleted/blocked video with a near-empty dict."""
    if not isinstance(raw, dict):
        return "no json object"
    if not raw.get("id"):
        return "missing id"
    if not raw.get("title"):
        return "missing title (deleted / blocked / region-locked?)"
    if not raw.get("duration") and raw.get("live_status") not in ("is_live", "is_upcoming"):
        return "missing duration (not a playable video)"
    return None


def _sub_keys(raw: dict | None) -> list[str]:
    """Real caption tracks only; danmaku/live chat are not readable subtitles."""
    if not isinstance(raw, dict):
        return []
    return sorted(k for k in raw
                  if k.lower() not in ("danmaku", "live_chat"))


MUSIC_HINT_RE = re.compile(
    r"(?:BGM|背景音乐|配乐|音乐|歌曲|歌名|Music|Song)\s*[:：]\s*([^\n]{1,100})",
    re.I)
MUSIC_BRACKET_RE = re.compile(r"《([^》]{1,80})》")


def music_hints(meta: dict) -> list[str]:
    """Cheap metadata-only music clues; never listens to the audio."""
    desc = str(meta.get("description") or "")
    out = []
    for m in MUSIC_HINT_RE.finditer(desc):
        val = m.group(1).strip(" 　-—|《》")
        if val:
            out.append(val)
    for m in MUSIC_BRACKET_RE.finditer(desc):
        out.append(m.group(1).strip(" 　《》"))
    seen, uniq = set(), []
    for x in out:
        if x and x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq[:8]


def fetch_meta(url: str) -> tuple[dict, list[dict]]:
    rc, out, err = run_yt(["-J", "--skip-download", url])
    if rc != 0 or not out.strip():
        if is_login_wall(err):
            raise SystemExit("STOP: this page needs a login / paid account. We do not bypass that."
                             + cookie_hint(err))
        raise SystemExit(f"meta failed rc={rc}: {err.strip()[:220]}{cookie_hint(err)}")
    raw = json.loads(out[out.find("{"):])
    bad = check_meta(raw)
    if bad:
        raise SystemExit(f"STOP: unusable page -> {bad}. 不继续，以免把垃圾当素材。")
    threats = []
    fields = {
        "id": raw.get("id"),
        "title": raw.get("title"),
        "uploader": raw.get("uploader") or raw.get("channel"),
        "uploader_id": raw.get("uploader_id"),
        "upload_date": raw.get("upload_date"),
        "duration": raw.get("duration"),
        "view_count": raw.get("view_count"),
        "like_count": raw.get("like_count"),
        "extractor": raw.get("extractor"),
        "webpage_url": raw.get("webpage_url") or url,
        "thumbnail": raw.get("thumbnail"),
        "description": raw.get("description"),
        "has_subs": _sub_keys(raw.get("subtitles")),
        "has_auto_subs": _sub_keys(raw.get("automatic_captions")),
        "bgm": None,
        "need_login_subtitle": None,
        "music_hints": [],
        "live_status": raw.get("live_status"),
        "age_limit": raw.get("age_limit"),
    }
    # Bilibili's player endpoint exposes the platform-declared BGM and whether
    # subtitles are login-gated. Metadata only; no media is downloaded.
    if str(fields.get("id") or "").startswith("BV"):
        try:
            import vidlens_extra as E
            pinfo = E.bili_player_info(fields["id"])
            fields["bgm"] = pinfo.get("bgm")
            fields["need_login_subtitle"] = pinfo.get("need_login_subtitle")
        except Exception:
            pass
    fields["music_hints"] = music_hints(fields)
    for k in ("title", "description", "uploader"):
        threats += S.scan(fields.get(k) or "", where=k)
    clean_meta = {}
    for k, v in fields.items():
        if k in ("title", "description", "uploader"):
            clean_meta[k] = S.clean(v, maxlen=4000 if k == "description" else 300)
        else:
            clean_meta[k] = v
    return clean_meta, threats


# ------------------------------------------------------------------ subtitles

TS = r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})"


def _ts(h, m, s, ms) -> float:
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000.0


def parse_vtt(text: str) -> list[dict]:
    """VTT/SRT tolerant parser. Handles cue settings, <c> tags, rolling duplicates."""
    rows = []
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i = 0
    cur = None
    body = []

    def flush():
        nonlocal cur, body
        if cur and body:
            txt = " ".join(body)
            txt = re.sub(r"<[^>]+>", "", txt)
            txt = re.sub(r"\{[^}]*\}", "", txt)
            txt = (txt.replace("&nbsp;", " ").replace("&amp;", "&")
                      .replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'"))
            txt = re.sub(r"\s{2,}", " ", txt).strip()
            if txt and (not rows or txt != rows[-1]["text"]):
                # rolling captions repeat the previous cue before adding words;
                # a pure prefix means "nothing new", a suffix does not.
                if rows and rows[-1]["text"].startswith(txt):
                    pass
                else:
                    rows.append({"t0": cur[0], "t1": cur[1], "text": txt,
                                 "words": [], "track": "subtitle"})
        cur, body = None, []

    while i < len(lines):
        line = lines[i].strip()
        m = re.match(rf"^{TS}\s*-->\s*{TS}", line)
        if m:
            flush()
            cur = (_ts(*m.groups()[:4]), _ts(*m.groups()[4:8]))
            i += 1
            continue
        if cur is not None:
            if line == "":
                flush()
            elif not line.isdigit():
                body.append(line)
        i += 1
    flush()
    # drop rolling-caption prefix duplicates
    out = []
    for r in rows:
        if out and r["text"].startswith(out[-1]["text"]) and len(r["text"]) <= len(out[-1]["text"]) + 8:
            out[-1] = r
            continue
        out.append(r)
    return out


def download_subs(url: str, d: Path, langs: str) -> tuple[list[dict], str]:
    """Download platform subtitles only (0 bytes of media). Human subs win over auto."""
    subdir = d / "subs"
    subdir.mkdir(parents=True, exist_ok=True)
    for old in list(subdir.glob("sub*.vtt")) + list(subdir.glob("sub*.srt")):
        old.unlink(missing_ok=True)
    rc, out, err = run_yt(["--skip-download", "--write-subs", "--write-auto-subs",
                           "--sub-langs", langs, "--sub-format", "vtt/srt/best",
                           "-o", str(subdir / "sub.%(ext)s"), url])
    files = sorted(subdir.glob("sub*.vtt")) + sorted(subdir.glob("sub*.srt"))
    if not files:
        return [], ""
    human = [f for f in files if ".auto." not in f.name.lower()]
    pick = (human or files)[0]
    try:
        rows = parse_vtt(pick.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return [], ""
    return rows, pick.name


# ------------------------------------------------------------------- media

AUDIO_EXT = (".m4a", ".webm", ".mp3", ".opus", ".aac", ".ogg", ".wav", ".flac",
             # bilibili sometimes hands back a combined container for paid videos:
             ".mp4", ".mkv", ".flv")


def media_duration(path: Path) -> float:
    """Duration in seconds, parsed from ffmpeg's banner. 0.0 if unreadable."""
    rc, so, se = core().run(["-i", str(path)])
    m = re.search(r"Duration:\s*(\d+):(\d{2}):(\d{2}(?:\.\d+)?)", se or "")
    if not m:
        return 0.0
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def _audio_duration_ok(path: Path, expected: float) -> bool:
    """A half-downloaded file is smaller and shorter; tolerate 5s / 2%."""
    if expected <= 0:
        return True
    got = media_duration(path)
    return got > 0 and abs(got - expected) <= max(5.0, expected * 0.02)


def _has_video_stream(path: Path) -> bool:
    """True when the container carries a real video stream (not just audio)."""
    try:
        _rc, _so, se = core().run(["-i", str(path)])
    except Exception:
        return False
    return bool(re.search(r"Stream #\d+:\d+.*?: Video:", se or ""))


def download_audio(url: str, d: Path, max_mb: float, force: bool,
                   expected_dur: float = 0.0, notes: list | None = None) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    # reuse what we already have: re-downloading 26MB for nothing is rude to the site
    existing = [p for p in d.glob("audio.*") if p.suffix.lower() in AUDIO_EXT
                and p.stat().st_size > MIN_AUDIO_BYTES]
    if existing and not force:
        pick = max(existing, key=lambda p: p.stat().st_size)
        if _audio_duration_ok(pick, expected_dur):
            return pick
        pick.unlink(missing_ok=True)  # truncated/corrupt: fetch again
    rc, out, err = run_yt(["-f", "ba/b", "-o", str(d / "audio.%(ext)s"), url])
    cands = [p for p in d.glob("audio.*") if p.suffix.lower() in AUDIO_EXT]
    if not cands:
        raise SystemExit(f"audio download failed rc={rc}: {err.strip()[:220]}"
                         + cookie_hint(err))
    f = max(cands, key=lambda p: p.stat().st_size)
    mb = f.stat().st_size / 1048576
    if mb > max_mb and not force:
        f.unlink(missing_ok=True)
        raise SystemExit(f"audio is {mb:.1f}MB > --max-mb {max_mb}. Use --force if you really want it.")
    if notes is not None and _has_video_stream(f):
        # `ba/b` fell through to the combined format: the site has no audio-only
        # track, so "only the bytes we need" did not hold this time. Say so instead
        # of letting the caller believe 16MB of mp4 was a 300KB m4a.
        notes.append(f"该站没有纯音轨，回退下载了整段视频（{mb:.1f}MB）")
    return f


def fmt_t(t: float) -> str:
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def video_selector(height: int) -> str:
    """yt-dlp chain for "some video, at most `height` tall".

    The trailing `/bv*/b` is not decoration: a direct MP4 (or some AcFun items)
    exposes one combined format with no `height` field, so every height-filtered
    branch matches nothing and yt-dlp refuses the whole download -- which then
    takes shot-cut scanning and clip cutting down with it.
    """
    return f"bv*[height<={height}]/b[height<={height}]/bv*/b"


def section_selector(height: int, with_audio: bool) -> str:
    """Format chain for a cut-out section; same fallback rule as video_selector."""
    if with_audio:
        return f"bv*[height<={height}]+ba/b[height<={height}]/bv*+ba/b/b"
    return video_selector(height)


def section_args(t0: float, t1: float, height: int, with_audio: bool) -> list[str]:
    return ["-f", section_selector(height, with_audio),
            "--download-sections", f"*{fmt_t(t0)}-{fmt_t(t1)}",
            "--force-keyframes-at-cuts"]


def download_video_lowest(url: str, d: Path, height: int = 360) -> Path:
    """Video-only, lowest usable resolution. Only for shot-cut scanning."""
    d.mkdir(parents=True, exist_ok=True)
    ffdir = core().ffmpeg_dir()
    rc, out, err = run_yt(["-f", video_selector(height),
                           "--ffmpeg-location", ffdir,
                           "-o", str(d / "video.%(ext)s"), url])
    cands = [p for p in d.glob("video.*") if p.suffix.lower() in (".mp4", ".mkv", ".webm")]
    if not cands:
        raise SystemExit(f"video download failed rc={rc}: {err.strip()[:180]}"
                         + cookie_hint(err))
    return max(cands, key=lambda p: p.stat().st_size)


def download_section(url: str, d: Path, t0: float, t1: float,
                     height: int, with_audio: bool) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    ffdir = core().ffmpeg_dir()
    args = section_args(t0, t1, height, with_audio) + [
        "--ffmpeg-location", ffdir, "-o", str(d / "sec.%(ext)s"), url]
    rc, out, err = run_yt(args)
    cands = [p for p in d.glob("sec.*") if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".m4a")]
    if not cands:
        raise SystemExit(f"section download failed rc={rc}: {err.strip()[:220]}"
                         + cookie_hint(err))
    return max(cands, key=lambda p: p.stat().st_size)


def download_audio_section(url: str, d: Path, t0: float, t1: float,
                           max_mb: float = MAX_AUDIO_MB) -> Path:
    """Audio only for one window. Used when no transcript/subs are cached yet."""
    d.mkdir(parents=True, exist_ok=True)
    ffdir = core().ffmpeg_dir()
    args = ["-f", "ba/b", "--download-sections", f"*{fmt_t(t0)}-{fmt_t(t1)}",
            "--ffmpeg-location", ffdir, "-o", str(d / "sec.%(ext)s"), url]
    rc, out, err = run_yt(args)
    cands = [p for p in d.glob("sec.*") if p.suffix.lower() in AUDIO_EXT]
    if not cands:
        raise SystemExit(f"audio section failed rc={rc}: {err.strip()[:180]}"
                         + cookie_hint(err))
    f = max(cands, key=lambda p: p.stat().st_size)
    mb = f.stat().st_size / 1048576
    if mb > max_mb:
        f.unlink(missing_ok=True)
        raise SystemExit(f"audio section is {mb:.1f}MB > {max_mb}MB")
    return f


# ------------------------------------------------------------------ analysis

def transcribe(path: Path, model="small", device="cpu", compute="int8",
               lang="zh", beam=1, prompt=None, on_progress=None) -> tuple[list[dict], dict]:
    """Local ASR dispatcher.

    VIDLENS_ASR=auto (default) uses SenseVoice when its model+tokens+sherpa-onnx
    are present; otherwise faster-whisper. `VIDLENS_ASR=whisper` forces the old
    backend. Whisper is loaded with local_files_only=True first, so a new chat
    does not hit the Hugging Face API just to check the version.
    """
    backend = (os.environ.get("VIDLENS_ASR") or "auto").strip().lower()
    if backend == "sensevoice" or (backend == "auto" and not prompt):
        try:
            import vidlens_sensevoice as sv
            if sv.available():
                return sv.transcribe(path, lang=lang, on_progress=on_progress)
            if backend == "sensevoice":
                raise SystemExit(
                    "SenseVoice 不可用：检查 VIDLENS_SENSEVOICE_MODEL / "
                    "VIDLENS_SENSEVOICE_TOKENS，以及是否安装了 sherpa-onnx")
        except SystemExit:
            raise
        except Exception:
            if backend == "sensevoice":
                raise
            # auto: fall through to whisper

    from faster_whisper import WhisperModel
    c = core()
    common = dict(device=device, compute_type=compute, download_root=c.model_dir(),
                  cpu_threads=max(1, (os.cpu_count() or 4) - 1))
    try:
        m = WhisperModel(model, local_files_only=True, **common)
        local_only = True
    except Exception:
        m = WhisperModel(model, local_files_only=False, **common)
        local_only = False
    if prompt is None and lang and lang.startswith("zh"):
        prompt = "以下是普通话的发言，请用简体中文转写。"
    segs, info = m.transcribe(c.load_audio(str(path)), language=lang, initial_prompt=prompt,
                              beam_size=beam, vad_filter=True, word_timestamps=True,
                              condition_on_previous_text=False,
                              vad_parameters=dict(min_silence_duration_ms=350))
    rows = []
    for s in segs:
        rows.append({"t0": round(s.start, 3), "t1": round(s.end, 3),
                     "text": s.text.strip(), "track": "speech",
                     "words": [{"w": w.word, "t0": round(w.start, 3), "t1": round(w.end, 3),
                                "p": round(w.probability, 3)} for w in (s.words or [])]})
        if on_progress:
            try:
                on_progress(float(s.end), float(info.duration or 0))
            except Exception:
                pass
    meta = {"language": info.language, "language_probability": round(info.language_probability, 4),
            "duration": round(info.duration, 3), "segments": len(rows),
            "model": model, "device": device, "backend": "whisper",
            "local_files_only": local_only}
    return rows, meta


def pause_gaps(path: Path, dbfs=-32.0, min_dur=0.45) -> list[dict]:
    c = core()
    rc, so, se = c.run(["-i", str(path), "-vn", "-af",
                        f"silencedetect=noise={dbfs}dB:d={min_dur}", "-f", "null", "-"])
    st = [float(x) for x in re.findall(r"silence_start:\s*([0-9.]+)", se)]
    en = [float(x) for x in re.findall(r"silence_end:\s*([0-9.]+)", se)]
    return [{"t0": round(a, 3), "t1": round(b, 3), "dur": round(b - a, 3), "track": "silence"}
            for a, b in zip(st, en)]


def read_pauses(d: Path) -> list[dict]:
    """Read pauses.json whatever shape wrote it, and return clean gaps.

    The CLI pipeline writes {"threshold_db": ..., "gaps": [...]}; grab/MCP write a
    plain list. Code used to assume one of the two, so the other crashed with
    AttributeError: 'str' object has no attribute 'get'. Normalise here.
    """
    p = d / "pauses.json"
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(raw, dict):
        raw = raw.get("gaps")
    if not isinstance(raw, list):
        return []
    out = []
    for g in raw:
        if not isinstance(g, dict):
            continue
        try:
            t0, t1 = float(g["t0"]), float(g["t1"])
        except (KeyError, TypeError, ValueError):
            continue
        try:
            dur = float(g.get("dur"))
        except (TypeError, ValueError):
            dur = t1 - t0
        out.append({**g, "t0": t0, "t1": t1, "dur": max(0.0, dur)})
    return out


def plan_chapters(dur: float, cuts: list[float], gaps: list[dict],
                  window: float = DEFAULT_CHAPTER_WINDOW) -> list[dict]:
    """Merge cuts and long silences into cheap viewing windows."""
    dur = float(dur or 0)
    if dur <= 0:
        return []
    marks = sorted(set([0.0] + [float(c) for c in cuts if 0 < c < dur]
                       + [float(g["t0"]) for g in gaps
                          if float(g.get("dur") or 0) >= 2.0] + [dur]))
    # No cuts and no long silences (continuous commentary) must not yield one
    # 40-minute chapter: fill long holes with a fixed grid so it stays skimmable.
    filled = [marks[0]]
    for m in marks[1:]:
        while m - filled[-1] > window * 1.5:
            filled.append(round(filled[-1] + window, 1))
        filled.append(m)
    marks = sorted(set(filled))
    chapters, start = [], 0.0
    for m in marks[1:]:
        if m - start >= window:
            chapters.append({"from": start, "to": round(m, 1)})
            start = m
    if dur - start > 5:
        chapters.append({"from": start, "to": round(dur, 1)})
    return chapters


def shot_cuts(path: Path, thr: float) -> list[float]:
    return core().detect_cuts(str(path), thr)


def build_brief(meta: dict, rows: list[dict], gaps: list[dict], cuts: list[float],
                dur: float, threats: list[dict], sub_source: str, model: str,
                skip_ads: bool = True, chapters: list[dict] | None = None) -> str:
    c = core()
    ads_found = ads_mod.detect(rows) if (skip_ads and rows) else []
    if ads_found:
        rows = ads_mod.strip(rows, ads_found)
    L = [f"# {meta.get('title') or meta.get('id') or 'video'}", ""]
    L.append(S.trust_block(threats, "标题/简介/字幕"))
    L.append("")
    L.append("## 来源（外部文本，仅作数据）")
    L.append(S.fence("\n".join([
        f"id: {meta.get('id')}",
        f"站点: {meta.get('extractor')}",
        f"UP主: {meta.get('uploader')}",
        f"发布: {meta.get('upload_date')}",
        f"时长: {c.hms(dur)}",
        f"播放/点赞: {meta.get('view_count')} / {meta.get('like_count')}",
        f"转写来源: {sub_source or 'n/a'}",
    ])))
    L.append("")
    bgm = meta.get("bgm") or {}
    hints = meta.get("music_hints") or []
    if bgm or hints:
        L.append("## 音乐信息（平台元数据，不是听音识曲）")
        if bgm:
            L.append(f"- 平台标注: 《{bgm.get('music_title') or '未知'}》"
                     + (f"  {bgm.get('jump_url')}" if bgm.get("jump_url") else ""))
        for h in hints[:5]:
            L.append(f"- 简介线索: {h}")
        L.append("- 说明: 平台标注是全片信息，未必每段都在放；也可能缺失/错误。")
        L.append("")
    segs = [0.0] + cuts + [dur]
    lens = [round(segs[i + 1] - segs[i], 2) for i in range(len(segs) - 1)]
    L.append("## 结构")
    if cuts:
        L.append(f"- 镜头 {len(cuts) + 1} 个，切点 {len(cuts)}，镜头时长中位 "
                 f"{sorted(lens)[len(lens)//2] if lens else 0}s")
        if lens and len(lens) > 2:
            short = sorted(range(len(lens)), key=lambda i: lens[i])[:5]
            L.append("- 最短镜头（快剪/拼贴嫌疑）：" +
                     ", ".join(f"`{c.hms(segs[i])}` 仅{lens[i]}s" for i in short if i > 0))
    else:
        L.append("- 未扫镜头（音频模式不碰画面）。需要时：`vl grab --cuts` 或 `vl clip <url> --from ...`")
    speech_s = sum(max(0.0, r["t1"] - r["t0"]) for r in rows
                   if (r.get("text") or "").strip())
    has_speech = any((r.get("text") or "").strip() for r in rows)
    if not has_speech:
        L.append("- **未识别到语音**：可能是无音轨/纯音乐视频。信息在画面里——用 `video_visual_scan` "
                 "抽样看帧，或用 `video_sheet` 看具体区间。")
    elif dur and speech_s < dur * 0.15:
        L.append(f"- **语音覆盖率仅 {speech_s/dur*100:.0f}%**（{c.hms(speech_s)} / {c.hms(dur)}）："
                 "大量段落无词，信息可能在画面（字幕、演示、动画），建议 `video_visual_scan`。")
    elif dur and speech_s < dur * 0.5:
        L.append(f"- 语音覆盖率 {speech_s/dur*100:.0f}%：有相当长的无词段落，"
                 "这些段落用 `video_sheet` 抽查画面。")
    if chapters and len(chapters) > 1:
        L.append("")
        L.append("## 分步看（长视频按顺序，不要一次下整片）")
        L += [f"- `{c.hms(x['from'])}` → `{c.hms(x['to'])}`"
              for x in chapters[:MAX_BRIEF_CHAPTERS]]
        if len(chapters) > MAX_BRIEF_CHAPTERS:
            L.append(f"- …另有 {len(chapters) - MAX_BRIEF_CHAPTERS} 段")
    emos = Counter((r.get("emotion") or "").strip() for r in rows
                   if (r.get("emotion") or "").strip())
    events = Counter((r.get("event") or "").strip() for r in rows
                     if (r.get("event") or "").strip())
    langs = Counter((r.get("lang") or "").strip() for r in rows
                    if (r.get("lang") or "").strip())
    if emos or events:
        zh_emo = {"NEUTRAL": "中性", "HAPPY": "高兴", "SAD": "悲伤", "ANGRY": "愤怒",
                  "FEARFUL": "害怕", "DISGUSTED": "厌恶", "SURPRISED": "惊讶",
                  "EMO_UNKNOWN": "未知"}
        zh_event = {"Speech": "语音", "BGM": "背景音乐", "Music": "音乐",
                    "Laughter": "笑声", "Applause": "掌声", "Cry": "哭声",
                    "Cough": "咳嗽", "Sneeze": "喷嚏"}
        L.append("")
        L.append("## 声音信号（本地 SenseVoice，启发式）")
        if langs:
            L.append("- 语种: " + ", ".join(f"{k} {v}" for k, v in langs.most_common()))
        if emos:
            L.append("- 情感: " + ", ".join(
                f"{zh_emo.get(k, k)} {v}" for k, v in emos.most_common()))
        if events:
            ev_line = "- 事件: " + ", ".join(
                f"{zh_event.get(k, k)} {v}" for k, v in events.most_common())
            if "BGM" in events and has_speech:
                ev_line += "（有语音的段落也可能同时有背景音乐）"
            L.append(ev_line)
        L.append("- 说明: 标签来自音频模型，用于提示语气/音乐/掌声，不是事实判断。")
    L.append("")
    L.append(ads_mod.section(ads_found, dur))
    L.append("")
    if gaps:
        speech_end0 = max((r["t1"] for r in rows), default=dur)
        mid0 = [g for g in gaps if g["t1"] <= speech_end0 + 0.5]
        top = sorted(mid0 or gaps, key=lambda g: -g["dur"])[:5]
        L.append("- 最长停顿（话中）：" + ", ".join(f"`{c.hms(g['t0'])}` {g['dur']:.2f}s" for g in top))
        tail = [g for g in gaps if g["t1"] > speech_end0 + 0.5]
        if tail:
            L.append(f"- 另有 {len(tail)} 段静音落在语音结束后（约 {c.hms(speech_end0)} 之后），属于无词段落/片尾")
    L.append("")
    if gaps and rows:
        speech_end = max((r["t1"] for r in rows), default=0.0)
        mid = [g for g in gaps if g["t1"] <= speech_end + 0.5]
        L.append("## 停顿处的上下文（犹豫/回避/换话题）")
        seen = set()
        shown = 0
        for g in sorted(mid, key=lambda x: -x["dur"]):
            if shown >= 8:
                break
            if g["dur"] < 1.2:
                continue
            before = [r for r in rows if r["t1"] <= g["t0"] + 0.3]
            after = [r for r in rows if r["t0"] >= g["t0"] + 0.05]
            if not before or not after:
                continue
            key = (before[-1]["text"], after[0]["text"])
            if key in seen:
                continue
            seen.add(key)
            shown += 1
            L.append(f"- `{c.hms(g['t0'])}` 静默 {g['dur']:.2f}s")
            L.append(f"    - 停前：{S.clean(before[-1]['text'], 160)}")
            L.append(f"    - 停后：{S.clean(after[0]['text'], 160)}")
        if shown == 0:
            L.append("- 无。所有静音段都落在语音结束之后（片尾/无词段落），不是话中犹豫。")
        L.append("")
    low = []
    for r in rows:
        for w in r.get("words") or []:
            if w.get("p", 1.0) < 0.62:
                low.append((w["t0"], w["w"], w["p"]))
    if low:
        L.append("## 低置信词（必须回画面/原音核对，不要当事实）")
        L += [f"- `{c.hms(t)}` 「{S.clean(w, 24)}」 p={p}"
              for t, w, p in low[:MAX_LOW_WORDS]]
        L.append("")
    L.append("## 转写（每行挂在时间码上）")
    L += [f"- `{c.hms(r['t0'])}` {S.clean(r['text'], 300)}"
          for r in rows[:MAX_TRANSCRIPT_LINES] if (r.get("text") or "").strip()]
    L.append("")
    L.append("## 建议下一步看哪里（按需取画面，不下载全片）")
    if gaps:
        g = max([x for x in gaps if x["t1"] <= (max((r['t1'] for r in rows), default=0.0) + 0.5)] or gaps,
                key=lambda x: x["dur"])
        L.append(f"- 最长停顿 `{c.hms(g['t0'])}`（{g['dur']:.1f}s）：取该点前后 10 秒画面")
    if lens and len(lens) > 2:
        i = min(range(1, len(lens)), key=lambda k: lens[k])
        L.append(f"- 最短镜头 `{c.hms(segs[i])}`（{lens[i]}s）：可能是快剪拼贴")
    L.append("- 命令示例：`vl clip <url> --from 02:00 --to 02:20`")
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------- commands

def cmd_meta(a):
    meta, threats = fetch_meta(a.url)
    d = out_root() / (meta.get("id") or "unknown")
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps(
        {"meta": meta, "threats": threats}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"id={meta.get('id')} extractor={meta.get('extractor')} dur={meta.get('duration')}s")
    print(f"subs={len(meta.get('has_subs') or [])} auto_subs={len(meta.get('has_auto_subs') or [])}")
    print(f"threats={len(threats)} level={S.level(threats)}")
    print(f"meta -> {d/'meta.json'}")


def cmd_grab(a):
    c = core()
    t_start = time.time()
    meta, threats = fetch_meta(a.url)
    dur = float(meta.get("duration") or 0)
    d = out_root() / (meta.get("id") or "unknown")
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps(
        {"meta": meta, "threats": threats}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[1/4] meta ok  dur={c.hms(dur)}  threats={len(threats)}")

    rows, sub_source, model = [], "", "none"
    media = None
    if not a.no_subs:
        rows, sub_source = download_subs(a.url, d, a.sub_langs)
        if rows:
            print(f"[2/4] platform subtitles: {len(rows)} cues from {sub_source} (0 bytes of media)")

    if not rows:
        print("[2/4] no subtitles -> audio only")
        media = download_audio(a.url, d, a.max_mb, a.force, expected_dur=dur)
        mb = media.stat().st_size / 1048576
        print(f"      audio {mb:.1f}MB")
        if a.reuse and (d / "transcript.jsonl").exists():
            rows = [json.loads(x) for x in (d / "transcript.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
            model = "cached"
            sub_source = f"asr(audio {mb:.1f}MB, cached)"
        else:
            rows, info = transcribe(media, model=a.model, device=a.device, compute=a.compute,
                                    lang=a.lang, beam=a.beam)
            (d / "speech_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
            backend = info.get("backend") or "whisper"
            model = a.model if backend == "whisper" else backend
            if backend == "whisper":
                sub_source = f"asr(audio {mb:.1f}MB, model={a.model})"
            else:
                sub_source = f"asr({backend}, audio {mb:.1f}MB)"
            print(f"      asr {len(rows)} segments ({backend})")
    else:
        media = download_audio(a.url, d, a.max_mb, a.force, expected_dur=dur)
        print(f"      audio for pause analysis {media.stat().st_size/1048576:.1f}MB")

    for r in rows:
        r["text_threats"] = S.scan(r.get("text") or "", where=f"subtitle@{r['t0']}")
        threats += r["text_threats"]
        r["text"] = S.clean(r.get("text"), 500)
    c.write_jsonl(d / "transcript.jsonl", rows)
    (d / "transcript.srt").write_text(c.to_srt(rows), encoding="utf-8")
    print(f"[3/4] transcript -> {d/'transcript.srt'}")

    gaps = pause_gaps(media, a.dbfs, a.min_dur) if media else []
    (d / "pauses.json").write_text(json.dumps(gaps, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    cuts = []
    if a.cuts:
        print("[3.5/4] cuts need pixels: fetching lowest video stream (costs ~20MB for 7min)")
        vid = download_video_lowest(a.url, d, a.cuts_height)
        print(f"      video {vid.stat().st_size/1048576:.1f}MB")
        cuts = shot_cuts(vid, a.thr)
        vid.unlink(missing_ok=True)
        print(f"      cuts={len(cuts)}")
        (d / "shots.json").write_text(json.dumps({"threshold": a.thr, "cuts": cuts}),
                                      encoding="utf-8")
    brief = build_brief(meta, rows, gaps, cuts, dur, threats, sub_source, model,
                        chapters=plan_chapters(dur, cuts, gaps))
    (d / "brief.md").write_text(brief, encoding="utf-8")
    print(f"[4/4] brief -> {d/'brief.md'}  pauses={len(gaps)} cuts={len(cuts)}")

    if media and not a.keep:
        media.unlink(missing_ok=True)
        print("      media deleted (use --keep to retain)")
    print(f"seconds={time.time()-t_start:.1f}  threats_total={len(threats)}")


def cmd_clip(a):
    c = core()
    t0, t1 = c.parse_t(a.start), c.parse_t(a.end)
    if t1 <= t0:
        raise SystemExit("--to must be after --from")
    meta, _ = fetch_meta(a.url)
    d = out_root() / (meta.get("id") or "unknown") / f"clip_{int(t0)}_{int(t1)}"
    d.mkdir(parents=True, exist_ok=True)
    print(f"downloading section {c.hms(t0)}-{c.hms(t1)} @<={a.height}p ...")
    sec = download_section(a.url, d, t0, t1, a.height, a.with_audio)
    print(f"section {sec.stat().st_size/1048576:.2f}MB")
    dur = t1 - t0
    if a.sheet:
        c.cmd_sheet(types.SimpleNamespace(video=str(sec), out=str(d), start="0",
                                          end=str(dur), cols=a.cols, rows=a.rows,
                                          width=a.width, fs=22, offset=t0))
        print(f"sheet -> {d}")
    else:
        made = c.grab_at(str(sec), [i / a.fps for i in range(int(dur * a.fps) + 1)], d, a.width, 3)
        for rel, path in made:
            abs_t = t0 + rel
            new = d / f"t{int(round(abs_t*1000)):09d}ms.jpg"
            Path(path).replace(new)
            print(f"{c.hms(abs_t)}\t{new}")
    if not a.keep:
        sec.unlink(missing_ok=True)
        print("section media deleted (use --keep to retain)")


def add_subcommands(ap):
    def common(p):
        p.add_argument("url")
        p.add_argument("--json", action="store_true")

    p = ap.add_parser("meta", help="metadata only, downloads nothing")
    common(p); p.set_defaults(f=cmd_meta)

    p = ap.add_parser("grab", help="subtitles/audio -> transcript -> brief (no full download)")
    common(p)
    p.add_argument("--lang", default="zh")
    p.add_argument("--model", default="small")
    p.add_argument("--device", default="cpu")
    p.add_argument("--compute", default="int8")
    p.add_argument("--beam", type=int, default=1)
    p.add_argument("--sub-langs", dest="sub_langs", default=DEFAULT_SUB_LANGS)
    p.add_argument("--no-subs", action="store_true", help="skip platform subtitles")
    p.add_argument("--max-mb", dest="max_mb", type=float, default=MAX_AUDIO_MB)
    p.add_argument("--force", action="store_true")
    p.add_argument("--keep", action="store_true", help="keep downloaded media")
    p.add_argument("--reuse", action="store_true", help="reuse existing transcript.jsonl")
    p.add_argument("--thr", type=float, default=0.25)
    p.add_argument("--cuts", action="store_true", help="also scan shot cuts (downloads lowest video stream)")
    p.add_argument("--cuts-height", dest="cuts_height", type=int, default=360)
    p.add_argument("--dbfs", type=float, default=-32.0)
    p.add_argument("--min-dur", dest="min_dur", type=float, default=0.45)
    p.set_defaults(f=cmd_grab)

    p = ap.add_parser("clip", help="download ONLY a section and return frames/sheet")
    common(p)
    p.add_argument("--from", dest="start", default="0")
    p.add_argument("--to", dest="end", default="20")
    p.add_argument("--height", type=int, default=360)
    p.add_argument("--fps", type=float, default=1.0)
    p.add_argument("--width", type=int, default=960)
    p.add_argument("--sheet", action="store_true")
    p.add_argument("--cols", type=int, default=4)
    p.add_argument("--rows", type=int, default=3)
    p.add_argument("--with-audio", dest="with_audio", action="store_true")
    p.add_argument("--keep", action="store_true")
    p.set_defaults(f=cmd_clip)
