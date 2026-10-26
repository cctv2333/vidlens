# 工程交接入口

## 当前状态（2026-10-26，V-009）

新接手先看这四件事：

1. **两个仓库**：`cctv2333/vidlens`（Python + MCP，PyPI `vidlens-mcp`）、
   `cctv2333/dsh-vidlens`（DSH 插件，npm `dsh-vidlens`）。插件通过常驻桥
   `bridge/vidlens_bridge.py` 复用 `vl_mcp` 的函数，不存在第二份实现。
2. **上下文预算已就位**：`brief` 默认 digest；`watch` 分段；插件侧 per-Agent 台账
   （12k 提示 / 24k 硬钳）；相同参数调用不重跑。来龙去脉见 `BUG_LEDGER.md` B-050…B-056。
3. **验证入口**：`python -m unittest discover -s tests`（136 项）、插件
   `node tools/selftest.mjs`（122 项）、CI（ubuntu/windows × py3.10/3.12）。
4. **最该继续做的**（按收益）：

   | # | 事项 | 为什么 | 起手点 |
   |---|---|---|---|
   | 1 | schema 再瘦身 | 现在 6,768 字符（≈3k tokens）**每轮**都付；dsh-ops 卡 400 token/工具 | 删少用参数（`model`/`prompt` 合并进 config），或把工具拆成按需激活 |
   | 2 | 台账精度 | 现在按 `exec.agent` 记账，重载即清零；图片不计入 | 先真机确认 `vidlens_budget` 是否累加；否则改按 `rootCallId` 或落文件 |
   | 3 | 失败 memo 时间窗 | 20 分钟内同参数不重跑，网络刚恢复时要靠 `refresh=true` | 改为指数退避，或失败 3 次后提示换 URL |
   | 4 | 去重的证据强度 | 我们只是本地记忆，dsh-ops 会证明「上次正文确实在最近一次请求里」 | 读 `docs/context-read-dedup.md` 再决定要不要接宿主 `tools/result` |
   | 5 | 分段与批量的取舍 | 用户要结论时不该被要求"继续看"（已改成默认粗看） | 若要支持"一次看 3 段"，加 `ranges=[...]` 而不是让模型连调 |

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
