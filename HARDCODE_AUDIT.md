# 硬编码 / 魔法数字审计

日期：2026-10-25　对象：`D:\vidlens\vidlens`　方法：Python AST 扫描所有模块 + 人工分类。

## 一、结论

- **没有影响正确性的“硬编码路径”**：模型目录、输出目录、ffmpeg 目录都可用环境变量覆盖；
  代码里的 `D:\dev\models\whisper` 只是本机兜底，找不到会退到 `~/.cache/whisper`。
- **行为阈值大多是领域常量**（采样率、时间换算、ffmpeg 参数），不应为了“消灭数字”而抽象。
- **真正该命名的限制已收敛**：brief 截断、音频上限、缓存下限、切点阈值、扫描高度、
  章节窗口、轮询上限、图片数量等，已改成模块顶部常量。
- 仍有一部分阈值散落在函数里（广告判定、评论争议度、静音阈值、低置信度），
  它们是**可调策略**，已有函数参数或 CLI 参数；本轮不强行抽成全局配置，避免过度设计。

## 二、已命名常量

### `vl_mcp.py`

| 常量 | 值 | 作用 |
|---|---|---|
| `MAX_IMAGES` | 6 | 单次取帧上限 |
| `MAX_BRIEF_CHARS` | 9000 | MCP 返回 brief 的截断 |
| `MAX_AUDIO_MB` | 200 | 单条音频下载上限 |
| `CUT_THRESHOLD` | 0.25 | 镜头切点阈值 |
| `SCAN_HEIGHT` / `FRAME_SCAN_HEIGHT` | 360 / 480 | 扫切点 / 取帧的下载高度 |
| `SHEET_WIDTH` / `SHEET_FONT_SIZE` | 480 / 20 | 拼图宽度 / 时间码字号 |
| `DEFAULT_CHAPTER_WINDOW` | 300s | 章节窗口 |
| `MAX_POLL_WAIT` | 60s | job 轮询上限 |
| `LONG_VIDEO_SECONDS` | 1200s | 超过则默认只给抽样计划 |
| `MAX_SUB_LINES` | 500 | 字幕返回上限 |
| `FRAME_PAD_SECONDS` | 2s | 取帧窗口前后留白 |
| `MAX_SHEET_COLS` / `MAX_SHEET_ROWS` | 8 / 6 | 拼图网格上限 |
| `MAX_CHAPTERS_SHOWN` / `MAX_PLAN_CHAPTERS` | 12 / 20 | brief / plan 展示上限 |
| `MIN_CHAPTER_WINDOW` / `MAX_CHAPTER_WINDOW` | 60 / 3600s | `video_plan` 入参夹紧 |
| `BYTES_PER_MB` | 1048576 | 体积换算 |

### `vidlens_web.py`

`DEFAULT_SUB_LANGS`、`MIN_AUDIO_BYTES`、`MAX_AUDIO_MB`、`BYTES_PER_MB`、
`DEFAULT_CHAPTER_WINDOW`、`MAX_BRIEF_CHAPTERS`、`MAX_LOW_WORDS`、
`MAX_TRANSCRIPT_LINES`。

### `vidlens_extra.py`

`VISUAL_MIN_FRAMES`（4）、`VISUAL_MAX_FRAMES`（48）、`VISUAL_CUT_THRESHOLD`（0.25）。

## 三、刻意保留的领域常量（不算 bug）

| 位置 | 值 | 理由 |
|---|---|---|
| `vidlens.py` | 8000 / 16000 / 32768 | 8k 波形、16k whisper 输入、int16 满量程 |
| `vidlens.py` | 3600 / 60 / 1000 | 时间换算 |
| `vidlens.py` | 350ms | VAD 最小静音；已有 `--min-dur` 等 CLI 参数 |
| `vidlens_web.py` | `-32dB` / 0.45s | 静音检测默认值；`--dbfs` / `--min-dur` 可覆盖 |
| `vidlens_web.py` | `p < 0.62` | 低置信词阈值；报告会标“需回原音核对” |
| `vidlens_ads.py` | 6 / 15 / 2 / 25 | 广告判定的分数、时长、密度、合并间隔；函数参数可覆盖 |
| `vidlens_extra.py` | B 站 API URL、UA | 站点协议常量，改一处即可 |
| `vidlens_sanitize.py` | 180 / 4000 / 20000 | 证据截断、清洗上限、扫描上限，安全边界 |

