#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vidlens_extra - housekeeping, diagnosis, comments, and the "no audio" path.

Why this exists
---------------
1. MCP clients time out (often 60s). A 2-hour video cannot finish in that window,
   so long work must run as a job that the client polls.
2. Caches grow. Somebody has to sweep them.
3. When things break (site redesign, model missing, ffmpeg shim gone) the user
   needs one command that says WHAT is broken, not a stack trace.
4. Some videos have no audio, or long silent stretches that still carry meaning.
   Then the evidence has to come from the picture: sample frames at scene cuts,
   spread across the timeline, and look at them.
5. A video's comment section tells you whether the content is contested. That is
   a different signal from the video itself, and it is hostile text.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

import vidlens as core
import vidlens_sanitize as S
import vidlens_web as web

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

VISUAL_MIN_FRAMES = 4
VISUAL_MAX_FRAMES = 48
VISUAL_CUT_THRESHOLD = 0.25


# --------------------------------------------------------------- housekeeping

def cache_stats(root: Path | None = None) -> dict:
    root = root or web.out_root()
    items = []
    total = 0
    if root.exists():
        for d in sorted(root.iterdir()):
            if not d.is_dir():
                continue
            size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            total += size
            items.append({"dir": d.name, "mb": round(size / 1048576, 2),
                          "mtime": int(d.stat().st_mtime)})
    items.sort(key=lambda x: -x["mb"])
    return {"root": str(root), "count": len(items), "mb": round(total / 1048576, 1),
            "items": items}


def clean_cache(days: float = 7, dry_run: bool = True, keep_brief: bool = True,
                root: Path | None = None) -> dict:
    """Delete per-video dirs older than `days`. Returns what was (or would be) removed."""
    root = root or web.out_root()
    now = time.time()
    removed, kept, freed = [], [], 0
    if not root.exists():
        return {"removed": [], "freed_mb": 0, "kept": 0}
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        age_days = (now - d.stat().st_mtime) / 86400
        if age_days < days:
            kept.append(d.name)
            continue
        size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        freed += size
        removed.append({"dir": d.name, "mb": round(size / 1048576, 2),
                        "age_days": round(age_days, 1)})
        if dry_run:
            continue
        if keep_brief:
            # keep the cheap, useful things; delete media and bulk frames
            for p in list(d.rglob("*")):
                if p.is_file() and p.suffix.lower() in (
                        ".mp4", ".mkv", ".webm", ".m4a", ".mp3", ".wav", ".jpg", ".png"):
                    p.unlink(missing_ok=True)
            if not any(d.rglob("brief.md")):
                shutil.rmtree(d, ignore_errors=True)
        else:
            shutil.rmtree(d, ignore_errors=True)
    return {"removed": removed, "freed_mb": round(freed / 1048576, 1),
            "kept": len(kept), "dry_run": dry_run}


# --------------------------------------------------------------------- doctor

def _run(cmd, timeout=30):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return -1, str(e)


def _api_reachable(status: int, body: str) -> tuple:
    """Is the API really answering, or is this a risk-control / captcha page?

    Bilibili's WAF answers 200 with an HTML challenge, so a status-only check
    reports "network ok" while every real request is blocked. Anonymous access to
    /nav answers code=-101 ("not logged in") -- that still proves the API itself
    replied, so any integer `code` counts as reachable.
    """
    if status != 200:
        return False, f"http {status}"
    try:
        payload = json.loads(body)
    except Exception:
        return False, f"http {status}，但响应不是 JSON（可能被风控/验证码拦截）"
    if isinstance(payload, dict) and isinstance(payload.get("code"), int):
        return True, f"http {status} code={payload['code']}"
    return False, f"http {status}，但响应里没有 code 字段"


