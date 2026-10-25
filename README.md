# vidlens

[![ci](https://github.com/cctv2333/vidlens/actions/workflows/ci.yml/badge.svg)](https://github.com/cctv2333/vidlens/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/vidlens-mcp.svg)](https://pypi.org/project/vidlens-mcp/)
[![MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

把一个**公开可看**的视频，降解成「模型能真正读懂的证据表」。
零云 API、零视觉模型、零显卡依赖。核心原则：**只下最小必要字节**。

## 一分钟理解

我有眼睛（能看图片），但没有耳朵。所以我需要两样东西：
1. 声音 → 带时间戳的文字（这是唯一必须借工具的部分）
2. 任意时刻的画面 → 我自己看

工具只负责"取样 + 量化"，理解留在模型脑子里。

## 三级预算（实测数据，7 分钟 1080p 视频）

| 取法 | 体积 | 拿到什么 |
|---|---|---|
| 全片 1080p | 105.5 MB | 全部 |
| **只下音频** | **7.3 MB** | **100% 语言信息（139 段 / 2184 字，与 1080p 逐字一致）** |
| 只取 20 秒片段 | 0.9 MB | 那 20 秒的画面 |
| 平台字幕（若有） | 0 MB | 平台自带的字幕轨，连音频都不用下 |

**分辨率对语言信息零贡献。** 只有要读小字（代码、表格、UI 参数）时才需要原分辨率单帧。

## 安装

需要 Python 3.10+。两种装法：

**A. 从 PyPI（推荐给使用者，不用 clone）**

```bash
pipx install "vidlens-mcp[all]"      # 或 pip install "vidlens-mcp[all]"
vidlens doctor                        # CLI 自检
# MCP 配置只需要：{"command": "vidlens-mcp"}
```

产物与缓存在 `%LOCALAPPDATA%\vidlens\`（POSIX：`~/.local/share/vidlens/`），
可用 `VIDLENS_OUT` / `VIDLENS_BIN` 覆盖；模型仍然放在你自己的模型目录。

**B. 从源码（开发用）**

```bat
install.cmd
```

工程默认在 `D:\vidlens\vidlens`（可用环境变量覆盖）：
- 产物：`VIDLENS_OUT`，默认工程内 `out/`（源码布局）；装成 wheel 后默认 `%LOCALAPPDATA%\vidlens\out`
- 模型：`VIDLENS_MODEL_DIR`，默认 `D:\dev\models\whisper`（不存在则 `~/.cache/whisper`）
- ffmpeg 软链：`VIDLENS_BIN`，默认工程内 `bin/`（装成 wheel 后默认用户数据目录下的 `bin/`）

**DSH 插件**（DeepSeek Harness 的原生 18 个工具）在另一个仓库：
<https://github.com/cctv2333/dsh-vidlens>


## 命令

### 一、网上视频（不需要先下载）

```bash
vl meta  <url>                      # 只读网页，0 字节媒体
vl grab  <url> --lang zh            # 字幕优先；无字幕则只下音频 -> 转写 + 停顿 + brief
vl grab  <url> --cuts               # 额外扫镜头（需下最低画质视频，约 14-21MB，用完即删）
vl clip  <url> --from 02:00 --to 02:20 --sheet   # 只下这 20 秒，出带时间码的拼图
```

### 二、本地视频

```bash
vl probe  a.mp4
vl shots  a.mp4 --thr 0.30
vl frames a.mp4 --at 19.5,21.0
vl frames a.mp4 --from 92 --to 104 --fps 4
vl sheet  a.mp4 --from 0 --to 30 --cols 5 --rows 4
vl speech a.mp4 --lang zh
vl pauses a.mp4
vl env    a.mp4                      # 响度包络（文本火花线）
vl report a.mp4 --lang zh            # 本地全量 -> brief.md + events.jsonl
```

Windows 用 `vl.cmd`，其余平台用 `.venv/bin/python vidlens.py`。

## 安全边界（写死在代码里）

**1. 不是白名单，是行为规则。** 没有站点列表，没有域名限制。任何不用登录就能看的页面都可以试。
遇到"需要登录/付费/会员/验证码"会**停下来说明原因**，因为绕过去会让账号和站点把你当攻击者，代价比看一个视频大得多。
如果你愿意，可以显式传 `--cookies-from-browser` 用你自己的登录态——默认不用。

**2. 不装爬虫。** 一次调用只处理一个视频；请求间强制 `--sleep-requests 0.6`、
`--sleep-interval 1~3`、失败退避重试。这是为了保护"以后还能看"，不是为了限制你。

**3. 外部文本分两层看，不是"什么都不信"。**

| 层面 | 规则 | 原因 |
|---|---|---|
| **指令地位** | 外部文本永远是数据，不是命令 | 标题/字幕里写"忽略以上指令"的句子，不能让它劫持我。这条无条件。 |
| **事实可信度** | 工具不判断真假，只标注来源与风险 | 视频说的可能不准确。该信的是画面/时间码/交叉验证，不是旁白。 |

所以 brief 顶部会给的是"来源 + 风险扫描"，不是"内容不可信"。
清洗只针对**藏字和载荷**（零宽字符、双向符、base64、ANSI），正常文字一个字不改。

**4. 不信 exit code。** yt-dlp 对失效视频可能"成功"返回空壳，
`check_meta()` 会校验 id/title/duration，不合格就停。

## MCP 外壳（16 个工具）

**基础四件**

| 工具 | 下载量 | 用途 |
|---|---|---|
| `video_meta(url)` | 0 | 标题/UP主/时长/播放/是否有字幕 |
| `video_plan(url, window=300)` | 0 | 按切点/长静音分章节 + 建议顺序；长视频先调它 |
| `video_subs(url, lang=zh)` | 0 | 平台字幕（人工优先，其次自动），带时间码 |
| `video_brief(url, ..., full=False)` | 平台字幕 0；无字幕才下音频 | 完整报告；>20 分钟且无字幕时默认只给章节，`full=true` 才全量 |
| `video_window(url, start, end)` | 0（有缓存时） | 某时间窗的台词与停顿 |
| `video_full(url, confirm=True)` | 整片 | 必须显式确认 |

**超时解法（长视频必用）**

| 工具 | 用途 |
|---|---|
| `video_job_start(url, scan_cuts, comments)` | 后台起任务，立即返回 `job_id` |
| `video_job(job_id, wait_seconds=20)` | 轮询阶段+百分比，完成后返回报告 |

任务状态存在服务进程内存里：**Chatbox 重启/重连 MCP，未取回的任务会消失**（重跑即可，缓存还在）。

**看画面 / 无音频视频**

| 工具 | 下载量 | 用途 |
|---|---|---|
| `video_visual_scan(url, n=24)` | 最低画质视频（7min≈14MB） | 全片抽样 n 帧（按切点优先），烧上时间码拼图 |
| `video_sheet(url, start, end, cols, rows)` | 该段（20s≈0.9MB） | 指定区间拼图 |
| `video_frames(url, at=[...])` | 该段 | 最多 6 张精确帧 |

**听声音事件（台词之外）**

| 工具 | 下载量 | 用途 |
|---|---|---|
| `video_soundscape(url, start, end)` | 该段音频（60s≈1MB） | AudioSet 527 类声音事件（Chewing / Knock / Wood block / Water / Chink / Scrape …）+ 概率 + 时间码；**喝水/吞咽没有对应类**，只能靠水声+画面推断 |

**判断内容性质**

| 工具 | 下载量 | 用途 |
|---|---|---|
| `video_comments(url, limit=40)` | 0 | 评论互动比、正/负面词频、争议度启发式 |
| `vidlens_models(action=list)` | 0 | 本地模型目录 + 硬件建议；**只读，不自动下载** |
| `vidlens_doctor()` | 0 | 自检：python/ffmpeg/yt-dlp/依赖/模型/磁盘/网络 |

Chatbox / Claude / Cursor 里加 stdio server 的三项：

```
command : D:\vidlens\vidlens\.venv\Scripts\python.exe
args    : D:\vidlens\vidlens\vl_mcp.py
env     : PYTHONIOENCODING=utf-8 ; HF_HUB_DISABLE_XET=1
```

通用 JSON 见 `mcp.example.json`（`<PROJECT>` 换成工程目录）；本机 `mcp.json` 是实际路径。
**注意：MCP 走 stdio，服务进程绝对不能 print**；
库函数用 `verbose=False`，下载/ASR 用 `_MEDIA_LOCK` 串行。禁止用
`contextlib.redirect_stdout` 长时间劫持 `sys.stdout`，那会吞掉协议响应。

**需要 cookie 的站点**（抖音等）默认不碰；用户可显式开启：

```
VIDLENS_COOKIES=D:\path\cookies.txt
# 或
VIDLENS_COOKIES_FROM_BROWSER=chrome   # edge / firefox / chromium
```

## 命令行新增命令

```bash
vl clean --days 7 --dry-run      # 清理旧缓存（默认只删媒体，保留 brief.md）
vl clean --days 7                # 真删
vl clean --days 30 --all         # 整个目录删
vl doctor                        # 自检 11 项
vl comments <url>                # 评论区信号 -> out/<id>/comments.md
vl scan <url> --n 24             # 全片抽样帧拼图（无音频视频用）
vl plan <url> --window 300       # 长视频分步建议
vl models                        # 本地模型目录（只读，不下载）
vl models --recommend            # 按内存/CPU/磁盘给建议
```

## 无音频 / 长静音视频怎么办

1. `video_brief` 会先算**语音覆盖率**；低于 15% 直接提醒"信息在画面里"
2. 用 `video_visual_scan` 全片抽样（有切点按切点取，没有就均匀取），一次返回多张带时间码的图
3. 发现可疑段落，再用 `video_sheet` 或 `video_frames` 局部放大

## 长视频怎么办：默认抽样，按需全量

人类看长视频会加速/跳过，工具也按这个顺序：

1. `video_meta` → 值不值得看
2. `video_plan` → 0 下载拿章节
3. 挑 2-3 段：`video_window` 读台词、`video_sheet` 看画面
4. 只有用户明确要「完整/逐字/全片」时：`video_brief(full=true)`，超过 60 秒用
   `video_job_start(full=true)` → `video_job` 轮询

超过 20 分钟、且没有平台字幕的视频，`video_brief` 默认**只返回章节建议**，
不会偷偷下完整音频。平台字幕优先（`video_subs`，0 下载）；没有字幕才走本地 ASR。
`video_job(comments=True)` 会顺带附上评论区分析。

## 本地 ASR：SenseVoice（推荐）/ Whisper

默认 `VIDLENS_ASR=auto`：只要 `sherpa-onnx`、SenseVoice 模型和词表都在，就用 SenseVoice；
否则自动回退 faster-whisper。**不会重复下模型**。

- 用户已有模型（FlashVoice 自带）：
  `C:\Users\yu\AppData\Roaming\com.flashvoices\models\sense-voice-large.onnx`
  （937MB，等于官方 float32 `model.onnx`，元数据 `iic/SenseVoiceSmall`）
- 词表：`D:\dev\models\sensevoice\tokens.txt`（308KB，一次下载，25,055 行）
- 覆盖路径：
  ```
  VIDLENS_SENSEVOICE_MODEL=D:\path\sense-voice.onnx
  VIDLENS_SENSEVOICE_TOKENS=D:\path\tokens.txt
  ```
- 实测（本机 CPU）：加载 1.5s；28.4s 音频解码 0.53s；20s 音乐段解码 0.35s。
- 一次输出：`text`、`lang`（zh/en/yue/ja/ko）、`emotion`（NEUTRAL/HAPPY/SAD/…）、
  `event`（Speech/BGM/Laughter/Applause/Cry/…）、`timestamps`。
- `video_audio` 用这些标签 + 一个轻量节拍估计（合成 120 BPM 实测 121.0；真实 BGM 约 125）。
- 强制旧后端：`VIDLENS_ASR=whisper`。Whisper 加载时先试 `local_files_only=True`，
  缓存命中就不联网（实测 1.68s 加载）；只有缓存缺失才下载。
- **注意**：新对话会启动新的 MCP 进程，模型需要重新加载进内存（SenseVoice 约 1.5s），
  但不会重新下载权重。模型加载 ≠ 下载。

## 音乐信息（优先看平台元数据）

- **B 站**：`player/wbi/v2` 的 `bgm_info` 直接给 `music_title` 和音乐链接。
  `video_meta` 会显示「平台音乐」，`video_brief` 有「音乐信息」章节，
  `video_audio` 也会带上。
- **其他站**：扫描标题/简介里的 `BGM：`、`配乐：`、`音乐：`、`歌曲：`、`《…》`
  等线索；这是零下载的文本信息，不是听音识曲。
- **注意**：平台标注是**全片**信息，未必当前片段在放；也可能缺失/写错。
- 实测 BV1PvHX61EgV：`bgm_info` = 《Macarena (River Re-Mix 103 BPM)》，
  `video_meta` 已正确显示。

## 模型目录 / CED-mini / AcoustID

`vidlens_models`（或 `vl models`）只读列出本机模型、体积、用途和硬件建议；
**不会自动下载**，下载前先问用户。

- **CED-mini**（已接入，V-007）：sherpa-onnx 的 `AudioTagging` + `k2-fsa` int8 模型
  （10.4MB）+ `class_labels_indices.csv`（14.7KB），AudioSet 527 类声音事件分类，
  **不是 ASR**。入口：`video_soundscape` / `vidlens_soundscape`。
  能识别吃饭/咀嚼（Chewing, mastication）、敲/拍（Knock / Tap / Wood block / Thump）、
  水声（Water / Water tap）、杯子碰撞（Chink, clink）、拖拽（Scrape）、塑料袋
  （Crumpling, crinkling）、掌声/笑声等。**喝水/吞咽没有对应 AudioSet 类**，只能靠
  水声 + 画面推断；要准需 CLAP 零样本或自训小分类器。
  实测：加载 0.14s、28s 音频推理 43ms。下载：`tools/fetch_sound_model.py`（插件仓库内），
  或 `VIDLENS_TAGGING_MODEL` / `VIDLENS_TAGGING_LABELS` 指向已有文件；**不自动下载**。
- **AcoustID**：音频指纹检索，不是 AI 模型。需要 Chromaprint `fpcalc` + 客户端
  API key，官方限 3 请求/秒、仅非商业；返回 MusicBrainz 记录，不保证歌名。
  优先级低于平台元数据：B 站 `player/wbi/v2` 的 `bgm_info` 直接给歌名和链接，
  已接入 `video_meta` / `video_brief` / `video_audio`。
- 平台元数据也可能缺失/写错；需要时再用听音识曲交叉核对。

## 方言 / 口音 / 字幕

- **人工字幕**：UP 主上传的字幕最可靠，直接 `video_subs` 或 `video_brief`（0 下载）。
- **自动字幕**：平台 ASR 生成的，免下载但可能错；仍比没有强。
- **B 站 AI 字幕**：`video_meta` 的 `has_auto_subs` 会显示 `ai-zh` 等；
  但匿名 `player/v2` 多数返回空，通常需要登录态。设置
  `VIDLENS_COOKIES_FROM_BROWSER=edge`（或 chrome/firefox）后再试。
  字幕匹配已包含 `ai-zh,ai-en,ai-.*`。
- **无字幕**：SenseVoice 优先；`lang` 传 `yue`（粤语）等可改善；重口音仍可能错。
  要旧 Whisper 加方言提示词：`VIDLENS_ASR=whisper` + `prompt=...`。
- **画面硬字幕**：用 `video_sheet` / `video_frames` 取帧，AI 自己看字。
- 低置信词会列在 brief 的「低置信词」章节，必须回画面/原音核对。
## 产物结构

```
out/<视频id>/
  meta.json          元数据 + 风险扫描结果
  transcript.jsonl   词级时间戳 + 每词置信度
  transcript.srt     字幕
  pauses.json        话中停顿
  brief.md           来源/风险扫描 / 结构 / 停顿语境 / 低置信词 / 下一步看哪里
  clip_<a>_<b>/      按需片段与拼图（媒体文件默认删除）
```

## 广告自动跳过

赞助口播、带货、优惠码——**零价值，不进摘要**。

- `vidlens_ads.py` 按“赞助/优惠/下单/链接/积分/保温杯…”等词加权，按**时间间隔**聚类成段，
  再要求“时长够长 + 命中密度够高”才判定（不靠单个关键词就下手）
- brief 里单独列出「广告段落（已跳过）」及时间码，**转写正文直接剔除**
- 原始文字仍保留在 `transcript.jsonl`（可追溯），只是不进摘要
- 实测：某 40 分钟视频命中 `20:02.780 → 21:39.060`（96 秒，占 4%）；无广告视频 0 命中
- 阈值可调：`vidlens_ads.detect(rows, min_score=, min_dur=, density=, join_sec=)`，
  误判可直接看 brief 里的段落推翻

## 交接与分发

- 交接入口：`HANDOVER.md` → `handover/README.md`
- 架构/模型/分发/归档/复现：`handover/ARCHITECTURE.md`、`MODELS.md`、
  `DISTRIBUTION.md`、`ARCHIVE.md`、`REPRODUCE.md`
- 可分发包：`dist/vidlens-src-YYYYMMDD.zip`（不含模型、`out/`、`.venv/`、`bin/`、
  `mcp.json`）。本次包解压后 94 项测试通过。
- 许可证：**MIT**（见 `LICENSE`）；模型权重不随仓库/分发包分发。

## 测试（104 项，默认不依赖网络）

```bash
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`core` 9 + `web` 23 + `extra` 12 + `ads` 9 + `mcp` 7（含真实 stdio 握手）+
`plan` 10 + `features` 24（字幕/抽样/cookie/缓存/边界/声音工具/模型目录）+
`audioevents` 7（声音事件，模型缺失时自动跳过）+ `lock` 3（跨进程锁）。
网络相关用例用 `VIDLENS_NET_TESTS=1` 打开。

覆盖：探测、切点、抽帧命名、拼图偏移（历史 bug 回归）、静音检测、时间码解析、
SRT 生成、模型目录、零宽字符清洗、中英文注入检测、shell/外泄检测、
滚动字幕去重、VTT 解析、片段参数边界、登录墙识别、空壳元数据拒绝、
AudioSet 窗口切分与时间码不漂移、跨进程文件锁。

## 发布（维护者）

- CI：`.github/workflows/ci.yml`（ubuntu + windows × python 3.10/3.12，离线测试 +
  wheel 构建 + 「安装形态写用户数据目录」检查）。
- 发版：打 tag 即发布。

```bash
git tag v1.4.0 && git push origin v1.4.0
```

`release.yml` 构建 sdist + wheel、上传 PyPI（需要仓库 secret `PYPI_API_TOKEN`；
也可改用 PyPI Trusted Publishing）、并附到 GitHub Release。

## 已知坑（都是实测踩过的）

1. **`av` 版本**：faster-whisper 1.2.1 用 `av.open(metadata_errors=...)`，av 19 已删该参数。
   本工具绕开 PyAV，用 ffmpeg 自解码 16k 波形喂模型。
2. **`HF_HUB_DISABLE_XET=1` 必须设**，否则 hf-mirror 走 Xet 会 401。
3. **`--download-sections` 要求可执行文件名就是 `ffmpeg`**，而 imageio 给的是
   `ffmpeg-win-x86_64-v7.1.exe` → 用 `ffmpeg_dir()` 建一个软链接/副本。
4. **`-ss` 会让 pts 归零**，拼图时间码会全错 → 必须 `setpts=PTS+offset/TB`。
5. **静音段分两种**：话中犹豫，和片尾无词。混在一起会给出 8 条一样的"犹豫"结论。
6. **PowerShell 读无 BOM 脚本，中文全烂；`.cmd` 必须 CRLF；中文别走命令行参数。**

## 许可证与归属

本项目以 **MIT** 许可证发布，见 [`LICENSE`](LICENSE)。本项目未复制任何外部代码，
只借鉴设计思路，已逐项在 `NOTICE.md` 登记。
运行时依赖：yt-dlp（Unlicense）、faster-whisper（MIT）、imageio-ffmpeg（BSD-2）、
sherpa-onnx（Apache-2.0）、ffmpeg 二进制（LGPL/GPL，以子进程方式调用，不链接）。
模型权重（SenseVoice / Whisper / CED-mini）不随仓库分发，各自遵循上游许可。
