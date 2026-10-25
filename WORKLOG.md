# WORKLOG — vidlens

> 索引：只读本区 + 最近 ≤10 条 + 相关条目（grep）。更早条目按 `WORKLOG-archive-YYYYMM.md` 归档。

## 索引

| # | 日期 | 标题 | 状态 | 归档 |
|---|---|---|---|---|
| V-008 | 2026-10-25 | PyPI 打包 + 跨进程媒体锁 + 两仓库拆分（vidlens / dsh-vidlens） | 已完成 | — |
| V-007 | 2026-10-25 | 声音事件接入（CED-mini + AudioSet 527）：video_soundscape + DSH 插件 | 已完成 | — |
| V-006 | 2026-10-25 | 工程交接与可分发包（handover/ + dist zip） | 已完成 | — |
| V-005 | 2026-10-25 | B站 AI字幕/平台 BGM 元数据、模型目录与 CED-mini/AcoustID 调研 | 已完成 | — |
| V-004 | 2026-10-25 | 本地 ASR 复用：SenseVoice/Whisper 模型不重复联网 + 情感/事件调研 | 已完成 | — |
| V-003 | 2026-10-25 | 硬编码/魔法数字审计与字幕/抽样能力验收 | 已完成 | — |
| V-002 | 2026-10-25 | 审计 P1/P2 修复：字幕优先、cookie、锁、注入扫描、缓存与边界 | 已完成 | — |
| V-001 | 2026-10-25 | plan() / pauses.json 双形态崩溃修复 | 已完成 | — |

---

## 2026-10-25 PyPI 打包 + 跨进程锁 + 两仓库拆分（V-008）

- **目标**：① 让 MCP 能 `pipx install` 而不是 clone；② 修掉多进程争 `out/` 的并发 bug；
  ③ 按「工程 / DSH 插件」拆两个公开仓库。
- **改动**：
  - `pyproject.toml`（setuptools，flat `py-modules` 10 个）；入口
    `vidlens = vidlens:main`、`vidlens-mcp = vl_mcp:main`；extras
    `sensevoice` / `whisper` / `audioevents` / `all`。
  - `vidlens.project_root()`：源码布局保持工程目录；wheel 安装后用
    `%LOCALAPPDATA%\vidlens`（POSIX `~/.local/share/vidlens`）。`out_root()` /
    `ffmpeg_dir()` 都改走它 —— 装成 wheel 不再往 site-packages 写数据。
  - `vidlens_web.CrossProcessLock` + `media_lock()`：进程内 RLock + 一个机器级文件锁
    （`out/.media.lock`，Windows `msvcrt` / POSIX `flock`，超时 `VIDLENS_LOCK_TIMEOUT`）。
    `vl_mcp._MEDIA_LOCK` 换成它；`video_comments` 补上媒体锁。
  - `tests/test_lock.py`（3 项）+ `tests/test_audioevents.py`（7 项）。
  - README 安装段改为「PyPI 优先，源码次之」；LICENSE 相关表述统一为 MIT。
  - 仓库拆分：`cctv2333/vidlens`（本仓库，Python + MCP）与
    `cctv2333/dsh-vidlens`（DSH 插件，18 工具）。
- **验证**：
  - `uv build --wheel` 成功，wheel 含 10 个模块 + `LICENSE`/`NOTICE.md` + 两个 console script；
  - 装到临时 target 后从空目录导入：`project_root = C:\Users\yu\AppData\Local\vidlens`，
    `out_root` / `ffmpeg_dir` 都落在用户目录，16 个 MCP 工具可加载；
  - 锁：3 项单测通过；两进程真实 `video_sheet` 实测串行（proc1 acq 4.66s→end 17.76s，
    proc0 acq 17.95s→end 30.47s）；
  - 全量 `Ran 104 tests ... OK (skipped=1)`。
- **状态**：已完成

---

## 2026-10-25 声音事件接入（V-007）