def doctor() -> list[dict]:
    rows = []

    def add(name, ok, detail):
        rows.append({"check": name, "ok": bool(ok), "detail": detail})

    import sys
    add("python", sys.version_info >= (3, 9), f"{sys.version.split()[0]} @ {sys.executable}")

    ff = None
    try:
        ff = core.ffmpeg_exe()
        rc, out = _run([ff, "-version"])
        ver = (out.splitlines() or ["?"])[0][:70] if out else "?"
        add("ffmpeg", rc == 0, ver)
    except Exception as e:
        add("ffmpeg", False, str(e))

    try:
        shim = Path(core.ffmpeg_dir()) / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        add("ffmpeg shim (name yt-dlp expects)", shim.exists(), str(shim))
    except Exception as e:
        add("ffmpeg shim", False, str(e))

    rc, out = _run([sys.executable, "-m", "yt_dlp", "--version"])
    add("yt-dlp", rc == 0, out.strip().splitlines()[0] if out.strip() else "missing")

    for mod in ("faster_whisper", "imageio_ffmpeg", "numpy", "mcp"):
        try:
            __import__(mod)
            add(f"dep:{mod}", True, "ok")
        except Exception as e:
            add(f"dep:{mod}", False, str(e)[:80])

    # `find_spec` says "installed" for a package whose own import explodes (tokenizers
    # missing, av ABI mismatch). Import it for real, and name the transitive one.
    try:
        import faster_whisper
        from faster_whisper import WhisperModel  # noqa: F401
        add("dep:faster_whisper import", True,
            f"{getattr(faster_whisper, '__version__', '?')} @ {Path(faster_whisper.__file__).parent}")
    except Exception as e:
        add("dep:faster_whisper import", False, f"{type(e).__name__}: {e}"[:120])
    try:
        import tokenizers
        add("dep:tokenizers (hard dep of faster-whisper)", True,
            getattr(tokenizers, "__version__", "?"))
    except Exception as e:
        add("dep:tokenizers (hard dep of faster-whisper)", False,
            f"{type(e).__name__}: {e}  ← `pip install tokenizers`（不要用 --no-deps 装 faster-whisper）"[:140])
    try:
        import av
        ver = tuple(int(x) for x in re.findall(r"\d+", getattr(av, "__version__", "0"))[:2] or [0, 0])
        patched = web._patch_av_open() if hasattr(web, "_patch_av_open") else False
        add("dep:av", True, f"{getattr(av, '__version__', '?')}"
                            + ("（已打 metadata_errors 兼容补丁）" if ver >= (13, 0) else ""))
    except Exception as e:
        add("dep:av", False, str(e)[:80])

    # Where downloads would actually land, versus what HF thinks its cache is.
    try:
        import vidlens_models as mm
        add("model dirs", True,
            f"root={mm.MODEL_ROOT}｜whisper={mm.WHISPER_ROOT}"
            f"｜HF_HUB_CACHE={os.environ.get('HF_HUB_CACHE') or '(未设)'}"
            f"｜可用 whisper: {', '.join(mm.installed_whisper()) or '无'}")
    except Exception as e:
        add("model dirs", False, str(e)[:80])

    try:
        import vidlens_ocr as ocr
        ok, why = ocr.available()
        # An optional extra that is absent is not a broken install: most videos have
        # speech and never need OCR. Report the state, do not fail the check.
        add("ocr (optional, screen text)", True,
            "rapidocr 可用（PP-OCRv6 随包分发）" if ok
            else f'未装（可选，静音视频才需要）—— pip install "vidlens-mcp[ocr]"'
                 f'（{why[:50]}）')
    except Exception as e:      # a broken optional module must not hide the rest
        add("ocr (optional, screen text)", False, str(e)[:80])

    md = Path(core.model_dir())
    model_files = list(md.rglob("model.bin")) if md.exists() else []
    add("whisper model", bool(model_files),
        f"{md} ({round(sum(f.stat().st_size for f in model_files)/1048576)} MB)" if model_files
        else f"not found under {md}")

    # A directory named `models--Systran--faster-whisper-*` can contain one file and
    # still load-fail later. Check the four files faster-whisper actually reads.
    try:
        import vidlens_models as mm
        sizes = ("large-v3", "medium", "small", "base", "tiny")
        good = [s for s in sizes if mm.whisper_complete(s)]
        broken = [f"{s}(缺{len(mm.whisper_missing(s))})" for s in sizes
                  if mm.whisper_dir(s).exists() and not mm.whisper_complete(s)]
        add("whisper files", bool(good),
            f"完整: {', '.join(good) or '无'}｜不完整: {', '.join(broken) or '无'}"
            f"｜默认会用 {mm.resolve_whisper('')}")
    except Exception as e:
        add("whisper files", False, str(e)[:80])


    try:
        free = shutil.disk_usage(web.out_root().anchor or "C:\\").free / 1073741824
        add("disk free", free > 2, f"{free:.1f} GB on {web.out_root().anchor}")
    except Exception as e:
        add("disk free", False, str(e))

    # The cache grows by design (one directory per video, media deleted but
    # sheets/transcripts kept) and nothing prunes it automatically. Report the
    # number instead of letting the first surprise be a full disk.
    try:
        cs = cache_stats()
        big = cs["mb"] > 2048
        add("cache", not big,
            f"{cs['mb']} MB / {cs['count']} 项 @ {cs['root']}"
            + ("　偏大：`vl clean --days 7`（默认只删媒体，保留 brief.md）" if big else ""))
    except Exception as e:
        add("cache", False, str(e))

    try:
        req = urllib.request.Request("https://api.bilibili.com/x/web-interface/nav",
                                     headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            status, body = r.status, r.read(4096).decode("utf-8", "replace")
        ok, detail = _api_reachable(status, body)
        add("network: bilibili api", ok, detail)
    except Exception as e:
        add("network: bilibili api", False, str(e)[:80])
    return rows


# ------------------------------------------------------------------- comments

def bvid_of(url: str) -> str | None:
    m = re.search(r"(BV[0-9A-Za-z]{10})", url or "")
    return m.group(1) if m else None


def _get_json(url: str, timeout=20):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Referer": "https://www.bilibili.com/"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


NEG = ["假", "骗", "退钱", "垃圾", "恶心", "举报", "删", "失望", "拉黑", "割韭菜",
       "引战", "恰饭", "翻车", "不信", "质疑", "反驳", "错误", "误导", "标题党",
       "水军", "洗地", "无聊", "蹭", "抄袭", "搬运", "版权",
       # finance / consumer-protection vocabulary (added after a real miss)
       "亏", "韭菜", "宗罪", "漏洞百出", "忽悠", "取关", "上当", "骗钱",
       "高仿", "假冒", "冒充", "退充", "避雷"]
SCAM_WORDS = ["高仿", "假冒", "冒充", "假号", "仿号"]
POS = ["赞", "牛", "强", "喜欢", "厉害", "谢谢", "有用", "支持", "收藏", "好看", "震撼"]


def _download_image(url: str, dst: Path) -> Path:
    if not url:
        raise ValueError("empty url")
    url = url.replace("http://", "https://")
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                              "Referer": "https://www.bilibili.com/"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    return dst


def bili_comments(url: str, limit: int = 40, download_pics: bool = True,
                  max_pics: int = 6) -> dict:
    bv = bvid_of(url)
    if not bv:
        return {"error": "不是 B 站链接，暂不支持评论区抓取"}
    view = _get_json(f"https://api.bilibili.com/x/web-interface/view?bvid={bv}")
    if view.get("code") != 0:
        return {"error": f"view api code={view.get('code')}"}
    d = view["data"]
    aid = d["aid"]
    stat = d.get("stat") or {}
    out = {"title": S.clean(d.get("title"), 200), "aid": aid,
           "view": stat.get("view"), "like": stat.get("like"),
           "reply_count": stat.get("reply"), "danmaku": stat.get("danmaku"),
           "favorite": stat.get("favorite"), "coin": stat.get("coin"),
           "comments": [], "pages": 0, "pictures": [],
           "paid": bool(d.get("is_upower_exclusive"))}

    ps = min(20, max(1, limit))
    nxt, mode = 0, 3          # mode 3 = 按热度, 2 = 按时间
    pages = max(1, min(10, (limit + ps - 1) // ps))
    for i in range(pages):
        c = _get_json(f"https://api.bilibili.com/x/v2/reply/main?type=1&oid={aid}"
                      f"&mode={mode}&ps={ps}&pn={i + 1}&next={nxt}")
        if c.get("code") != 0:
            # legacy endpoint gives only ~3 per page, but better than nothing
            c = _get_json(f"https://api.bilibili.com/x/v2/reply?type=1&oid={aid}"
                          f"&sort=2&ps={ps}&pn={i + 1}")
            if c.get("code") != 0:
                out["error"] = f"reply api code={c.get('code')}"
                break
        data = c.get("data") or {}
        reps = data.get("replies") or []
        if not reps:
            break
        out["pages"] += 1
        for r in reps:
            ct = r.get("content") or {}
            msg = (ct.get("message") or "").strip()
            pics = [{"src": p.get("img_src"), "w": p.get("img_width"),
                     "h": p.get("img_height")} for p in (ct.get("pictures") or [])]
            if not msg and not pics:
                continue
            item = {"like": r.get("like", 0), "rcount": r.get("rcount", 0),
                    "time": r.get("ctime"), "user": (r.get("member") or {}).get("uname"),
                    "text": msg, "text_clean": S.clean(msg, 400),
                    "pictures": pics, "threats": S.scan(msg, where="comment")}
            out["comments"].append(item)
            for p in pics:
                out["pictures"].append({**p, "user": item["user"], "like": item["like"]})
        cur = data.get("cursor") or {}
        if cur.get("is_end"):
            break
        nxt = cur.get("next") or 0
        if len(out["comments"]) >= limit:
            break
        time.sleep(0.6)  # polite

    if download_pics and out["pictures"]:
        pd = web.out_root() / bv / "comment_pics"
        pd.mkdir(parents=True, exist_ok=True)
        for i, p in enumerate(out["pictures"][:max_pics]):
            try:
                dst = pd / f"c{i:02d}_{p.get('like', 0)}.jpg"
                _download_image(p["src"], dst)
                p["local"] = str(dst)
            except Exception:
                p["local"] = None

    # The pager fetches by page (20 at a time), so `limit=30` returned 36. Cut to the
    # number that was asked for and remember what was dropped, so `limit` means
    # something and the reply can say "fetched N, showing M" (R-5).
    fetched = len(out["comments"])
    if fetched > limit:
        out["comments"] = out["comments"][:limit]
        out["trimmed"] = fetched - limit

    texts = [c["text_clean"] for c in out["comments"]]
    blob = "".join(texts)
    neg = sum(blob.count(k) for k in NEG)
    pos = sum(blob.count(k) for k in POS)
    n = max(1, len(texts))
    out["neg_hits"], out["pos_hits"] = neg, pos
    out["neg_per_100"] = round(neg * 100 / n, 1)
    # 点赞加权：高赞的抱怨比零赞的牢骚更有信号
    total_likes = sum((c["like"] or 0) + 1 for c in out["comments"]) or 1
    neg_likes = sum((c["like"] or 0) + 1 for c in out["comments"]
                    if any(k in c["text_clean"] for k in NEG))
    out["neg_like_ratio"] = round(neg_likes * 100 / total_likes, 1)
    out["scam_reports"] = len([c for c in out["comments"]
                               if any(k in c["text_clean"] for k in SCAM_WORDS)])
    out["reply_per_1k_views"] = (round((out["reply_count"] or 0) * 1000 / max(1, out.get("view") or 1), 2))
    ratio = (out.get("like") or 0) / max(1, out.get("view") or 1)
    out["like_rate"] = round(ratio * 100, 2)
    score = 0
    score += 2 if out["neg_per_100"] >= 8 else (1 if out["neg_per_100"] >= 3 else 0)
    score += 2 if out["neg_like_ratio"] >= 40 else (1 if out["neg_like_ratio"] >= 15 else 0)
    score += 1 if out["reply_per_1k_views"] >= 3 else 0
    score += 1 if ratio < 0.02 else 0
    score += 2 if out.get("scam_reports") else 0
    out["controversy"] = ["低", "低", "中", "高"][min(3, score)]
    out["threat_count"] = sum(len(c["threats"]) for c in out["comments"])
    return out


def comments_block(info: dict, top: int = 8) -> str:
    if info.get("error"):
        return f"## 评论区\n\n- 拿不到：{info['error']}\n"
    L = ["## 评论区信号（启发式，不是结论）", ""]
    L.append(f"- 播放 {info.get('view')} / 点赞 {info.get('like')}（点赞率 {info.get('like_rate')}%）")
    L.append(f"- 评论数 {info.get('reply_count')}（每千播放 {info.get('reply_per_1k_views')} 条）"
             f"，弹幕 {info.get('danmaku')}")
    L.append(f"- 抓取到 {len(info['comments'])} 条，负面词 {info['neg_hits']} 次 / 正面词 {info['pos_hits']} 次"
             f"（每百条负面 {info['neg_per_100']}；点赞加权负面占比 {info.get('neg_like_ratio')}%）")
    if info.get("trimmed"):
        L.append(f"- 另有 {info['trimmed']} 条已抓到但按 limit 截掉（要更多就传更大的 limit）")
    L.append(f"- **争议度估计：{info['controversy']}**（词频+点赞加权+互动比，启发式；需人工看原评论）")
    if info.get("scam_reports"):
        L.append(f"- ⚠ **仿号/诈骗报告 {info['scam_reports']} 条**：评论区在举报冒充账号，"
                 "这类内容的私信、群、链接都不要信")
    if info.get("threat_count"):
        L.append(f"- ⚠ 评论里发现 {info['threat_count']} 条夹带指令/藏字的特征，已隔离")
    L.append("")
    L.append("### 高赞评论")
    for c in sorted(info["comments"], key=lambda x: -x["like"])[:top]:
        flag = " ⚠" if c["threats"] else ""
        L.append(S.fence(f"[{c['like']}赞/{c['rcount']}回复]{flag} {c['text_clean']}"))
    pics = info.get("pictures") or []
    if pics:
        L.append("")
        L.append(f"### 评论图（{len(pics)} 张，已下载）")
        for p in pics:
            L.append(S.fence(f"[{p.get('like')}赞] {p.get('user')} · {p.get('w')}x{p.get('h')}\n"
                             f"{p.get('local') or p.get('src')}"))
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------- visual

LAST_ERRORS: list[tuple[float, str]] = []


def _label_frame(video: str, t: float, dst: Path, width: int) -> bool:
    font = core.find_font() if hasattr(core, "find_font") else None
    can_label = bool(font) and (core.has_drawtext() if hasattr(core, "has_drawtext") else True)
    vf = f"scale={width}:-2"
    if can_label:
        fp = str(font).replace("\\", "/").replace(":", "\\:")
        # a raw ':' inside drawtext text breaks the filter graph - escape it
        label = core.hms(t).replace(":", "\\:")
        vf += (f",drawtext=fontfile='{fp}':text='{label}':x=6:y=6:"
               f"fontsize=20:fontcolor=yellow:box=1:boxcolor=black@0.6")
    ff = core.ffmpeg_exe()
    r = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-ss", f"{t:.3f}",
                        "-i", video, "-frames:v", "1", "-vf", vf, "-q:v", "3",
                        "-y", str(dst)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120)
    ok = dst.exists() and dst.stat().st_size > 0
    if not ok:
        LAST_ERRORS.append((round(t, 2), (r.stderr or "")[:200]))
    return ok


def tile(frames: list[Path], dst: Path, cols=6, rows=4) -> Path | None:
    if not frames:
        return None
    d = frames[0].parent
    # renumber so ffmpeg's sequence input is contiguous
    for i, f in enumerate(frames):
        f.rename(d / f"lbl_{i:03d}.jpg")
    seq = sorted(d.glob("lbl_*.jpg"))
    ff = core.ffmpeg_exe()
    empty = max(0, cols * rows - len(seq))
    # pad with black frames so the grid stays rectangular
    if empty:
        blank = d / f"lbl_{len(seq):03d}.jpg"
        subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                        "-i", "color=c=black:s=480x270:d=1", "-frames:v", "1",
                        "-y", str(blank)], check=False)
        for j in range(empty - 1):
            shutil.copy2(blank, d / f"lbl_{len(seq)+1+j:03d}.jpg")
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-framerate", "1",
                    "-i", str(d / "lbl_%03d.jpg"), "-vf", f"tile={cols}x{rows}",
                    "-frames:v", "1", "-q:v", "3", "-y", str(dst)], check=False)
    return dst if dst.exists() else None