## 四、硬编码路径 / 环境相关

| 位置 | 内容 | 处理 |
|---|---|---|
| `vidlens.py:60` | `D:\dev\models\whisper` | `VIDLENS_MODEL_DIR` 优先；不存在退 `~/.cache/whisper`。本机兜底，保留 |
| `vidlens.py:264` | `C:\Windows\Fonts\...` | 跨平台字体候选，找不到会跳过 |
| `mcp.json` | `D:\vidlens\vidlens\...` | 本机 MCP 配置；`mcp.example.json` 是 `<PROJECT>` 占位版，换机复制改路径 |
| `README.md` | 同上 | 文档示例，不是运行时代码 |
| `tools/manual/` | 一次性调试脚本 | 已从根目录移走，避免误用 |

## 四点五、SenseVoice / 节拍模块

| 位置 | 值 | 说明 |
|---|---|---|
| `vidlens_sensevoice.py` | FlashVoice 模型路径 | 默认指向本机已有 937MB 模型；`VIDLENS_SENSEVOICE_MODEL` 可覆盖 |
| `vidlens_sensevoice.py` | `D:\dev\models\sensevoice\tokens.txt` | 308KB 词表；`VIDLENS_SENSEVOICE_TOKENS` 可覆盖 |
| `vidlens_sensevoice.py` | `CHUNK_SECONDS=20` | 长音频分块；不重叠，避免边界重复 |
| `vidlens_sensevoice.py` | `LANGS` | SenseVoice 支持的 auto/zh/en/ja/ko/yue |
| `vidlens_audio.py` | 1024 / 256 | FFT 帧长 / 帧移；16k 下约 62.5 帧/秒 |
| `vidlens_audio.py` | 40–200 BPM / 110 先验 | 节拍搜索范围与先验；只做近似估计 |
| `vidlens_audio.py` | 120s | 单次节拍分析最长音频，避免长视频爆内存 |
| `vidlens_web.py` | `local_files_only=True` | Whisper 缓存命中时不联网；失败才回退下载 |

> SenseVoice 权重不复制、不重复下载；换机只需把两个 env 指向已有模型/词表。
> `sherpa-onnx` 是 18.8MB 的本地推理包，已写入 requirements。

## 四点六、模型目录 / 音乐元数据

| 位置 | 值 | 说明 |
|---|---|---|
| `vidlens_models.py` | `D:\dev\models` / `D:\dev\models\whisper` | `VIDLENS_MODEL_ROOT` / `VIDLENS_MODEL_DIR` 可覆盖 |
| `vidlens_models.py` | 4GB / 8GB RAM 阈值 | 推荐 whisper-tiny / sensevoice-int8 / sensevoice |
| `vidlens_models.py` | 各模型 size_mb | 目录展示用；不是下载逻辑 |
| `vidlens_web.py` | `MUSIC_HINT_RE` | 只匹配 `BGM/配乐/音乐/歌曲...` 后的文本，避免标题误报 |
| `vidlens_extra.py` | `x/player/wbi/v2` | B 站平台 BGM/字幕登录门槛；元数据请求，0 媒体 |
| `vidlens_models.py` | `ced-mini` 50MB | 仅登记，未接入；AudioSet 分类不是 ASR |

## 五、建议但未做

1. 把广告/评论/低置信度阈值集中到 `config.json`（需要用户明确要可调再动）。
2. 把 `mcp.json` 拆成 `mcp.example.json`（占位路径）+ 本机 `mcp.json`；当前用户已在用，先不动。
3. 为 `download_audio` 的 2%/5s 容差加 CLI 参数；目前按经验值固定，已足够。

> 结论：**不存在“换个电脑就跑不起来”的硬编码**；存在少量可调阈值，
> 已把影响面大的命名化，其余保持领域常量并在本文件登记。
