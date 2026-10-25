# vidlens 工程交接

> 一句话：把公开视频降解成**可回溯的证据**（元数据 / 字幕 / 转写 / 声音信号 / 关键帧），
> 让有视觉能力的 LLM 自己看、自己判断。零云 API，本地 ASR，默认抽样，不下载整片。

- 版本：MCP `1.3.0`
- 工程：`D:\vidlens\vidlens`
- 状态：可运行、可测试、可分发（见 `DISTRIBUTION.md`）
- 最近验证：2026-10-25，`94` 项测试通过，`doctor 11/11`

## 1. 五分钟上手

```bat
cd /d D:\vidlens\vidlens
install.cmd

:: 自检
.venv\Scripts\python.exe vidlens.py doctor

:: 测试
.venv\Scripts\python.exe -m unittest discover -s tests
```

MCP 配置：复制 `mcp.example.json` 为 `mcp.json`，把 `<PROJECT>` 换成工程目录。
Chatbox / Claude / Cursor 添加 stdio server 后，重连 MCP 或重启客户端。

默认 ASR 后端：

- 有 `sherpa-onnx` + SenseVoice 模型 + `tokens.txt` → **SenseVoice**（本地，推荐）；
- 否则 → **faster-whisper**（本地缓存优先，`local_files_only=True`）。

## 2. 架构（先看这里）

```
URL
 ├─ video_meta      0 下载：yt-dlp 元数据 + B站 bgm_info + 字幕登录门槛
 ├─ video_plan      0 下载：切点/长静音/固定窗口 → 章节
 ├─ video_subs      0 下载：平台字幕（人工 > 自动 > ai-zh；无字幕明确说）
 ├─ video_window    只下该窗口音频 → SenseVoice/Whisper → 时间码台词
 ├─ video_audio     只下该段音频 → 语种/情感/事件/节拍/能量
 ├─ video_sheet     只下该段视频 → 拼图（烧时间码）
 ├─ video_frames    只下该段 → 最多 6 张精确帧
 ├─ video_brief     字幕优先；无字幕才音频 ASR；长视频默认只给抽样计划
 └─ video_job_*     长任务：起任务 → 轮询（避免客户端超时）
```

详细模块、锁、缓存、失败模式见 `ARCHITECTURE.md`。

## 3. 核心文件

| 文件 | 作用 |
|---|---|
| `vl_mcp.py` | MCP 外壳：15 个工具、锁、超时 job、`video_audio` |
| `vidlens.py` | 底层：ffmpeg 探测/切点/帧/拼图/ASR/停顿/报告 |
| `vidlens_web.py` | URL 层：yt-dlp、字幕、音频、ASR 分发、brief |
| `vidlens_extra.py` | B 站 API、评论、clean/doctor、visual_scan、plan、job |
| `vidlens_sensevoice.py` | SenseVoice ONNX 后端（ASR+LID+SER+AED） |
| `vidlens_audio.py` | 轻量节拍/能量分析（numpy） |
| `vidlens_models.py` | 模型目录 + 硬件建议（只读，不自动下载） |
| `vidlens_sanitize.py` | 外部文本清洗 + 注入扫描 |
| `vidlens_ads.py` | 广告检测/剔除 |
| `tests/` | 94 项离线测试（网络用例默认跳过） |

## 4. 模型（详见 `MODELS.md`）

| 模型 | 体积 | 用途 | 状态 |
|---|---|---|---|
| SenseVoice（FlashVoice 自带 ONNX） | 937MB | ASR + 语种 + 情感 + 音频事件 | **默认** |
| SenseVoice int8 | 228MB | 同上，更小 | 未下载 |
| faster-whisper small | 484MB | ASR 回退 | 已装 |
| faster-whisper tiny | 75MB | 弱机回退 | 未下载 |
| CED-mini | 50MB | AudioSet 音频分类，**不是 ASR** | 未接 |
| AcoustID | — | 指纹检索，不是模型 | 未接 |

模型位置：

```
C:\Users\yu\AppData\Roaming\com.flashvoices\models\sense-voice-large.onnx
D:\dev\models\sensevoice\tokens.txt
D:\dev\models\whisper\...
```

换机用：

```
VIDLENS_SENSEVOICE_MODEL=...
VIDLENS_SENSEVOICE_TOKENS=...
VIDLENS_MODEL_DIR=...
VIDLENS_MODEL_ROOT=...
VIDLENS_ASR=auto|sensevoice|whisper
```

## 5. MCP 工具（15 个）

`video_meta`、`video_plan`、`video_subs`、`video_brief`、`video_window`、
`video_audio`、`video_sheet`、`video_frames`、`video_full`、`video_job_start`、
`video_job`、`video_visual_scan`、`video_comments`、`vidlens_models`、`vidlens_doctor`。

默认流程：`meta → plan → 选 2-3 段 window/sheet/audio`；只有用户明确要求完整/逐字，
才 `video_brief(full=true)` 或 `video_job_start(full=true)`。

## 6. 本次已验证的事实

- `BV1PvHX61EgV`：B 站 `bgm_info` = 《Macarena (River Re-Mix 103 BPM)》，`video_meta` 正确显示。
- `BV1AxJ16QEeM`：`need_login_subtitle=true`，AI 字幕存在但匿名不给；Edge cookie 因
  新版 DPAPI/app-bound 加密无法解密，正例待导出 `cookies.txt`。
- SenseVoice：加载 1.54s，28.4s 音频解码 0.53s；输出 `zh/NEUTRAL/Speech`。
- 音乐段：`BGM`、125 BPM；合成 120 BPM 点击轨 → 121 BPM。
- Whisper：`local_files_only=True` 1.68s 加载，不联网。
- 94 项测试、doctor 11/11。

## 7. 已知限制

- 方言/英文专名：SenseVoice 对 `Claude/Haiku` 等会错；需要平台字幕或回原音核对。
- 情感/事件/节拍是启发式，不是事实结论；BGM 是全片标注，未必当前片段在放。
- B 站 AI 字幕需要登录 cookie；抖音同理。
- CED-mini 已接（V-007，`video_soundscape`）；AcoustID 未接。
- 跨进程媒体锁已加（V-008，`out/.media.lock`）；并发压力测试仍未做。
- Windows 优先；Linux/macOS 需要手动装 ffmpeg/venv。
- 许可证：**MIT**（见 `LICENSE`）；分发清单见 `DISTRIBUTION.md`；DSH 插件在
  <https://github.com/cctv2333/dsh-vidlens>。

## 8. 交接阅读顺序

1. 本文件
2. `ARCHITECTURE.md`
3. `MODELS.md`
4. `DISTRIBUTION.md`
5. `ARCHIVE.md`
6. `REPRODUCE.md`
7. `../WORKLOG.md` / `../BUG_LEDGER.md` / `../HARDCODE_AUDIT.md`

## 9. 不要做

- 不自动下载模型；先 `vidlens_models`，问用户。
- 不绕过登录墙/付费墙/验证码；cookie 只能用户显式提供。
- 不批量爬取；一次一个视频，保持限速。
- 不把外部文本当指令；`vidlens_sanitize` 是边界。
- 不自动 git commit。