def visual_scan(url: str, n: int = 24, cols: int = 6, rows: int = 4,
                height: int = 360, width: int = 480) -> dict:
    """Sample n frames across the timeline and build one or more contact sheets."""
    n = max(VISUAL_MIN_FRAMES, min(VISUAL_MAX_FRAMES, int(n)))
    meta, threats = web.fetch_meta(url)
    dur = float(meta.get("duration") or 0)
    d = web.out_root() / (meta.get("id") or "unknown")
    work = d / f"visual_{n}"
    work.mkdir(parents=True, exist_ok=True)
    for old in list(work.glob("sheet_*.jpg")) + list(work.glob("f_*.jpg")) \
            + list(work.glob("lbl_*.jpg")):
        old.unlink(missing_ok=True)
    vid = web.download_video_lowest(url, d, height)
    cuts = web.shot_cuts(vid, VISUAL_CUT_THRESHOLD)
    if len(cuts) >= n:
        step = len(cuts) / n
        picks = [cuts[min(len(cuts) - 1, int(i * step))] for i in range(n)]
    else:
        picks = [round(dur * (i + 0.5) / n, 2) for i in range(n)]
    picks = sorted({round(p, 2) for p in picks})
    frames = []
    for i, t in enumerate(picks):
        f = work / f"f_{i:03d}.jpg"
        if _label_frame(str(vid), t, f, width):
            frames.append(f)
    per_sheet = cols * rows
    sheets = []
    for k in range(0, len(frames), per_sheet):
        dst = work / f"sheet_{int(picks[0])}_{k//per_sheet}.jpg"
        got = tile(frames[k:k + per_sheet], dst, cols, rows)
        if got:
            sheets.append(str(got))
    if not web.local_path(url):
        vid.unlink(missing_ok=True)      # local input: `vid` IS the user's file
    # keep only the contact sheets; individual frames are already tiled into them
    for old in list(work.glob("f_*.jpg")) + list(work.glob("lbl_*.jpg")):
        old.unlink(missing_ok=True)
    return {"id": meta.get("id"), "duration": dur, "cuts": len(cuts),
            "picked": picks, "sheets": sheets, "threats": threats,
            "errors": LAST_ERRORS[-3:] if not frames else []}


