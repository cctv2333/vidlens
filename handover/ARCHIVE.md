# 档案索引

> `out/` 下除验证文档/日志外，都是用户视频数据，**不可分发**。

## 1. 工程文档

| 文件 | 内容 |
|---|---|
| `README.md` | 安装、CLI、MCP 工具、预算、方言、默认抽样 |
| `NOTICE.md` | 第三方依赖/模型许可证与归属 |
| `WORKLOG.md` | V-001～V-005：目标/改动/验证/回退点 |
| `BUG_LEDGER.md` | B-001～B-034：现象/根因/防御规则/状态 |
| `HARDCODE_AUDIT.md` | AST 扫描 + 人工分类：常量/路径/阈值 |
| `handover/README.md` | 交接入口 |
| `handover/ARCHITECTURE.md` | 模块、数据流、锁、缓存、失败模式 |
| `handover/MODELS.md` | 模型/非模型能力、体积、许可证、下载政策 |
| `handover/DISTRIBUTION.md` | 分发评估、zip 内容、换机清单 |
| `handover/ARCHIVE.md` | 本文件 |
| `handover/REPRODUCE.md` | 复现测试/自检/真实链路 |

## 2. 验证记录

| 文件 | 证明 |
|---|---|
| `out/plan_bug_evidence.md` | pauses.json 双形态崩溃的复现 traceback + 修复 |
| `out/tests_v12.log` | v1.2 的 90 项测试（历史） |
| `out/tests_v13.log` | SenseVoice 接入后的 91 项测试（历史） |
| `out/tests_v14.log` | 当前 94 项测试通过 |
| `out/doctor_v14.log` | 11/11 + `asr backend: sensevoice (local, no network)` |
| `out/verification_v12.md` | 默认抽样/窗口/长视频/字幕 e2e |
| `out/verification_sensevoice.md` | SenseVoice 模型身份、速度、情感/事件、BGM |
| `out/verification_music_models.md` | 平台 BGM、AI 字幕登录门槛、CED-mini/AcoustID |

## 3. 代码与测试

- `tests/test_core.py`、`test_web.py`、`test_extra.py`、`test_ads.py`、`test_mcp.py`
- `tests/test_plan.py`：pauses.json 双形态、章节、job brief
- `tests/test_features.py`：字幕优先、长视频抽样、cookie、缓存完整性、负时间、
  声音工具、模型目录、music hints
- 网络测试默认跳过；`VIDLENS_NET_TESTS=1` 打开

## 4. 归档的一次性脚本

`tools/manual/meta3.py`、`tools/manual/run_three.ps1`
—— 含本机路径，仅作历史参考，不参与运行，不分发。

## 5. 模型/词表（不在仓库）

| 路径 | 大小 |
|---|---|
| `C:\Users\yu\AppData\Roaming\com.flashvoices\models\sense-voice-large.onnx` | 937,617,178B |
| `D:\dev\models\sensevoice\tokens.txt` | 315,894B |
| `D:\dev\models\whisper\...\model.bin` | 483,546,902B |

## 6. 分发包

构建后：`dist/vidlens-src-YYYYMMDD.zip`（SHA256 记录在构建输出里）。

本次：

```
dist/vidlens-src-20261025.zip
大小与 SHA256 见 dist/SHA256SUMS.txt
解压后 94 tests OK (skipped=1)
```

只含源码/测试/文档/示例配置；不含模型、`out/`、`.venv/`、`bin/`、`mcp.json`。

## 7. 数据保留

`out/<BV...>/` 是实际分析产物（转写、评论、brief、截图）。
保留策略：

- 只清理媒体，保留 `brief.md`：`vl clean --days 7`
- 整目录删除：`vl clean --days 30 --all`
- 分发/交接前：不要打包 `out/`，除非逐个确认无隐私内容。
