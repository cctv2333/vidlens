# vidlens

[![ci](https://github.com/cctv2333/vidlens/actions/workflows/ci.yml/badge.svg)](https://github.com/cctv2333/vidlens/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/vidlens-mcp.svg?cacheSeconds=600)](https://pypi.org/project/vidlens-mcp/)
[![MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[中文](README.md) · **English**

Turn a **publicly viewable** video into "evidence a model can actually read".
No cloud API, no vision model, no GPU. One rule: **download the minimum bytes**.

## In one minute

I have eyes (I can look at images) but no ears. So I need exactly two things:

1. sound → text with timestamps (the only part that must borrow a tool);
2. a frame at any moment → I look at it myself.

The tool only **samples and quantifies**. Understanding stays in the model.

## Three-tier budget (measured, 7-minute 1080p video)

| Route | Size | What you get |
|---|---|---|
| Whole file, 1080p | 105.5 MB | everything |
| **Audio only** | **7.3 MB** | **100% of the speech (139 segments / 2184 chars, identical to the 1080p transcript)** |
| One 20-second section | 0.9 MB | the picture for those 20 seconds |
| Platform subtitles (if any) | 0 MB | the site's own subtitle track; not even audio |

**Resolution contributes nothing to speech.** You only need native resolution for a
single frame when you must read small text (code, tables, UI values).

## Install

Python 3.10+.

**A. From PyPI (for users; no clone needed)**

```bash
pipx install "vidlens-mcp[all]"      # or: pip install "vidlens-mcp[all]"
vidlens doctor                        # CLI self-check
# MCP config is just: {"command": "vidlens-mcp"}
```

Artifacts and cache live in `%LOCALAPPDATA%\vidlens\` (POSIX: `~/.local/share/vidlens/`);
override with `VIDLENS_OUT` / `VIDLENS_BIN`. Models stay wherever you keep models.

**B. From source (development)**

```bat
install.cmd
```

Defaults after a source install: artifacts in `out/` inside the checkout
(`VIDLENS_OUT`), ffmpeg shim in `bin/` (`VIDLENS_BIN`), models under
`VIDLENS_MODEL_ROOT` (default `%LOCALAPPDATA%\vidlens\models`, or XDG on POSIX;
a pre-existing `D:\dev\models` is reused only when it already exists).

**DeepSeek Harness plugin** (21 native tools) lives in a second repo:
<https://github.com/cctv2333/dsh-vidlens>

## Commands

### Online videos (no download first)

```bash
vl meta  <url>                      # page metadata only, 0 bytes of media
vl grab  <url> --lang en            # subtitles first; else audio only -> transcript + pauses + brief
vl grab  <url> --cuts               # also scan shot cuts (lowest-quality video, ~14-21MB, deleted after)
vl clip  <url> --from 02:00 --to 02:20 --sheet   # only those 20 seconds, timecoded contact sheet
```

### Local files

```bash
vl probe  a.mp4
vl shots  a.mp4 --thr 0.30
vl frames a.mp4 --at 19.5,21.0
vl sheet  a.mp4 --from 0 --to 30 --cols 5 --rows 4
vl speech a.mp4 --lang en
vl pauses a.mp4
vl env    a.mp4                      # loudness envelope as text
vl report a.mp4 --lang en            # full local pass -> brief.md + events.jsonl
```

**Every MCP tool accepts local paths too** (since 1.6.0): `D:\a.mp4`, `file:///D:/a.mp4`,
`~/a.mov`, quoted paths. A local file is never downloaded and never goes through yt-dlp.
Two things are missing by nature: **platform subtitles** (falls back to local ASR) and
**comments** (the tool says so instead of inventing them).

## MCP surface (18 tools)

`url` accepts a public link **or a local path**.

**Basics**

| Tool | Downloads | Purpose |
|---|---|---|
| `video_meta(url)` | 0 | title / channel / duration / views / subtitles |
| `video_plan(url, window=300)` | 0 | chapters from cuts + long silences, plus a viewing order |
| `video_subs(url, lang=zh)` | 0 | platform subtitles (human over auto), timecoded |
| `video_brief(url, ..., level="digest")` | subtitles 0; audio only when there are none | **digest** (~1.5k chars: chapters + 5 key lines + path to the full report); `level="full"` gives the 6–9k report; >20 min without subtitles returns chapters only until `full=true` |
| `video_watch(url, minutes=5, cursor="next")` | that window's audio (or cache) | watch in segments, reporting progress |
| `video_window(url, start, end)` | 0 with cache | transcript + pauses for one window |
| `video_full(url, confirm=True)` | whole file | must be confirmed explicitly |

**Long videos (timeout escape hatch)**

| Tool | Purpose |
|---|---|
| `video_job_start(url, scan_cuts, comments)` | background job, returns `job_id` immediately |
| `video_job(job_id, wait_seconds=20)` | poll phase + percentage, then the report |

Job state lives in the server process: **restarting the MCP client loses unfinished jobs**
(rerun; cached media survives).

**Picture / silent videos**

| Tool | Downloads | Purpose |
|---|---|---|
| `video_visual_scan(url, n=24)` | lowest-quality video (7 min ≈ 14MB) | sample n frames across the film, timecoded contact sheets |
| `video_sheet(url, start, end, cols, rows)` | that section (20 s ≈ 0.9MB) | contact sheet for one range |
| `video_frames(url, at=[...])` | that section | up to 6 exact frames |
| `video_ocr(url, start, end, n=12)` | lowest quality of that range | **read on-screen text into timecoded text** (local OCR, offline) — the workhorse for videos with no speech |

**Sound events beyond speech**

| Tool | Downloads | Purpose |
|---|---|---|
| `video_soundscape(url, start, end)` | that section's audio (60 s ≈ 1MB) | AudioSet's 527 sound classes + probability + timecode. **Drinking/swallowing has no class**; infer from water sounds plus the frame |

**Judging what the video is**

| Tool | Downloads | Purpose |
|---|---|---|
| `video_comments(url, limit=40)` | 0 | engagement ratio, sentiment words, controversy heuristic |
| `vidlens_models(action=list)` | 0 | local model dirs, sizes, hardware advice, **the real paths on this machine**; `action=download` asks first, then downloads with `confirm=true` |
| `vidlens_doctor()` | 0 | python / ffmpeg / yt-dlp / extras / models / disk / network |

Wire it into Chatbox / Claude / Cursor as a stdio server:

```
command : <python>
args    : <checkout>\vl_mcp.py     # or just: vidlens-mcp
env     : PYTHONIOENCODING=utf-8 ; HF_HUB_DISABLE_XET=1
```

Generic JSON is in `mcp.example.json`. **MCP is stdio: the server must never print to
stdout** — library calls run with `verbose=False`, downloads and ASR are serialized by
`_MEDIA_LOCK`, and `contextlib.redirect_stdout` must never hijack `sys.stdout` for long.

Sites that need cookies (Douyin and friends) are left alone by default; the user opts in:

```
VIDLENS_COOKIES=/path/cookies.txt
# or
VIDLENS_COOKIES_FROM_BROWSER=chrome   # edge / firefox / chromium
```

**The browser must be closed.** While it runs, its cookie database is locked and cannot be
copied. And whether that browser has cookies for the site at all is a separate question: if you
never signed in, there is nothing to read, and the tool will not invent it. With recent
Chrome/Edge App-Bound encryption, an exported `cookies.txt` plus `VIDLENS_COOKIES` is the
reliable route.

**Inline image policy** (an MCP image block is base64 on the wire; one 340KB sheet ≈ 450k chars):

```
VIDLENS_INLINE_IMAGES=auto    # default: inline only ≤200KB, otherwise give the path
VIDLENS_INLINE_IMAGES=always  # inline everything
VIDLENS_INLINE_IMAGES=never   # paths only
```

Every heavier result ends with `[cost] this reply ≈N tok` so you can decide before calling again.

## Silent (caption-only) videos

A large share of knowledge videos have **no speech and no subtitles; all text is burned into
the picture**. `video_brief` says so up front ("almost no speech, 0 effective lines"), then
`video_ocr` reads the n sampled frames, merges the same line across frames, drops watermarks
and diagram labels, and returns quotable timecoded text (12 frames ≈ 1.3k tokens — an order of
magnitude cheaper than looking at frames one by one).

OCR is an optional extra. The engine is [RapidOCR](https://github.com/RapidAI/RapidOCR)
(Apache-2.0); PP-OCRv6 models ship inside the wheel (~30MB), so once installed it is
**fully offline**. The first `video_ocr` call does not download in secret: it tells you the
size, the target directory and how to change it; call again with `install=true` to proceed.

| Variable | Effect | Default |
|---|---|---|
| `VIDLENS_OCR_TARGET` | install here (added to `sys.path`, never into system dirs) | this interpreter's `site-packages` (usually **C:** on Windows) |
| `VIDLENS_OCR_AUTO_INSTALL` | `ask` (default) / `auto` / `off` | `ask` |

## Long videos: sample by default, full only on request

1. `video_meta` → worth watching at all?
2. `video_plan` → chapters with zero download;
3. pick 2–3 sections: `video_window` for lines, `video_sheet` for picture;
4. only when the user asks for "complete / verbatim / whole film": `video_brief(full=true)`,
   and beyond 60 seconds use `video_job_start(full=true)` + `video_job`.

Above 20 minutes without platform subtitles, `video_brief` returns **chapters only** and does
not quietly download the full audio.

## Local ASR: SenseVoice (preferred) / Whisper

`VIDLENS_ASR=auto` uses SenseVoice when `sherpa-onnx`, its model and token table are all
present, and falls back to faster-whisper otherwise. **Models are never downloaded twice.**

- Point at existing weights:
  `VIDLENS_SENSEVOICE_MODEL=/path/sense-voice.onnx`, `VIDLENS_SENSEVOICE_TOKENS=/path/tokens.txt`
  (candidates are probed across the model root, the user data dir and FlashVoice's own copy).
- One pass returns `text`, `lang` (zh/en/yue/ja/ko), `emotion`, `event`
  (Speech/BGM/Laughter/Applause/Cry/…) and word timestamps.
- Forcing the old backend: `VIDLENS_ASR=whisper`. Whisper is loaded with
  `local_files_only=True` first, so a cache hit means **no network**.
- A new conversation starts a new MCP process: the model is reloaded into RAM (≈1.5 s) but
  **weights are not re-downloaded**. Load ≠ download.

## Music metadata (platform data first)

- **Bilibili**: `player/wbi/v2` exposes `bgm_info` with title and link; it shows up in
  `video_meta`, in the brief's music section and in `video_audio`.
- **Elsewhere**: scan the title/description for `BGM:` / `music:` / `「…」` style hints.
  That is text, not audio fingerprinting.
- Platform labels describe the **whole video** and can be missing or wrong.

## Model directories / downloads

```
vidlens_models(action="list")                                     # dirs + real paths
vidlens_models(action="download", name="ced-mini")                # size + target only
vidlens_models(action="download", name="ced-mini", confirm=true)  # actually download
```

| Variable | Effect | Default |
|---|---|---|
| `VIDLENS_MODEL_ROOT` | the whole model tree (whisper / sensevoice / audio-tagging) | `%LOCALAPPDATA%\vidlens\models` (XDG on POSIX); a pre-existing `D:\dev\models` is reused only when it exists |
| `VIDLENS_MODEL_DIR` / `VIDLENS_TAGGING_DIR` | override whisper / sound events individually | subdirectories of the above |
| `VIDLENS_MODEL_AUTO_DOWNLOAD` | `ask` / `auto` (**≤20MB only**) / `off` | `ask` |

Downloadable: `ced-mini` 10MB, `whisper-tiny` 75MB, `whisper-base` 145MB, `whisper-small` 484MB.
**Whisper no longer downloads silently.** SenseVoice (937MB) is explained, never fetched for you.

- **CED-mini** (sherpa-onnx `AudioTagging` + k2-fsa int8 + AudioSet label table) classifies
  527 sound events — it is **not ASR**. Measured: 0.14 s load, 43 ms inference on 28 s of audio;
  download 10.0MB in 52 s. It sees chewing, knocking, water, glass clinks, scraping, plastic
  bags, applause, laughter. **Drinking/swallowing has no AudioSet class** — that needs CLAP
  zero-shot or a small trained classifier.
- **AcoustID** is audio fingerprinting, not a model. Needs Chromaprint `fpcalc` plus a client
  key, rate-limited and non-commercial only, and does not guarantee a track title. Lower
  priority than platform metadata.

## Accents, dialects, subtitles

- **Human subtitles** uploaded by the creator are the most reliable: `video_subs` or
  `video_brief`, 0 download.
- **Auto captions** are the platform's own ASR: free but fallible, still better than nothing.
- **Bilibili AI captions** appear as `has_auto_subs: ["ai-zh", …]`, but anonymous
  `player/v2` usually returns nothing; set `VIDLENS_COOKIES_FROM_BROWSER=edge` (or chrome /
  firefox) and retry. Subtitle matching already includes `ai-zh, ai-en, ai-*`.
- **No subtitles at all**: SenseVoice first; pass `lang=yue` for Cantonese and similar.
  Heavy accents still fail. For the old Whisper backend add a prompt: `VIDLENS_ASR=whisper`,
  `prompt=...`.
- **Burned-in captions**: grab frames with `video_sheet` / `video_frames` and read them.
- Low-confidence words are listed in the brief and must be checked against the picture or the
  original audio.

## Artifacts

```
out/<video id>/
  meta.json          metadata + risk scan
  transcript.jsonl   word-level timestamps + per-word confidence
  transcript.srt     subtitles
  pauses.json        mid-sentence pauses
  brief.md           sources / risk scan / structure / pause context / low-confidence words / next steps
  clip_<a>_<b>/      on-demand sections and sheets (media deleted by default)
```

## Ads are skipped

Sponsor reads, promo codes, "link in bio" — **zero value, never in the summary**.
`vidlens_ads.py` weights sponsor/promo vocabulary, clusters hits by **time proximity**, and
only flags a segment when it is long enough and dense enough. The brief lists the skipped
range with timecodes and removes it from the body; `transcript.jsonl` keeps the original text
so nothing is lost. Measured: a 40-minute video flagged `20:02.780 → 21:39.060` (96 s, 4%);
an ad-free video flagged 0.

## Safety rules (encoded in the code)

1. **Public only.** No login walls, no paywalls, no captcha solving, no cookie theft. If the
   site says "sign in", we stop and say why. Cookies are opt-in via environment variables.
2. **No crawler.** One video per call, `--sleep-requests 0.6`, `--sleep-interval 1–3`,
   backoff retries. This protects "you can still watch it later".
3. **External text is data, never instructions.** Titles, descriptions and subtitles go through
   `vidlens_sanitize` (zero-width and bidi characters, ANSI, payload patterns). Truthfulness is
   not asserted; the brief shows sources and risk levels instead.
4. **Never trust exit codes.** yt-dlp can "succeed" with an empty shell for a dead video;
   `check_meta()` validates id/title/duration and stops.

## Cache maintenance

```bash
vl clean --days 7 --dry-run      # default: media only, brief.md kept
vl clean --days 7                # really delete
vl clean --days 30 --all         # remove the whole directory
vl doctor                        # 11 self-checks
vl comments <url>                # comment signals -> out/<id>/comments.md
vl scan <url> --n 24             # whole-film sampled contact sheets
vl plan <url> --window 300       # chapter plan for long videos
vl models                        # local model dirs (read-only)
vl models --recommend            # advice from RAM/CPU/disk
```

## Tests

```bash
python -m unittest discover -s tests   # 228 tests, 1 skipped; network-free by default
```

CI runs Ubuntu and Windows on Python 3.10 and 3.12. Releases go out on a `v*` tag with OIDC
(no PyPI or npm tokens). **`pyproject.toml` must not contain a BOM.**

## Troubleshooting (all of these happened on a real machine)

| Symptom | Cause | Fix |
|---|---|---|
| `No module named 'faster_whisper'` | ASR extras missing, or pip installed into another interpreter | `pip install "vidlens-mcp[all]"`, then confirm `python -c "import faster_whisper"` uses that interpreter |
| `No module named 'tokenizers'` | faster-whisper installed with `--no-deps` | `pip install tokenizers`; `doctor` now checks it separately |
| `LocalEntryNotFoundError: whisper 'small'` | default is small but only tiny/base exists, or the folder holds one file | since 1.7.0 the tool **falls back to whatever is installed** and says so; `VIDLENS_WHISPER_MODEL=tiny` to pin |
| "timeout" on a download, then minutes of silence | a second download queued behind the first one's file lock | `vidlens_models(action="status")`; **one download at a time** — the second is refused immediately, with the reason |
| download says ok, later "not local" | only the directory name was checked | the four required files are now verified: `model.bin` / `config.json` / `tokenizer.json` / `vocabulary.txt` |
| weights landed in `F:\hf-cache` while the tool looks in C: | `snapshot_download` honoured the ambient HF cache | we pass `cache_dir=<model dir>` explicitly; `doctor` prints both |
| Windows `your machine does not support them` (symlinks), double disk | no developer mode: hub writes blobs *and* snapshots | `HF_HUB_DISABLE_SYMLINKS=1` is set automatically |
| listed in `models list`, "unknown model" on download | two hand-written lists | since 1.7.0 one registry drives both and marks *downloadable* vs *bring your own* |
| `TypeError: open() got an unexpected keyword argument 'metadata_errors'` | faster-whisper 1.2.x vs av>=13 | a runtime shim drops that keyword; or `pip install "av<13"` |
| a 484MB fetch dies at the host's 30s timeout | downloading through a generic shell tool | use `vidlens_models(action="download", confirm=true)` (900s in the plugin) |

Every error line carries a stable code: `ERROR[E_AUTH]` (cookie/login), `E_DEP` (missing dependency or
model), `E_URL` (URL shape), `E_SOURCE` (site/extractor/DRM), `E_TIMEOUT`, `E_MEDIA` (unreadable file),
`E_OTHER`. The sentence after the code is the human explanation.
## Known limits

- Platform subtitle availability varies by site and time; Bilibili's AI captions usually need
  a login.
- OCR samples frames uniformly, so very fast captions can slip through between frames.
- `video_soundscape` sees sound classes, not events ("chewing" ≠ "eating a meal").
- Long-video ASR runs on CPU: a 45-minute film is minutes of work, not seconds.
- iQiyi / Tencent / Youku style long-form platforms: the extractor often cannot find the video
  at all (DRM), and the tool says so instead of guessing.

## License and attribution

MIT for this project. Third-party components, model licences and attribution are listed in
[NOTICE.md](NOTICE.md) (RapidOCR / PP-OCRv6, ONNX Runtime, sherpa-onnx, Whisper, SenseVoice,
CED-mini). The offline-OCR *approach* was inspired by
[Umi-OCR](https://github.com/hiroi-sora/Umi-OCR) (MIT); no code was copied.