# ------------------------------------------------------------------- long plan

def plan(url: str, window: float = web.DEFAULT_CHAPTER_WINDOW,
         meta: dict | None = None) -> dict:
    """Split a long video into cheap passes: chapters from cuts + long silences."""
    if meta is None:
        meta, _ = web.fetch_meta(url)
    dur = float(meta.get("duration") or 0)
    d = web.out_root() / (meta.get("id") or "unknown")
    try:
        cuts = json.loads((d / "shots.json").read_text(encoding="utf-8"))["cuts"] \
            if (d / "shots.json").exists() else []
    except (OSError, ValueError, KeyError, TypeError):
        cuts = []
    gaps = web.read_pauses(d)
    chapters = web.plan_chapters(dur, cuts, gaps, window)
    # Where the boundaries came from decides how the plan should be WORDED: a grid
    # is not a chapter, and calling it one makes the model invent narrative turns.
    source = ("cuts" if cuts
              else "gaps" if any(float(g.get("dur") or 0) >= 2.0 for g in gaps)
              else "grid")
    return {'id': meta.get('id'), 'duration': dur, 'chapters': chapters, 'source': source,
            'advice': ('先 video_brief 拿全局；再按章节用 video_window 读台词、'
                       'video_sheet 看画面，不要一次下整片。')}


