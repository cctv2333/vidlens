#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vidlens - degrade a video into evidence an LLM can actually read.

Design rules
------------
1. NO vision model. The LLM (me) looks at the JPEGs with its own eyes.
2. NO cloud API. Everything runs offline.
3. Only two binaries/packages: ffmpeg (via imageio-ffmpeg) + faster-whisper.
4. Every output is timestamped, so any claim can be traced back to a frame.
5. Stdout stays ASCII (Windows console encoding); all text goes into UTF-8 files.

Commands
--------
  probe     metadata: duration / fps / resolution / codec / tags
  shots     hard cuts on the pixel timeline (threshold on scene score)
  frames    grab frames for an arbitrary range (the "zoom" primitive)
  sheet     contact sheet: N frames in one image (saves the vision budget)
  speech    ASR with word-level timestamps -> transcript.jsonl
  pauses    silence gaps (the parts where the ear is missing)
  env       loudness envelope as a text sparkline
  report    merge everything -> events.jsonl + brief.md

Typical use
-----------
  vidlens shots  a.mp4
  vidlens sheet  a.mp4 --from 92 --to 104 --cols 4 --rows 3
  vidlens frames a.mp4 --at 93.2,94.0,95.5 --width 1600
  vidlens speech a.mp4 --lang zh
  vidlens pauses a.mp4
  vidlens report a.mp4
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import vidlens_ads as ads_mod

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


# ---------------------------------------------------------------- ffmpeg glue

MODEL_DIRS = [
    os.environ.get("VIDLENS_MODEL_DIR"),
    r"D:\dev\models\whisper",
    str(Path.home() / ".cache" / "whisper"),
]


def model_dir() -> str:
    for d in MODEL_DIRS:
        if d and Path(d).exists():
            return d
    fallback = Path(MODEL_DIRS[1] if not MODEL_DIRS[0] else MODEL_DIRS[0])
    fallback.mkdir(parents=True, exist_ok=True)
    return str(fallback)


def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        p = shutil.which("ffmpeg")
        if not p:
            sys.exit("ffmpeg not found: pip install imageio-ffmpeg")
        return p


FFMPEG = None


def run(args, *, timeout=None):
    global FFMPEG
    if FFMPEG is None:
        FFMPEG = ffmpeg_exe()
    cmd = [FFMPEG, "-hide_banner", "-nostdin"] + args
    p = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return p.returncode, p.stdout or "", p.stderr or ""


def outdir(video: Path, out: str | None) -> Path:
    d = Path(out) if out else Path.cwd() / "out" / video.stem
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def write_jsonl(path: Path, rows) -> int:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)


def hms(t: float) -> str:
    t = max(0.0, float(t))
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}" if h else f"{m:02d}:{s:06.3f}"


def parse_t(s: str) -> float:
    s = s.strip()
    if ":" in s:
        parts = [float(x) for x in s.split(":")]
        v = 0.0
        for p in parts:
            v = v * 60 + p
        return v
    return float(s)


# ------------------------------------------------------------------- commands

DUR_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)")
VID_RE = re.compile(r"Stream #\d+:\d+.*?: Video: (\w+).*?[,\s](\d{2,5})x(\d{2,5})")
FPS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*fps")
AUD_RE = re.compile(r"Stream #\d+:\d+.*?: Audio: (\w+).*?(?:(\d+) Hz)?(?:.*?(mono|stereo))?")


def _project_dir() -> Path:
    return Path(__file__).resolve().parent


_CHECKOUT_MARKERS = ("install.cmd", "requirements.txt", "HARDCODE_AUDIT.md")


def project_root() -> Path:
    """Where `out/` and `bin/` belong.

    In a source checkout: beside the modules (unchanged behaviour, existing
    caches keep working). Installed from PyPI: site-packages is code, not data,
    so fall back to a per-user directory instead of writing next to the wheel.
    """
    here = Path(__file__).resolve().parent
    if any((here / m).exists() for m in _CHECKOUT_MARKERS):
        return here
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    d = base / "vidlens"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ffmpeg_dir() -> str:
    """yt-dlp looks for an executable literally named 'ffmpeg'.
    imageio ships 'ffmpeg-win-x86_64-v7.1.exe', so expose a stable shim."""
    real = Path(ffmpeg_exe())
    name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    want = real.parent / name
    if want.exists() and want.resolve() == real.resolve():
        return str(real.parent)
    cache = Path(os.environ.get("VIDLENS_BIN") or (project_root() / "bin"))
    cache.mkdir(parents=True, exist_ok=True)
    shim = cache / name
    if not shim.exists() or shim.stat().st_size != real.stat().st_size:
        shutil.copy2(real, shim)
        if os.name != "nt":
            shim.chmod(0o755)
    return str(cache)


