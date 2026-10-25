# 分发评估与清单

## 1. 结论

**技术上可以分发，但不能把当前目录原样打包。**

必须排除：

- `.venv/`（含本机 Python 包、18.8MB sherpa）
- `out/`（用户视频转写、评论、brief、截图——隐私数据）
- `bin/`（ffmpeg 副本；许可证/体积）
- `__pycache__/`
- `mcp.json`（本机绝对路径；改发 `mcp.example.json`）
- `tools/manual/`（一次性调试脚本、硬编码路径）
- 模型权重：Whisper 484MB / SenseVoice 937MB
- cookies、浏览器配置、API key
- `dist/` 本身

**法律上**：仓库已采用 **MIT**（`LICENSE`，2026-10-25 决定）。分发时保留
`LICENSE` 与 `NOTICE.md` 的第三方归属即可；模型权重不要随包发。

## 2. 可分发包内容

```
vidlens-src-YYYYMMDD.zip
├─ *.py
├─ tests/
├─ demo/                  # 小样本，可选用
├─ README.md
├─ NOTICE.md
├─ WORKLOG.md
├─ BUG_LEDGER.md
├─ HARDCODE_AUDIT.md
├─ HANDOVER.md            # 根入口（指向 handover/）
├─ handover/
│   ├─ README.md
│   ├─ ARCHITECTURE.md
│   ├─ MODELS.md
│   ├─ DISTRIBUTION.md
│   ├─ ARCHIVE.md
│   └─ REPRODUCE.md
├─ requirements.txt
├─ install.cmd
├─ vl.cmd
└─ mcp.example.json
```

不包含：

- 模型权重、tokens（tokens 308KB 可单独发，但要确认上游许可证）
- `mcp.json`、`out/`、`.venv/`、`bin/`
- `tools/manual/`

## 2.5 本次构建

```
dist/vidlens-src-20261025.zip
```

大小与 SHA256 见 `dist/SHA256SUMS.txt`（zip 内不自带自身哈希，避免自指）。

解压到临时目录后，用同一 venv 跑：

```
Ran 94 tests in 8.496s
OK (skipped=1)
```

说明：包内没有 `out/`、`.venv/`、`bin/`、`mcp.json`、模型权重、`__pycache__`；
`tests/`、`handover/`、`demo/` 目录结构完整。

## 3. 构建命令（Windows PowerShell）

```powershell
cd D:\vidlens\vidlens
$stamp = Get-Date -Format yyyyMMdd
$zip = "dist\vidlens-src-$stamp.zip"
New-Item -ItemType Directory -Force dist | Out-Null

$paths = @(
  "*.py", "tests", "demo", "handover",
  "README.md", "NOTICE.md", "WORKLOG.md", "BUG_LEDGER.md",
  "HARDCODE_AUDIT.md", "HANDOVER.md", "requirements.txt",
  "install.cmd", "vl.cmd", "mcp.example.json"
)
Compress-Archive -Path $paths -DestinationPath $zip -Force
Get-FileHash $zip -Algorithm SHA256
```

验证：

```powershell
tar -tf $zip | Select-String "out/|\.venv/|bin/|mcp\.json|\.onnx|\.bin|__pycache__"
# 应该没有输出
```

## 4. 换机安装

1. 解压到任意目录（建议非 C 盘）。
2. `install.cmd`（Python 3.9+；Windows）。
3. 复制 `mcp.example.json` → `mcp.json`，把 `<PROJECT>` 换成实际目录。
4. 自检：
   ```bat
   .venv\Scripts\python.exe vidlens.py doctor
   .venv\Scripts\python.exe -m unittest discover -s tests
   ```
5. 模型：
   - 没有 SenseVoice：自动回退 Whisper；首次会下载 Whisper small（约 484MB）。
   - 有 SenseVoice：设 `VIDLENS_SENSEVOICE_MODEL` / `VIDLENS_SENSEVOICE_TOKENS`。
   - 先用 `vl models` / `vl models --recommend` 看本机建议，**不要静默下载**。
6. 需要 B 站 AI 字幕/抖音：用户显式提供 `cookies.txt` 或浏览器 cookie；
   不把 cookie 写进仓库。

## 5. 可移植性风险

| 项 | 现状 | 建议 |
|---|---|---|
| 操作系统 | Windows 优先（`install.cmd`、字体、ffmpeg shim） | Linux/macOS 手动 venv + ffmpeg |
| Python | 3.12 实测；要求 3.9+ | 建议 3.11/3.12 |
| pip 镜像 | `install.cmd` 默认清华源 | 海外用户改 `MIRROR` 或 `VIDLENS_PIP_INDEX` |
| 模型路径 | SenseVoice 默认指向本机 AppData | 用 env 覆盖 |
| 模型根 | `D:\dev\models`；无 D 盘退 `~/.cache/vidlens-models` | `VIDLENS_MODEL_ROOT` |
| `mcp.json` | 本机绝对路径 | 发 `mcp.example.json` |
| 字体 | `C:\Windows\Fonts` + 跨平台候选 | 缺字体时拼图仍可用，时间码可能缺字 |
| 网络 | yt-dlp 依赖站点/地区 | 失败时明确报错，不绕过登录 |
| 模型许可证 | 未随包分发 | 让用户自己下；保留 NOTICE |

## 6. 分发前检查清单

- [x] 选好 `LICENSE`（MIT，已完成）。
- [ ] `NOTICE.md` 覆盖 sherpa-onnx / SenseVoice / Whisper / ffmpeg。
- [ ] 删除 `out/`、`.venv/`、`bin/`、`mcp.json`、`__pycache__/`、`tools/manual/`。
- [ ] 确认 zip 里没有 `*.onnx`、`*.bin`、`*.safetensors`、cookies、日志。
- [ ] 在一台**干净机器**跑 `install.cmd`、`doctor`、`unittest`。
- [ ] 用 `mcp.example.json` 配一次 Chatbox，确认 15 个工具可见。
- [ ] 跑一条真实视频：`video_meta` → `video_plan` → `video_window`。
- [ ] 确认没有把用户视频/评论/转写打进包。
- [ ] 记录 zip 的 SHA256。

## 7. 不分发的东西

- `out/BV...`：转写、评论、brief、截图 —— 用户数据。
- `out/*.log`：可能含路径、标题、错误上下文。
- `secrets/`（如果有）：cookie/API key。
- 模型权重：体积大且受上游许可证约束。
- `tools/manual/`：一次性脚本，含本机路径。