# ---------------------------------------------------------------------- jobs

JOBS: dict[str, dict] = {}


def gc_jobs(max_age: float = 3600.0) -> None:
    now = time.time()
    for k in list(JOBS):
        if now - JOBS[k]['t0'] > max_age:
            JOBS.pop(k, None)


def job_start(fn, *args, **kwargs) -> str:
    """Run a slow callable in a thread; the client polls instead of timing out."""
    import threading, uuid
    gc_jobs()
    jid = uuid.uuid4().hex[:8]
    JOBS[jid] = {'t0': time.time(), 'status': 'running', 'stage': 'queued',
                 'pct': 0, 'result': None, 'error': None}
    st = JOBS[jid]

    def progress(stage: str, pct: int) -> None:
        st['stage'], st['pct'] = stage, max(st['pct'], int(pct))

    def run():
        try:
            st['result'] = fn(progress, *args, **kwargs)
            st['status'], st['stage'], st['pct'] = 'done', 'done', 100
        except BaseException as e:  # noqa: BLE001 - a job must never die silently
            st['status'] = 'error'
            st['error'] = f'{type(e).__name__}: {e}'

    threading.Thread(target=run, daemon=True).start()
    return jid


def job_status(jid: str, wait: float = 0.0) -> str:
    deadline = time.time() + max(0.0, min(60.0, wait))
    while True:
        st = JOBS.get(jid)
        if not st:
            return f'ERROR: 没有这个任务 {jid}（可能已清理）'
        if st['status'] == 'done':
            return st['result'] or '（无结果）'
        if st['status'] == 'error':
            return f"ERROR: {st['error']}"
        if time.time() >= deadline:
            return (f"running  stage={st['stage']}  pct={st['pct']}%  "
                    f"elapsed={int(time.time() - st['t0'])}s\n"
                    f'继续轮询：video_job(job_id="{jid}", wait_seconds=20)')
        time.sleep(0.4)