def cmd_probe(a):
    rc, so, se = run(["-i", a.video])
    info = {"path": str(Path(a.video).resolve()), "duration_s": None,
            "width": None, "height": None, "fps": None,
            "vcodec": None, "acodec": None, "sample_rate": None, "channels": None,
            "has_audio": False, "tags": {}}
    m = DUR_RE.search(se)
    if m:
        info["duration_s"] = round(int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)), 3)
    m = VID_RE.search(se)
    if m:
        info["vcodec"], info["width"], info["height"] = m.group(1), int(m.group(2)), int(m.group(3))
    fm = FPS_RE.search(se)
    if fm:
        info["fps"] = float(fm.group(1))
    am = AUD_RE.search(se)
    if am:
        info["has_audio"] = True
        info["acodec"] = am.group(1)
        if am.group(2):
            info["sample_rate"] = int(am.group(2))
        if am.group(3):
            info["channels"] = am.group(3)
    for key in ("creation_time", "encoder", "com.apple.quicktime.location.ISO6709",
                "location", "com.android.version", "major_brand", "handler_name", "comment", "title"):
        mm = re.search(rf"{re.escape(key)}=([^\r\n]+)", se)
        if mm:
            info["tags"][key] = mm.group(1).strip()
    if a.json:
        print(json.dumps(info, ensure_ascii=False, indent=1))
    else:
        print(f"duration {hms(info['duration_s'] or 0)}  {info['width']}x{info['height']}  "
              f"{info['fps']}fps  {info['vcodec']}  audio={info['has_audio']}")
        for k, v in info["tags"].items():
            print(f"  tag {k} = {v}")
    return info


def detect_cuts(video: str, thr: float, min_gap: float = 0.2):
    rc, so, se = run(["-i", video, "-filter:v", f"select='gt(scene,{thr})',showinfo",
                      "-an", "-f", "null", "-"])
    times = []
    for m in re.finditer(r"pts_time:([0-9.]+)", se):
        t = float(m.group(1))
        if not times or t - times[-1] >= min_gap:
            times.append(round(t, 3))
    return times


def cmd_shots(a):
    cuts = detect_cuts(a.video, a.thr)
    d = outdir(Path(a.video), a.out)
    write_json(d / "shots.json", {"threshold": a.thr, "cuts": cuts})
    if a.json:
        print(json.dumps(cuts))
    else:
        print(f"cuts {len(cuts)} thr {a.thr}")
        print(" ".join(f"{c:.2f}" for c in cuts))
    return cuts


def grab_at(video, ts, d: Path, width: int, q: int):
    made = []
    for t in ts:
        name = d / f"t{int(round(t*1000)):09d}ms.jpg"
        rc, so, se = run(["-ss", f"{t:.3f}", "-i", video, "-frames:v", "1",
                          "-vf", f"scale={width}:-2", "-q:v", str(q), "-y", str(name)])
        if name.exists() and name.stat().st_size > 0:
            made.append((round(t, 3), str(name)))
    return made


def cmd_frames(a):
    d = outdir(Path(a.video), a.out)
    made = []
    if a.at:
        ts = [parse_t(x) for x in a.at.split(",") if x.strip()]
        made = grab_at(a.video, ts, d, a.width, a.q)
    else:
        start, end = parse_t(a.start), parse_t(a.end)
        dur = max(0.0, end - start)
        n = max(1, int(round(dur * a.fps)) + 1)
        tmp = Path(tempfile.mkdtemp())
        rc, so, se = run(["-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", a.video,
                          "-vf", f"fps={a.fps},scale={a.width}:-2",
                          "-q:v", str(a.q), "-y", str(tmp / "f%05d.jpg")])
        files = sorted(tmp.glob("f*.jpg"))
        for i, f in enumerate(files):
            t = round(start + i / a.fps, 3)
            dst = d / f"t{int(round(t*1000)):09d}ms.jpg"
            shutil.move(str(f), dst)
            made.append((t, str(dst)))
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"frames {len(made)}")
    for t, p in made:
        print(f"{hms(t)}\t{p}")
    write_jsonl(d / "frames_index.jsonl", [{"t": t, "file": p} for t, p in made])
    return made


