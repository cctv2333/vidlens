# 工程交接入口

## 当前状态（2026-10-26，V-012）

新接手先看这五件事：

1. **两个仓库**：`cctv2333/vidlens`（Python + MCP，PyPI `vidlens-mcp` 1.5.0）、
   `cctv2333/dsh-vidlens`（DSH 插件，npm `dsh-vidlens` 1.3.0）。插件通过常驻桥
   `bridge/vidlens_bridge.py` 复用 `vl_mcp` 的函数，不存在第二份实现。
2. **上下文预算已就位**：`brief` 默认 digest；`watch` 分段；插件侧 per-Agent 台账
   （12k 提示 / 24k 硬钳）；相同参数调用不重跑；大图不再 base64 内联。见 B-050…B-062。
3. **画面上的字现在能读**：`video_ocr`（可选依赖 `pip install "vidlens-mcp[ocr]"`，
   RapidOCR / Apache-2.0 / 模型随包分发 / 离线）。实测 12 帧 46s、≈1.3k tokens 拿到
   16 条带时间码字幕。三个测试视频里 2 个没有人声，这条链路是它们的唯一入口。见 B-063。
4. **验证入口**：`python -m unittest discover -s tests`（172 项）、插件
   `node tools/selftest.mjs`（127 项）、CI（ubuntu/windows × py3.10/3.12）、
   发布走 `v*` tag + OIDC（PyPI / npm 都不需要 token）。
5. **最该继续做的**（按收益）：

   | # | 事项 | 为什么 | 起手点 |
   |---|---|---|---|
   | 1 | schema 再瘦身 | 现在 6.8k 字符（≈3k tokens）**每轮**都付；dsh-ops 卡 400 token/工具 | 删少用参数（`model`/`prompt` 合并进 config），或把工具拆成按需激活 |
   | 2 | 静音探测 | 无声视频仍会白下 5–8MB 音频再报「无人声」（实测 13.6MB 白烧） | 先 ASR 3 个 30s 窗口（≈1.5MB），三点都 <6 字才判静音；**单点会误判**（开头 40s 纯 BGM 很常见） |
   | 3 | OCR 覆盖度 | 现在 n 帧均匀取，字幕很快的片子会漏句 | 按画面变化（切点）分配帧数；或先 9 帧粗扫、检出文字再补帧 |
   | 4 | 台账精度 | 现在按 `exec.agent` 记账，重载即清零；图片不计入 | 先真机确认 `vidlens_budget` 是否累加；否则改按 `rootCallId` 或落文件 |
   | 5 | 失败 memo 时间窗 | 20 分钟内同参数不重跑，网络刚恢复时要靠 `refresh=true` | 改为指数退避，或失败 3 次后提示换 URL |

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