# --------------------------------------------------- paid videos: direct url path

def bili_ids(bv: str) -> tuple[int, int, float]:
    d = _get_json(f"https://api.bilibili.com/x/web-interface/view?bvid={bv}")["data"]
    pages = d.get("pages") or []
    cid = pages[0]["cid"] if pages else None
    return d["aid"], cid, float(d.get("duration") or 0)


def bili_player_info(bv: str) -> dict:
    """Platform-declared BGM + subtitle login gate (metadata only)."""
    aid, cid, _dur = bili_ids(bv)
    d = _get_json(f"https://api.bilibili.com/x/player/wbi/v2?bvid={bv}&cid={cid}"
                  ).get("data") or {}
    bgm = d.get("bgm_info") or None
    if isinstance(bgm, dict):
        title = (bgm.get("music_title") or "").strip()
        m = re.match(r"^发现《(.*)》$", title)
        if m:
            bgm = {**bgm, "music_title": m.group(1).strip()}
    return {"bgm": bgm,
            "need_login_subtitle": bool(d.get("need_login_subtitle")),
            "asr_language": d.get("asr_language") or "",
            "cid": cid}


def direct_play_url(bv: str, cid: int, qn: int = 32) -> str | None:
    """Some videos (e.g. 充电专属) fail yt-dlp's section download but still expose
    a playable durl through the player API. This is the fallback."""
    p = _get_json(f"https://api.bilibili.com/x/player/playurl?bvid={bv}&cid={cid}"
                  f"&qn={qn}&fnval=16")
    d = p.get("data") or {}
    urls = [s.get("url") for s in (d.get("durl") or []) if s.get("url")]
    return urls[0] if urls else None