- **目标**：识别台词之外的声音——吃饭/咀嚼、敲桌子、水声、碰撞、拖拽；带时间码与概率。
- **事实（先查后做）**：
  - 本机 `sherpa_onnx 2.0.0` 自带 `AudioTagging`，且 `AudioTaggingModelConfig(ced=...)`
    可用（`ced` 是真字段，只是不在 `dir()` 里列出）；
  - 模型 `k2-fsa/sherpa-onnx-ced-mini-audio-tagging-2024-04-19`：
    `model.int8.onnx` 10,451,715B + `class_labels_indices.csv` 14,675B（Apache-2.0）；
  - AudioSet 527 类里**有** `Chewing, mastication`(#54)、`Knock`(#359)、`Tap`(#360)、
    `Wood block`(#173)、`Water`(#288)、`Water tap`(#370)、`Chink, clink`(#442)、
    `Scrape`(#475)、`Crumpling, crinkling`(#479)；
    **没有** Drinking/Sip/Gulp —— 喝水/吞咽只能靠水声 + 画面推断。
- **改动**：
  - 新增 `vidlens_audioevents.py`（懒加载、10s 窗/5s 跳、按 hop 合并成段、锁串行）；
  - `vl_mcp.py` 新增 `video_soundscape`（MCP 第 16 个工具）；
  - `vidlens_models.py` 的 ced-mini 行改为「已装/已接」，`available()` 走
    `VIDLENS_TAGGING_*` / `VIDLENS_MODEL_ROOT`；
  - `tests/test_mcp.py` 工具清单加 `video_soundscape`；新增 `tests/test_audioevents.py`（7 项）；
  - 插件侧（`D:\vidlens\vidlens-mcp-dsh`）：`vidlens_soundscape` 工具 + 桥分发 + 下载脚本；
  - 工程新增 `LICENSE`（MIT）。
- **验证**：
  - `Ran 101 tests ... OK (skipped=1)`；
  - 加载 0.14s；28.4s 音频推理 43ms；
  - 合成三下敲击 → `Wood block 0.18 / Drum 0.17 / Music 0.23`；
    水声噪声 → `Waterfall 0.17 / Stream 0.08`；静音 → `Silence 0.53`；
  - 真实视频 01:00–01:45 → `Music 0.89 / Speech 0.88 / Speech synthesizer 0.32`，与画面一致；
  - 插件端到端：`vidlens_soundscape` 返回逐窗 + 段 + 「怎么读」，105/105 自检通过。
- **限制**：概率整体偏低（AudioSet 多标签），>0.30 才当真；喝水/吞咽无类；
  声音事件暂未写进 `brief.md`（独立工具，按需调用）。
- **状态**：已完成

---

## 2026-10-25 工程交接与可分发包（V-006）

- **目标**：让下一位 AI/人不用重新摸索；评估并实际构建可分发包。
- **产出**：
  - `HANDOVER.md` + `handover/README.md`（入口）
  - `handover/ARCHITECTURE.md`（模块/数据流/锁/缓存/失败模式）
  - `handover/MODELS.md`（模型/非模型能力、体积、许可证、下载政策）
  - `handover/DISTRIBUTION.md`（分发清单、排除项、换机步骤）
  - `handover/ARCHIVE.md`（档案/验证/日志索引）
  - `handover/REPRODUCE.md`（复现命令）
  - `dist/vidlens-src-20261025.zip`（大小/HASH 见外部 `dist/SHA256SUMS.txt`，
    避免 zip 内自指）
- **验证**：zip 解压到临时目录后 `Ran 94 tests ... OK (skipped=1)`；
  包内无 `out/`、`.venv/`、`bin/`、`mcp.json`、模型权重、`__pycache__`。
- **状态**：已完成
- **分发限制**：仓库暂无 LICENSE（需项目所有者选；V-008 已定为 MIT）；模型权重不随包；
  Windows 优先；B 站 AI 字幕/抖音需要用户自己的 cookie。

---

## 2026-10-25 B站字幕/音乐元数据与模型目录（V-005）

- **目标**：测试用户给的 AI 字幕视频；接入平台 BGM 元数据；回答轻量模型/CED-mini/AcoustID。
- **事实**：
  - `BV1AxJ16QEeM` 的 `player/wbi/v2` 返回 `need_login_subtitle=true`、`login_mid=0`，
    匿名 `subtitles=[]`；AI 字幕存在，但需要登录态。
  - `BV1PvHX61EgV` 的 `bgm_info` 返回
    《Macarena (River Re-Mix 103 BPM)》+ music.bilibili.com 链接。
  - CED-mini：9,696,783 参数、usedStorage 49.7MB、Apache-2.0、AudioSet 音频分类，
    含 ONNX；**不是 ASR**。
  - AcoustID：Chromaprint 指纹检索，需 `fpcalc` + client API key，3 req/s、非商业；
    返回 MusicBrainz 记录，不是“听懂音乐”。
- **改动**：
  - `fetch_meta` 增加 B 站 `bgm_info` / `need_login_subtitle` / 简介音乐线索。
  - `video_meta` 显示平台音乐、音乐链接、字幕登录门槛。
  - `build_brief` 增加「音乐信息」章节；`video_audio` 带平台标注音乐。
  - 新增 `vidlens_models.py` + MCP `vidlens_models` + CLI `vl models`：
    模型目录/硬件建议，**只读、不自动下载**。
- **验证**：
  - `Ran 94 tests ... OK (skipped=1)`；`doctor 11/11`。
  - `video_meta(BV1PvHX61EgV)` 实测输出
    `平台音乐: Macarena (River Re-Mix 103 BPM)`。
  - `vl models --recommend`：`ram=14.9GB cpu=16cores recommended_asr=sensevoice`。
  - `video_audio(BV1PvHX61EgV 00:00-00:20)` 同时显示平台音乐 + `Speech` + 96.2 BPM。
- **状态**：已完成
- **待办**：AI 字幕正例需要登录 cookie；Edge 正在运行导致 cookie 库被锁，需用户关闭 Edge
  或导出 cookies.txt 后再测。CED-mini 未接（不是 ASR）；AcoustID 未接（需 fpcalc/key）。

---

## 2026-10-25 本地 ASR 复用与音频理解调研（V-004）

- **目标**：① 阻止每次新对话/新进程重复联网检查模型；② 评估并用上用户已有的
  `C:\Users\yu\AppData\Roaming\com.flashvoices\models\sense-voice-large.onnx`；
  ③ 调研音频情感/事件/节拍能力；④ 记录 B 站 AI 字幕限制。
- **事实**：Whisper small 权重 483.5MB 已在 `D:\dev\models\whisper`；新进程只是向
  HF 查版本（日志里的 GET），不是重下。SenseVoice 文件 937.6MB = 官方 float32
  `model.onnx`（894MiB），元数据 `sense_voice_ctc`、vocab 25055、`iic/SenseVoiceSmall`。
- **方案/改动**：
  - `vidlens_web.transcribe`：`VIDLENS_ASR=auto|sensevoice|whisper`；SenseVoice 优先，
    不可用回退 Whisper；Whisper 先 `local_files_only=True`，缓存缺失才联网。
  - 新增 `vidlens_sensevoice.py`：复用 FlashVoice 的 937MB ONNX + 308KB 词表，
    分块 ASR，返回 text/lang/emotion/event/timestamps。
  - 新增 `vidlens_audio.py`：numpy 频谱通量 + 自相关，估计 BPM/能量/动态/静音。
  - 新增 MCP `video_audio`：只听一段，返回语种/情感/事件/节拍/能量。
  - `build_brief` 增加「声音信号」章节；BGM 与语音并存时注明。
  - `DEFAULT_SUB_LANGS` 增加 `ai-zh,ai-en,ai-*`，覆盖 B 站 AI 字幕命名。
  - requirements 增加 `sherpa-onnx>=2.0.0,<3`。
- **验证**：
  - `Ran 91 tests ... OK (skipped=1)`。
  - SenseVoice：加载 1.54s，28.4s 音频解码 0.53s；输出 `zh/NEUTRAL/Speech`。
  - 音乐段 `video_audio`：`<|BGM|>`，125.0 BPM，20.4s。
  - 口播段 `video_audio`：`zh/NEUTRAL`，文本可用；对 Claude/Haiku 等英文专名仍会错。
  - 合成 120 BPM 点击轨 → 121.0 BPM；真实 BGM → 125 BPM。
  - Whisper `local_files_only=True`：加载 1.68s，不联网；`info.local_files_only=True`。
  - B 站匿名 `player/v2` 三个样本 `subtitle.subtitles=[]`；AI 字幕需登录 cookie。
- **状态**：已完成（研究 + 实装 + 实测）
- **限制**：SenseVoice 对英文品牌名/专名不如 Whisper；情感/事件/节拍是启发式，
  不当作事实；B 站 AI 字幕正例未拿到（无登录态）。

---

## 2026-10-25 硬编码审计与能力验收（V-003）

- **目标**：回答“有没有硬编码/魔法数字”；验证字幕、方言、默认抽样策略。
- **改动**：`HARDCODE_AUDIT.md`（AST 扫描 + 人工分类）；`vidlens_ads.py` 的 `毫光`→`毫克`；
  README 增补 cookie / 方言 / 默认抽样说明。
- **验证**：`Ran 90 tests ... OK (skipped=1)`；`doctor 11/11 ok`；
  真实 e2e：
  - 40 分钟无切点视频 → `video_plan` 8 个 5 分钟章节（修复了“整片 1 章”）；
  - 无缓存长视频 `video_brief` → 3.7s 返回抽样计划，out 目录 0 文件；
  - 无缓存 `video_window(02:00–02:20)` → 28.2s，只转写 20 秒，时间码 02:00 起，临时目录已清；
  - 有缓存 40 分钟视频 → `video_brief` 3.4s，含「分步看」，来源 `asr(cached)`；
  - `video_subs` 实际调用 yt-dlp，B 站匿名无 CC 时明确返回“没有可用字幕”。
- **状态**：已完成
- **限制**：B 站匿名通常只给 danmaku，不给 CC；正片字幕需 cookie/登录态，已提供 env 入口。

---

## 2026-10-25 审计 P1/P2 修复（V-002）

- **目标**：修掉审计报告里已核实的 P1/P2 问题；补字幕/方言能力；把“默认抽样、按需全量”写进工具行为与说明。
- **验收标准**：新增/修改行为有单测；全量测试绿；真实 MCP 握手与至少一条真实视频链路可用；`video_subs`/`video_plan` 可用；文档与行为一致。
- **排除项**：不部署本地大模型、不调云 API；不做爬虫/白名单；不改用户已有产物；不自动提交。
- **方案**：分批小步改，每批跑相关测试；先做字幕与默认抽样（主矛盾），再做锁/缓存/边界与魔法数字。
- **回退点**：每批改动前记录文件；若测试失败，回退该批。
- **改动**：
  - `vidlens_web.py`：`DEFAULT_SUB_LANGS`/`sub_langs_for`、cookie env + 报错提示、`media_duration`/音频完整性校验、`download_audio_section`、`subs/` 隔离目录、`plan_chapters` 长空洞兜底网格、展示上限常量。
  - `vl_mcp.py`：字幕优先 `_rows_with_media`、`video_subs`、`video_plan`、长视频默认抽样、`_MEDIA_LOCK`/`_JOB_LOCK`/同 URL job 去重、行级 `S.scan`、唯一临时目录、负时间夹紧、命名常量、删除 `quiet()` 死代码。
  - `vidlens_extra.py`：`plan(meta=)`、visual_scan 清理抽帧、命名常量。
  - `vidlens_ads.py`：`毫光` → `毫克`。
  - `requirements.txt`：`av>=11,<19`。
  - `tools/manual/`：归档 `_meta3.py`、`_run_three.ps1`。
  - `README.md`：13 个工具、字幕/方言、默认抽样、cookie、锁说明。
  - `tests/test_features.py`（18 项）+ `tests/test_plan.py`（10 项）。
- **验证**：`Ran 90 tests ... OK (skipped=1)`；`doctor 11/11 ok`；真实 MCP e2e 见 V-003。
- **状态**：已完成
- **待办**：无（P3 的可调阈值集中化见 `HARDCODE_AUDIT.md`，等用户明确再动）

---

## 2026-10-25 plan() / pauses.json 双形态崩溃修复（V-001）

- **目标**：修掉 `plan()` 在 CLI 形态 `{"threshold_db":...,"gaps":[...]}` 下抛 `AttributeError`，以及 `_do_brief` 静默吞异常。
- **验收标准**：两种 pauses.json 形态都能出章节；`_do_brief` 不再调用 `plan()`；真实 MCP job 可复现修复。
- **方案**：`vidlens_web.read_pauses()` 统一读取；`plan_chapters()` 抽出共用；`build_brief(chapters=)` 把「分步看」放在「结构」之后；同步/异步 brief 都补章节。
- **改动**：`vidlens_web.py`、`vidlens_extra.py`、`vl_mcp.py`、`tests/test_plan.py`、`README.md`。
- **验证**：`Ran 69 tests ... OK (skipped=1)`；真实 MCP job（临时字典形态缓存）输出 `HAS_PLAN_SECTION: True`、`HAS_ERROR: False`；证据 `out/plan_bug_evidence.md`。
- **状态**：已完成
- **回退点**：`out/plan_bug_evidence.md` 记录了改动点；缓存已恢复原样。
visual_scan 清理抽帧、命名常量。
  - `vidlens_ads.py`：`毫光` → `毫克`。
  - `requirements.txt`：`av>=11,<19`。
  - `tools/manual/`：归档 `_meta3.py`、`_run_three.ps1`。
  - `README.md`：13 个工具、字幕/方言、默认抽样、cookie、锁说明。
  - `tests/test_features.py`（18 项）+ `tests/test_plan.py`（10 项）。
- **验证**：`Ran 90 tests ... OK (skipped=1)`；`doctor 11/11 ok`；真实 MCP e2e 见 V-003。
- **状态**：已完成
- **待办**：无（P3 的可调阈值集中化见 `HARDCODE_AUDIT.md`，等用户明确再动）

---

## 2026-10-25 plan() / pauses.json 双形态崩溃修复（V-001）

- **目标**：修掉 `plan()` 在 CLI 形态 `{"threshold_db":...,"gaps":[...]}` 下抛 `AttributeError`，以及 `_do_brief` 静默吞异常。
- **验收标准**：两种 pauses.json 形态都能出章节；`_do_brief` 不再调用 `plan()`；真实 MCP job 可复现修复。
- **方案**：`vidlens_web.read_pauses()` 统一读取；`plan_chapters()` 抽出共用；`build_brief(chapters=)` 把「分步看」放在「结构」之后；同步/异步 brief 都补章节。
- **改动**：`vidlens_web.py`、`vidlens_extra.py`、`vl_mcp.py`、`tests/test_plan.py`、`README.md`。
- **验证**：`Ran 69 tests ... OK (skipped=1)`；真实 MCP job（临时字典形态缓存）输出 `HAS_PLAN_SECTION: True`、`HAS_ERROR: False`；证据 `out/plan_bug_evidence.md`。
- **状态**：已完成
- **回退点**：`out/plan_bug_evidence.md` 记录了改动点；缓存已恢复原样。
