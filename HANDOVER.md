# 工程交接入口

## 当前状态（2026-10-28，V-021）

新接手先看这六件事：

1. **两个仓库**：`cctv2333/vidlens`（Python + MCP，PyPI `vidlens-mcp` **1.7.1**）、
   `cctv2333/dsh-vidlens`（DSH 插件，npm `dsh-vidlens` **1.4.3**）。插件通过常驻桥
   `bridge/vidlens_bridge.py` 复用 `vl_mcp` 的函数，不存在第二份实现。
   **插件不含 Python 核心**：它 `import vidlens`，拿不到就回一句 pip 命令
   （`_import_error_text`），所以插件用户装核心走 PyPI，不走 GitHub。
2. **上下文预算已就位**：`brief` 默认 digest；`watch` 分段；插件侧 per-Agent 台账
   （12k 提示 / 24k 硬钳）；相同参数调用不重跑；大图不再 base64 内联。见 B-050…B-062。
3. **两条"没有文本"的出路都已接上**：
   - `video_ocr`（`pip install "vidlens-mcp[ocr]"`，RapidOCR / Apache-2.0 / 模型随包 / 离线）
     —— 实测 12 帧 46s、≈1.3k tokens 拿到 16 条带时间码字幕；三个测试视频里 2 个没人声，
     这条链路是它们的唯一入口。见 B-063、V-012。
   - `vidlens_models(action="download", name=..., confirm=true)` —— 音频侧同一条规则：
     先报大小与落点、确认才下；whisper 不再静默拉 484MB（B-066）。实测 ced-mini
     10.0MB / 52.3s，下完 `available()` 立刻认出来。见 V-014。
4. **本地文件是一等输入（1.6.0 / B-068）**：`url` 参数同时接受 `D:\a.mp4`、`file:///D:/a.mp4`、`~/a.mov`。
   判定只在 `vidlens_web.local_path()` 一处，五处短路（meta 用 ffmpeg banner、subs 返空落回 ASR、
   audio 抽 16k 单声道、video_lowest 直接回源文件、section 重编码切片）。
   **本地模式下 `download_video_lowest` 返回的是用户自己的文件**，所以凡是删临时文件的地方都走
   `_drop_temp(p, url)`——不要直接 `unlink`。
5. **路径规则统一，发布物里没有开发机路径**：`vidlens.models_root()` =
   env → legacy 目录（**仅当存在**）→ 用户数据目录。whisper / audio-tagging / SenseVoice
   三处共用；`NoPersonalPathsTests` 与插件自检各有一条护栏。见 B-065、V-013。
6. **验证入口**：`python -m unittest discover -s tests`（**233 项**）、插件
   `node tools/selftest.mjs`（**130 项**）、CI（ubuntu/windows × py3.10/3.12）、
   发布走 `v* tag + OIDC`（PyPI / npm 都不需要 token；注意 **pyproject 不能有 BOM**，B-064）。
7. **最该继续做的**（按收益）：

   | # | 事项 | 为什么 | 起手点 |
   |---|---|---|---|
   | 1 | schema 再瘦身 | 现在 6.8k 字符（≈3k tokens）**每轮**都付；dsh-ops 卡 400 token/工具 | 删少用参数（`model`/`prompt` 合并进 config），或把工具拆成按需激活 |
   | 2 | 静音探测 | 无声视频仍会白下 5–8MB 音频再报「无人声」（实测 13.6MB 白烧） | 先 ASR 3 个 30s 窗口（≈1.5MB），三点都 <6 字才判静音；**单点会误判**（开头 40s 纯 BGM 很常见） |
   | 3 | OCR 覆盖度 | 现在 n 帧均匀取，字幕很快的片子会漏句 | 按画面变化（切点）分配帧数；或先 9 帧粗扫、检出文字再补帧 |
   | 4 | 跨盘模型探测 | 现在只探 env / 用户目录 / legacy / FlashVoice，自定义位置（如 `E:\models`）找不到 | 加 `vl models --scan`（限深度 3 + 超时），找到就报路径 |
   | 5 | 台账精度 | 现在按 `exec.agent` 记账，重载即清零；图片不计入 | 先真机确认 `vidlens_budget` 是否累加；否则改按 `rootCallId` 或落文件 |

## 分发与用量怎么看（2026-10-26 记录）

GitHub 的 clone 数**不是用户数**，别拿它当安装量：

| 渠道 | 是否经过 GitHub | 能看到的量 |
|---|---|---|
| `pip install vidlens-mcp` / `pipx` | ❌（PyPI） | `pypistats.org/api/packages/vidlens-mcp/recent`，实测 last_week **115** |
| `npm install dsh-vidlens` | ❌（npm registry） | `api.npmjs.org/downloads/point/last-week/dsh-vidlens`（刚发布返回 404，几天后才有数） |
| `dsh plugin add github:cctv2333/dsh-vidlens` | ✅ **真的 git clone** | 会计进本仓库的 clone 数 |
| `git clone`（插件 README 的"先有一份 vidlens"备选） | ✅ | 会计进 vidlens 的 clone 数 |

这解释了 10-25 的差异：**插件的推荐安装方式 B 是 `github:` 直装（clone）**，而 Python 核心的推荐
方式是 `pipx install`（PyPI，不计 clone）。所以"插件 clone 多、核心 clone 少"是**安装路径不同**，
既不代表插件用户更多，也不代表他们必须去 clone 核心——核心它们在 PyPI 装。

两个仓库在 2026-10-25 的 clone 数（250/95 与 259/70 uniques）几乎全部落在创建当天，
与"当天十几次 CI + dependabot PR + 镜像抓取"同一天，**不能据此推断人**；
人类信号只有 views uniques 11 / 15。要看真实使用，应看 PyPI/npm 下载数，
或让用户跑 `vidlens_doctor`（我们**没有**任何遥测）。

## 详细文档

详细交接文档在 [`handover/`](handover/README.md)。

建议阅读顺序：

1. [`handover/README.md`](handover/README.md) — 项目是什么、当前状态、五分钟上手
2. [`handover/ARCHITECTURE.md`](handover/ARCHITECTURE.md) — 模块、数据流、锁、缓存
3. [`handover/MODELS.md`](handover/MODELS.md) — 模型/非模型能力、体积、许可证
4. [`handover/DISTRIBUTION.md`](handover/DISTRIBUTION.md) — 能不能分发、打包清单
5. [`handover/ARCHIVE.md`](handover/ARCHIVE.md) — 全部档案/验证索引
6. [`handover/REPRODUCE.md`](handover/REPRODUCE.md) — 复现命令

工程台账：

- [`WORKLOG.md`](WORKLOG.md)
- [`BUG_LEDGER.md`](BUG_LEDGER.md)
- [`HARDCODE_AUDIT.md`](HARDCODE_AUDIT.md)
- [`README.md`](README.md)
- [`NOTICE.md`](NOTICE.md)