def _ff_headers() -> str:
    return f"Referer: https://www.bilibili.com/\r\nUser-Agent: {UA}\r\n"


def direct_frame(play_url: str, t: float, dst: Path, width: int = 960) -> bool:
    ff = core.ffmpeg_exe()
    cmd = [ff, "-hide_banner", "-loglevel", "error", "-headers", _ff_headers(),
           "-ss", f"{t:.3f}", "-i", play_url, "-frames:v", "1",
           "-vf", f"scale={width}:-2", "-q:v", "3", "-y", str(dst)]
    subprocess.run(cmd, capture_output=True, timeout=180)
    return dst.exists() and dst.stat().st_size > 0


def direct_sheet(bv: str, cid: int, t0: float, t1: float, cols: int = 4,
                 rows: int = 3, width: int = 480, outdir: Path | None = None):
    """Build a contact sheet without yt-dlp, seeking straight into the play URL."""
    url = direct_play_url(bv, cid)
    if not url:
        return None, []
    d = Path(outdir) if outdir else (web.out_root() / bv / "direct")
    d.mkdir(parents=True, exist_ok=True)
    n = min(cols * rows, 24)
    dur = max(0.1, t1 - t0)
    times = [round(t0 + dur * (i + 0.5) / n, 2) for i in range(n)]
    frames = []
    for i, t in enumerate(times):
        f = d / f"f_{i:03d}.jpg"
        if direct_frame(url, t, f, width):
            frames.append(f)
    sheet = d / f"sheet_{int(t0)}_{int(t1)}.jpg"
    got = tile(frames, sheet, cols, rows)
    return got, times


def direct_frames(bv: str, cid: int, ts: list[float], outdir: Path,
                  width: int = 960) -> list[Path]:
    url = direct_play_url(bv, cid)
    if not url:
        return []
    outdir.mkdir(parents=True, exist_ok=True)
    made = []
    for t in ts:
        dst = outdir / f"t{int(round(t*1000)):09d}ms.jpg"
        if direct_frame(url, t, dst, width):
            made.append(dst)
    return made


# ------------------------------------------------------------------- CLI glue

