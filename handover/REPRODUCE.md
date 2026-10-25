# 复现与验证命令

## 1. 安装与自检

```bat
cd /d D:\vidlens\vidlens
install.cmd

.venv\Scripts\python.exe vidlens.py doctor
.venv\Scripts\python.exe vidlens.py models
.venv\Scripts\python.exe vidlens.py models --recommend
```

预期：

```
11/11 ok
OK   asr backend: sensevoice (local, no network)
```

## 2. 测试

```bat
.venv\Scripts\python.exe -m unittest discover -s tests
```

预期（2026-10-25）：

```
Ran 94 tests
OK (skipped=1)
```

网络测试：

```bat
set VIDLENS_NET_TESTS=1
.venv\Scripts\python.exe -m unittest discover -s tests
```

## 3. 平台音乐元数据（0 媒体下载）

```bat
.venv\Scripts\python.exe vidlens.py meta https://www.bilibili.com/video/BV1PvHX61EgV/
```

预期包含：

```
平台音乐: Macarena (River Re-Mix 103 BPM)
音乐链接: https://music.bilibili.com/h5/music-detail?...
```

## 4. 声音信号（只下 20 秒）

```bat
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,r'D:\vidlens\vidlens'); import vl_mcp as M; print(M.video_audio('https://www.bilibili.com/video/BV1PvHX61EgV/', start='00:00', end='00:20'))"
```

预期包含：

```
- 平台标注音乐: 《Macarena (River Re-Mix 103 BPM)》
- 语种: en
- 事件: Speech
- 估计节拍: 9x.x BPM
```

## 5. SenseVoice 直连（不经过 MCP）

```bat
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,r'D:\vidlens\vidlens'); import vidlens_sensevoice as sv; print(sv.status()); rows, info = sv.transcribe(r'D:\vidlens\vidlens\demo\speech.wav'); print(info); print(rows[0]['text'][:80], rows[0]['emotion'], rows[0]['event'])"
```

预期：`available=True`；`backend=sensevoice`；`NEUTRAL/Speech`。

## 6. Whisper 离线（验证不联网）

```bat
set VIDLENS_ASR=whisper
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,r'D:\vidlens\vidlens'); import vidlens_web as w; rows, info = w.transcribe(r'D:\vidlens\vidlens\demo\speech.wav'); print(info.get('backend'), info.get('local_files_only'))"
```

预期：`whisper True`（缓存命中，不联网）。

## 7. B 站 AI 字幕（需要登录 cookie）

```bat
:: 推荐：浏览器扩展导出 cookies.txt
set VIDLENS_COOKIES=D:\path\cookies.txt

.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,r'D:\vidlens\vidlens'); import vidlens_web as w; rows,name=w.download_subs('https://www.bilibili.com/video/BV1AxJ16QEeM/', __import__('pathlib').Path('out/BV1AxJ16QEeM'), w.sub_langs_for('zh')); print(len(rows), name); print(rows[:3])"
```

预期：`rows>0`，文件名含 `ai-zh`；若无 cookie，`need_login_subtitle=true`，返回 0 条。

> Edge 新版使用 app-bound 加密，yt-dlp 的 `--cookies-from-browser edge` 可能报
> `Failed to decrypt with DPAPI`。这不是本工程的 bug；用 cookies.txt 或登录后的
> 浏览器导出即可。

## 8. 真实窗口（只下 20 秒）

```bat
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,r'D:\vidlens\vidlens'); import vl_mcp as M; print(M.video_window('https://www.bilibili.com/video/BV1PinG6fEPX/', start='02:00', end='02:20'))"
```

预期：来源 `asr(window 02:00.000-02:20.000, sensevoice)`，目录无 `audio.*`。

## 9. 失败排查

| 症状 | 先看 |
|---|---|
| `doctor` 有 BAD | 缺 ffmpeg/yt-dlp/依赖/模型/磁盘 |
| 每次启动联网 | 是否用了 Whisper 且 `local_files_only` 未生效；看 `speech_info.json` |
| SenseVoice 不可用 | `sv.status()`：模型/词表/`sherpa-onnx` |
| 字幕 0 条 | `need_login_subtitle`、cookie、`--sub-langs` |
| `Failed to decrypt with DPAPI` | 浏览器 app-bound 加密；用 cookies.txt |
| 长视频不转写 | 默认抽样；`video_brief(full=true)` 才全量 |
| job 超时 | `video_job_start` → `video_job(wait_seconds=20)` 轮询 |