FONTS = [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\arial.ttf",
         "/System/Library/Fonts/PingFang.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def find_font():
    for f in FONTS:
        if Path(f).exists():
            return f
    return None


_DRAWTEXT: bool | None = None


def has_drawtext() -> bool:
    """Whether this ffmpeg build has the drawtext filter (needs libfreetype).

    imageio-ffmpeg's Linux build usually omits it, so burned timecodes are an
    enhancement we must be able to skip: a sheet without labels still carries
    the same frames, and its filename/timecodes stay correct.
    """
    global _DRAWTEXT
    if _DRAWTEXT is None:
        try:
            _rc, so, _se = run(["-hide_banner", "-filters"])
            _DRAWTEXT = "drawtext" in (so or "")
        except Exception:
            _DRAWTEXT = False
    return _DRAWTEXT


def cmd_sheet(a):
    d = outdir(Path(a.video), a.out)
    start, end = parse_t(a.start), parse_t(a.end)
    offset = float(getattr(a, "offset", 0) or 0)
    dur = max(0.001, end - start)
    fps = max(0.05, (a.cols * a.rows - 1) / dur)
    # -ss 会让 pts 从 0 重新计时，必须把绝对时间加回去，否则烧进画面的时间码是错的
    vf = f"setpts=PTS+{start + offset:.3f}/TB,fps={fps:.4f},scale={a.width}:-2"
    font = find_font()
    labelled = bool(font) and has_drawtext()
    if labelled:
        fp = font.replace("\\", "/").replace(":", "\\:")
        vf += (f",drawtext=fontfile='{fp}':text='%{{pts\\:hms}}':x=6:y=6:fontsize={a.fs}:"
               f"fontcolor=yellow:box=1:boxcolor=black@0.55")
    vf += f",tile={a.cols}x{a.rows}"
    dst = d / f"sheet_{int((start + offset)*1000)}_{int((end + offset)*1000)}.jpg"
    rc, so, se = run(["-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", a.video,
                      "-vf", vf, "-frames:v", "1", "-q:v", "3", "-y", str(dst)])
    if not dst.exists():
        print("sheet FAILED")
        print(se[-800:])
        return
    print(f"sheet {dst}") if getattr(a, "verbose", True) else None
    if getattr(a, "verbose", True):
        print(f"range {hms(start + offset)} -> {hms(end + offset)}  grid {a.cols}x{a.rows}  "
              f"one tile ~ {dur/(a.cols*a.rows):.2f}s")
        if not labelled:
            print("note: this ffmpeg has no drawtext/font — tiles are NOT timecoded "
                  "（文件名与时间码仍然正确）")


def wav_of(video, dst: Path, sr=16000):
    rc, so, se = run(["-i", video, "-vn", "-ac", "1", "-ar", str(sr),
                      "-c:a", "pcm_s16le", "-y", str(dst)])
    return dst


def load_audio(video, sr=16000):
    """Decode with ffmpeg into a float32 mono array. Avoids PyAV entirely."""
    import numpy as np
    tmp = Path(tempfile.mkdtemp())
    w = tmp / "a.wav"
    try:
        wav_of(video, w, sr=sr)
        with wave.open(str(w), "rb") as f:
            n, ch, sw_ = f.getnframes(), f.getnchannels(), f.getsampwidth()
            raw = f.readframes(n)
    finally:
        pass
    shutil.rmtree(tmp, ignore_errors=True)
    if sw_ == 2:
        arr = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    else:
        raise SystemExit("unsupported wav sample width")
    if ch > 1:
        arr = arr.reshape(-1, ch).mean(axis=1)
    return arr


def cmd_speech(a):
    from faster_whisper import WhisperModel
    d = outdir(Path(a.video), a.out)
    prompt = getattr(a, "prompt", None)
    lang = a.lang if a.lang and a.lang != "auto" else None
    if prompt is None and lang and lang.startswith("zh"):
        prompt = "以下是普通话的发言，请用简体中文转写。"
    model = WhisperModel(a.model, device=a.device, compute_type=a.compute,
                         download_root=model_dir(),
                         cpu_threads=max(1, (os.cpu_count() or 4) - 1))
    segs, info = model.transcribe(
        load_audio(a.video), language=lang, initial_prompt=prompt,
        beam_size=a.beam, vad_filter=True, word_timestamps=True,
        condition_on_previous_text=False,
        vad_parameters=dict(min_silence_duration_ms=350),
    )
    rows, plain = [], []
    for s in segs:
        words = [{"w": w.word, "t0": round(w.start, 3), "t1": round(w.end, 3),
                  "p": round(w.probability, 3)} for w in (s.words or [])]
        rows.append({"t0": round(s.start, 3), "t1": round(s.end, 3),
                     "text": s.text.strip(), "words": words, "track": "speech"})
        plain.append(f"[{hms(s.start)}] {s.text.strip()}")
    n = write_jsonl(d / "transcript.jsonl", rows)
    (d / "transcript.txt").write_text("\n".join(plain) + "\n", encoding="utf-8")
    (d / "transcript.srt").write_text(to_srt(rows), encoding="utf-8")
    write_json(d / "speech_info.json", {"language": info.language,
                                       "language_probability": round(info.language_probability, 4),
                                       "duration": round(info.duration, 3), "segments": n,
                                       "model": a.model, "device": a.device})
    print(f"segments {n}  lang {info.language} p={info.language_probability:.2f}  -> {d/'transcript.jsonl'}")


def to_srt(rows):
    def ts(t):
        h = int(t // 3600); m = int(t % 3600 // 60); s = int(t % 60); ms = int((t % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    out = []
    for i, r in enumerate(rows, 1):
        out += [str(i), f"{ts(r['t0'])} --> {ts(r['t1'])}", r["text"], ""]
    return "\n".join(out)


def cmd_pauses(a):
    d = outdir(Path(a.video), a.out)
    rc, so, se = run(["-i", a.video, "-vn", "-af",
                      f"silencedetect=noise={a.dbfs}dB:d={a.min_dur}", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start:\s*([0-9.]+)", se)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([0-9.]+)", se)]
    gaps = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else None
        if e is None:
            continue
        gaps.append({"t0": round(s, 3), "t1": round(e, 3), "dur": round(e - s, 3),
                     "track": "silence"})
    write_json(d / "pauses.json", {"threshold_db": a.dbfs, "gaps": gaps})
    print(f"silences {len(gaps)} (>= {a.min_dur}s below {a.dbfs}dB)")
    for g in gaps[:40]:
        print(f"  {hms(g['t0'])}  {g['dur']:.2f}s")


def read_wav(path: Path, sr: int = 8000):
    with wave.open(str(path), "rb") as w:
        n, ch, sw = w.getnframes(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    import array
    if sw != 2:
        raise SystemExit("expected 16-bit wav")
    a = array.array("h")
    a.frombytes(raw)
    if ch > 1:
        a = array.array("h", a[::ch])
    return a, sr


BLOCKS = " .:-=+*#%@"


def cmd_env(a):
    d = outdir(Path(a.video), a.out)
    wav = d / "_env.wav"
    wav_of(a.video, wav, sr=8000)
    a16, sr = read_wav(wav)
    win = int(sr * a.win)
    import array
    levels = []
    for i in range(0, len(a16), win):
        chunk = a16[i:i + win]
        if not chunk:
            break
        s = 0
        for v in chunk:
            s += v * v
        rms = math.sqrt(s / len(chunk)) / 32768.0
        db = 20 * math.log10(rms) if rms > 0 else -120.0
        levels.append(round(db, 1))
    wav.unlink(missing_ok=True)
    lo, hi = -60.0, -6.0
    chars = []
    for db in levels:
        x = (max(lo, min(hi, db)) - lo) / (hi - lo)
        chars.append(BLOCKS[min(len(BLOCKS) - 1, int(x * len(BLOCKS)))])
    line = "".join(chars)
    wrap = 120
    print(f"env win={a.win}s  (-60..-6 dB)")
    for i in range(0, len(line), wrap):
        t = i * a.win
        print(f"{hms(t)} {line[i:i+wrap]}")
    write_json(d / "envelope.json", {"win": a.win, "db": levels})
    order = sorted(levels)
    if order:
        p = lambda q: order[min(len(order) - 1, int(q * len(order)))]
        print(f"db p10={p(0.1)} median={p(0.5)} p90={p(0.9)} max={order[-1]}")


def cmd_report(a):
    d = outdir(Path(a.video), a.out)
    print("[1/4] probe"); rc, so, se = run(["-i", a.video])
    # reuse functions silently
    info = {"path": str(Path(a.video).resolve())}
    m = DUR_RE.search(se)
    dur = 0.0
    if m:
        dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    info["duration_s"] = round(dur, 3)
    m = VID_RE.search(se)
    if m:
        info["vcodec"], info["width"], info["height"] = m.group(1), int(m.group(2)), int(m.group(3))
    fm = FPS_RE.search(se)
    info["fps"] = float(fm.group(1)) if fm else None
    info["has_audio"] = "Audio:" in se
    write_json(d / "meta.json", info)

    print("[2/4] cuts")
    cuts = detect_cuts(a.video, a.thr)
    segs = [0.0] + cuts + [dur] if dur else cuts
    lens = [round(segs[i + 1] - segs[i], 2) for i in range(len(segs) - 1)]
    write_json(d / "shots.json", {"threshold": a.thr, "cuts": cuts, "lengths": lens})

    print("[3/4] pauses")
    rc, so, se2 = run(["-i", a.video, "-vn", "-af",
                       f"silencedetect=noise={a.dbfs}dB:d={a.min_dur}", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start:\s*([0-9.]+)", se2)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([0-9.]+)", se2)]
    gaps = [{"t0": round(s, 3), "t1": round(e, 3), "dur": round(e - s, 3)}
            for s, e in zip(starts, ends)]
    write_json(d / "pauses.json", {"threshold_db": a.dbfs, "gaps": gaps})

    print("[4/4] speech")
    rows = []
    if a.no_speech:
        print("  skipped")
    else:
        cmd_speech(argparse.Namespace(video=a.video, out=a.out, model=a.model, device=a.device,
                                      compute=a.compute, lang=a.lang, beam=a.beam,
                                      prompt=getattr(a, "prompt", None)))
        rows = [json.loads(l) for l in (d / "transcript.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

    ads_found = ads_mod.detect(rows) if rows else []
    if ads_found:
        rows = ads_mod.strip(rows, ads_found)

    events = sorted(
        [{"t0": c, "t1": c, "track": "cut", "text": ""} for c in cuts]
        + [{"t0": g["t0"], "t1": g["t1"], "track": "silence",
            "text": f"silence {g['dur']:.2f}s"} for g in gaps]
        + [{"t0": r["t0"], "t1": r["t1"], "track": "speech", "text": r["text"]} for r in rows],
        key=lambda e: (e["t0"], e["track"]))
    n_ev = write_jsonl(d / "events.jsonl", events)

    brief = [f"# {Path(a.video).name}", ""]
    brief.append(f"- 时长 {hms(dur)} · {info.get('width')}x{info.get('height')} {info.get('fps')}fps {info.get('vcodec')} · 有音轨={info.get('has_audio')}")
    brief.append(f"- 镜头切点 {len(cuts)} · 静音段 {len(gaps)} · 语音分段 {len(rows)}")
    if lens:
        med = sorted(lens)[len(lens) // 2]
        brief.append(f"- 镜头时长 中位 {med}s / 最短 {min(lens)}s / 最长 {max(lens)}s")
        brief.append("- 最短的镜头（剪辑痕迹可疑处）: "
                     + ", ".join(f"{hms(segs[i])} 仅{lens[i]}s"
                                 for i in sorted(range(len(lens)), key=lambda i: lens[i]) if i > 0)[:200])
    if gaps:
        top = sorted(gaps, key=lambda g: -g["dur"])[:5]
        brief.append("- 最长停顿: " + ", ".join(f"{hms(g['t0'])} 停{g['dur']:.2f}s" for g in top))

    if gaps and rows:
        brief.append("")
        brief.append("## 停顿处的前后语境（犹豫/回避/换话题常在这里）")
        seen = set()
        for g in sorted(gaps, key=lambda g: -g["dur"])[:a.ctx]:
            if g["dur"] < a.ctx_min:
                continue
            before = [r for r in rows if r["t1"] <= g["t0"] + 0.2]
            after = [r for r in rows if r["t0"] >= g["t0"] + 0.05]
            if not before or not after:
                continue  # 片尾/无词静音，不是话中犹豫
            key = (before[-1]["text"], after[0]["text"])
            if key in seen:
                continue
            seen.add(key)
            brief.append(f"- `{hms(g['t0'])}` 静默 {g['dur']:.2f}s")
            brief.append(f"    - 停前: {before[-1]['text']}")
            brief.append(f"    - 停后: {after[0]['text']}")

    low = []
    for r in rows:
        for w in r.get("words") or []:
            if w.get("p", 1.0) < a.lowconf:
                low.append((w["t0"], w["w"], w["p"]))
    if low:
        brief.append("")
        brief.append(f"## 低置信词（<{a.lowconf}，必须回看原帧/原音核对，不要当事实）")
        brief += [f"- `{hms(t)}` 「{w}」 p={p}" for t, w, p in low[:40]]

    brief.append("")
    brief.append("## 转写（每行都挂在时间码上，可追溯）")
    brief += [f"- `{hms(r['t0'])}` {r['text']}" for r in rows[:400]]
    if ads_found:
        brief.insert(2, ads_mod.section(ads_found, dur))
        brief.insert(3, "")
    (d / "brief.md").write_text("\n".join(brief) + "\n", encoding="utf-8")
    print(f"events {n_ev} -> {d/'events.jsonl'}")
    print(f"brief  -> {d/'brief.md'}")


# ---------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(prog="vidlens", description="video -> evidence an LLM can read")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("video")
        p.add_argument("--out", default=None, help="output dir (default ./out/<stem>)")
        p.add_argument("--json", action="store_true")

    p = sub.add_parser("probe"); common(p); p.set_defaults(f=cmd_probe)
    p = sub.add_parser("shots"); common(p)
    p.add_argument("--thr", type=float, default=0.30, help="scene score threshold 0..1")
    p.set_defaults(f=cmd_shots)

    p = sub.add_parser("frames"); common(p)
    p.add_argument("--at", default=None, help="comma list of seconds, e.g. 12.5,90")
    p.add_argument("--from", dest="start", default="0")
    p.add_argument("--to", dest="end", default="10")
    p.add_argument("--fps", type=float, default=2.0)
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--q", type=int, default=3)
    p.set_defaults(f=cmd_frames)

    p = sub.add_parser("sheet"); common(p)
    p.add_argument("--from", dest="start", default="0")
    p.add_argument("--to", dest="end", default="20")
    p.add_argument("--cols", type=int, default=4)
    p.add_argument("--rows", type=int, default=3)
    p.add_argument("--width", type=int, default=640)
    p.add_argument("--fs", type=int, default=22, help="timestamp font size")
    p.add_argument("--offset", type=float, default=0.0,
                   help="absolute offset added to burned timestamps (for section files)")
    p.set_defaults(f=cmd_sheet)

    p = sub.add_parser("speech"); common(p)
    p.add_argument("--model", default="small", help="tiny/base/small/medium/large-v3")
    p.add_argument("--device", default="cpu")
    p.add_argument("--compute", default="int8")
    p.add_argument("--lang", default="auto")
    p.add_argument("--prompt", default=None, help="initial prompt, e.g. simplified-Chinese hint")
    p.add_argument("--beam", type=int, default=1)
    p.set_defaults(f=cmd_speech)

    p = sub.add_parser("pauses"); common(p)
    p.add_argument("--dbfs", type=float, default=-32.0)
    p.add_argument("--min-dur", dest="min_dur", type=float, default=0.45)
    p.set_defaults(f=cmd_pauses)

    p = sub.add_parser("env"); common(p)
    p.add_argument("--win", type=float, default=0.5)
    p.set_defaults(f=cmd_env)

    p = sub.add_parser("report"); common(p)
    p.add_argument("--thr", type=float, default=0.30)
    p.add_argument("--dbfs", type=float, default=-32.0)
    p.add_argument("--min-dur", dest="min_dur", type=float, default=0.45)
    p.add_argument("--model", default="small")
    p.add_argument("--device", default="cpu")
    p.add_argument("--compute", default="int8")
    p.add_argument("--lang", default="auto")
    p.add_argument("--prompt", default=None)
    p.add_argument("--beam", type=int, default=1)
    p.add_argument("--no-speech", action="store_true")
    p.add_argument("--lowconf", type=float, default=0.70, help="flag words below this probability")
    p.add_argument("--ctx", type=int, default=8, help="how many pauses to annotate with context")
    p.add_argument("--ctx-min", dest="ctx_min", type=float, default=1.2, help="min pause seconds to annotate")
    p.set_defaults(f=cmd_report)

    # web layer is optional: the core must keep working even if yt-dlp is missing
    try:
        import vidlens_web
        vidlens_web.add_subcommands(sub)
    except Exception as e:  # pragma: no cover
        print(f"[warn] web subcommands unavailable: {e}", file=sys.stderr)
    try:
        import vidlens_extra
        vidlens_extra.add_subcommands(sub)
    except Exception as e:  # pragma: no cover
        print(f"[warn] extra subcommands unavailable: {e}", file=sys.stderr)

    a = ap.parse_args()

    if False:
        pass
    a.f(a)


if __name__ == "__main__":
    main()