def cmd_clean(a):
    st = cache_stats()
    r = clean_cache(a.days, dry_run=a.dry_run, keep_brief=not a.all)
    print(f"cache root: {st['root']}  total {st['mb']}MB in {st['count']} dirs")
    print(f"{'DRY-RUN' if r.get('dry_run') else 'DELETED'}: {len(r['removed'])} dirs, {r['freed_mb']}MB")
    for it in r['removed'][:20]:
        print(f"  {it['dir']}  {it['mb']}MB  age {it['age_days']}d")


def cmd_doctor(a):
    rows = doctor()
    bad = [r for r in rows if not r['ok']]
    print(f"{len(rows) - len(bad)}/{len(rows)} ok")
    for r in rows:
        print(f"{'OK ' if r['ok'] else 'BAD'}  {r['check']}: {r['detail']}")
    try:
        import vidlens_sensevoice as sv
        st = sv.status()
        if st["available"]:
            print(f"OK   asr backend: sensevoice (local, no network)  model={st['model']}")
        else:
            print("INFO asr backend: whisper (SenseVoice 不可用；本地缓存命中时不联网)")
    except Exception as e:
        print(f"INFO asr backend: whisper ({type(e).__name__}: {e})")


def cmd_comments(a):
    info = bili_comments(a.url, limit=a.limit)
    blk = comments_block(info)
    d = web.out_root() / (bvid_of(a.url) or 'unknown')
    d.mkdir(parents=True, exist_ok=True)
    (d / 'comments.md').write_text(blk, encoding='utf-8')
    print(f"comments {len(info.get('comments') or [])} -> {d / 'comments.md'}")
    print(f"controversy {info.get('controversy')}  neg/100 {info.get('neg_per_100')}  "
          f"like_rate {info.get('like_rate')}%")


def cmd_scan(a):
    r = visual_scan(a.url, n=a.n, cols=a.cols, rows=a.rows)
    print(f"picked {len(r['picked'])} frames, cuts {r['cuts']}, sheets {len(r['sheets'])}")
    for s in r['sheets']:
        print(s)


def cmd_plan(a):
    p = plan(a.url, window=a.window)
    print(f"duration {core.hms(p['duration'])}  chapters {len(p['chapters'])}")
    for c in p['chapters']:
        print(f"  {core.hms(c['from'])} -> {core.hms(c['to'])}")


def cmd_models(a):
    import vidlens_models as m
    if getattr(a, "recommend", False):
        r = m.recommend()
        print(f"ram={r['ram_gb']}GB cpu={r['cpu_cores']}cores disk={r['disk_free_gb']}GB")
        print(f"recommended_asr={r['recommended_asr']} optional_audio={r['optional_audio']}")
        return
    for it in m.catalog():
        mark = "installed" if it["installed"] else "missing"
        print(f"{it['name']:18s} {it['size_mb']:5d}MB  {mark:9s}  {it['purpose']}")


def add_subcommands(ap):
    p = ap.add_parser('clean', help='delete old per-video dirs (media only by default)')
    p.add_argument('--days', type=float, default=7)
    p.add_argument('--dry-run', dest='dry_run', action='store_true')
    p.add_argument('--all', action='store_true', help='remove whole dirs, not just media')
    p.set_defaults(f=cmd_clean)

    p = ap.add_parser('doctor', help='self-check: python/ffmpeg/yt-dlp/deps/model/disk/net')
    p.set_defaults(f=cmd_doctor)

    p = ap.add_parser('comments', help='comment-section signals (bilibili, no login)')
    p.add_argument('url')
    p.add_argument('--limit', type=int, default=40)
    p.add_argument('--json', action='store_true')
    p.set_defaults(f=cmd_comments)

    p = ap.add_parser('scan', help='sample frames across a whole video (no-audio path)')
    p.add_argument('url')
    p.add_argument('--n', type=int, default=24)
    p.add_argument('--cols', type=int, default=6)
    p.add_argument('--rows', type=int, default=4)
    p.add_argument('--json', action='store_true')
    p.set_defaults(f=cmd_scan)

    p = ap.add_parser('plan', help='split a long video into cheap passes')
    p.add_argument('url')
    p.add_argument('--window', type=float, default=web.DEFAULT_CHAPTER_WINDOW)
    p.add_argument('--json', action='store_true')
    p.set_defaults(f=cmd_plan)

    p = ap.add_parser('models', help='list local models + hardware advice (no download)')
    p.add_argument('--recommend', action='store_true')
    p.set_defaults(f=cmd_models)
