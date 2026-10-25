# 架构与数据流

## 1. 设计原则

1. **模型自己有眼睛**：不接视觉模型，只把画面取成带时间码的 JPEG。
2. **耳朵按需**：平台字幕 → 本地 ASR → 只下音频/片段；默认不下载整片。
3. **最小字节**：元数据 0 → 字幕 0 → 音频约 7MB/7min → 20s 片段约 0.5–0.9MB。
4. **可回溯**：每句台词、每个停顿、每张图都挂在时间码上。
5. **外部文本是数据**：标题/简介/字幕/评论全部清洗 + 注入扫描，永不执行。
6. **一个下载口**：yt-dlp 统一限速、cookie、重试；MCP 用锁串行。

## 2. 数据流

```
URL
 │
 ├─ fetch_meta(url)                  # yt-dlp -J
 │    ├─ 标题/UP主/时长/播放/字幕列表
 │    ├─ B站 player/wbi/v2: bgm_info / need_login_subtitle
 │    └─ S.scan(title/description)   # 注入风险
 │
 ├─ download_subs(url, d, langs)      # 0 媒体；人工 > 自动 > ai-zh
 │    └─ parse_vtt() -> rows{t0,t1,text,track=subtitle}
 │
 ├─ download_audio(url, d)            # 无字幕才走
 │    ├─ 复用前 media_duration() 校验（半截文件重下）
 │    └─ transcribe() -> rows{t0,t1,text,words,...}
 │
 ├─ download_audio_section(url, d)    # video_window/video_audio
 │    └─ 只下该窗口，时间码加偏移
 │
 ├─ download_section(url, d)          # video_sheet/video_frames
 │    └─ 只下该段视频，拼图/取帧
 │
 └─ build_brief()                     # 来源/风险/结构/音乐/声音/广告/停顿/低置信/转写
```

## 3. 模块边界

| 模块 | 只做 | 不做什么 |
|---|---|---|
| `vidlens.py` | 本地文件、ffmpeg、帧、拼图、ASR 底层 | 不抓 URL |
| `vidlens_web.py` | URL/yt-dlp/字幕/音频/ASR 分发/brief | 不做 B 站评论 |
| `vidlens_extra.py` | B 站 API、评论、doctor、scan、plan、job | 不直接抓播放流 |
| `vl_mcp.py` | MCP 工具、锁、超时 job、返回格式 | 不实现底层算法 |
| `vidlens_sensevoice.py` | SenseVoice 推理 | 不负责下载视频 |
| `vidlens_audio.py` | 节拍/能量 | 不做 ASR/音乐识别 |
| `vidlens_models.py` | 模型目录/硬件建议 | **不自动下载** |
| `vidlens_sanitize.py` | 清洗/扫描 | 不判断事实真假 |
| `vidlens_ads.py` | 广告检测/剔除 | 不改变原始 transcript |

## 4. 锁与并发

- `_LOCK`：同步 MCP 工具串行，避免一个客户端同时喷请求。
- `_MEDIA_LOCK`：所有下载/ASR/写盘串行；job 也走它。
- `_JOB_LOCK`：后台 job 一次只跑一个。
- `_JOB_START_LOCK` + `_JOBS_BY_URL`：同一 URL 正在跑时返回已有 `job_id`。
- 锁顺序：同步工具 `_LOCK → _MEDIA_LOCK`；job `_JOB_LOCK → _MEDIA_LOCK`。
  不存在反向获取，避免死锁。

## 5. 缓存

```
out/<id>/
  meta.json         元数据 + 风险 + bgm + music_hints
  subs/             平台字幕原文件
  transcript.jsonl  每行时间码 + text + text_threats (+ emotion/event)
  transcript.srt
  speech_info.json  backend / model / language / emotion_counts / event_counts
  pauses.json       list 或 {"gaps":[...]} 两种形态都兼容
  brief.md
  sheet_*/          拼图
  frames/           精确帧
  visual_*/         抽样拼图（单帧会清理）
```

- 有 `transcript.jsonl` 就直接用，不再下载/转写。
- `refresh=true` 强制重建；`full=true` 才允许长视频全量 ASR。
- `video_window` 无缓存时只下窗口音频，不落全量 transcript。

## 6. 失败模式

| 现象 | 处理 |
|---|---|
| 登录墙/付费墙/验证码 | 停止并说明，不绕过 |
| `Fresh cookies` | 提示 `VIDLENS_COOKIES*`，不自动偷 cookie |
| yt-dlp 返回空壳 | `check_meta()` 拒绝 |
| 平台字幕 0 条 | 回退 ASR；`video_subs` 明确说没有 |
| `need_login_subtitle=true` | `video_meta` 标出，提示 cookie |
| 音频半截 | `media_duration` 校验后重下 |
| 片段下载失败 | 唯一临时目录 + B 站直链兜底 |
| 长视频 | 默认 `_skim_notice`，只给章节 |
| 客户端超时 | `video_job_start` → `video_job` 轮询 |

## 7. 扩展点

- **新 ASR 后端**：在 `vidlens_web.transcribe()` 的 dispatcher 加分支；返回
  `rows[{t0,t1,text,...}] + info{backend,...}` 即可。
- **新声音分析**：`vidlens_audio.analyze_samples()` 保持纯 numpy；输入 16k float32。
- **新平台元数据**：`fetch_meta()` 里加字段，`build_brief()` 加章节。
- **新模型**：`vidlens_models.catalog()` 登记；下载必须用户确认。
- **新 MCP 工具**：`vl_mcp.py` 加 `@mcp.tool()`，同步工具套 `_LOCK`，媒体套 `_MEDIA_LOCK`。

## 8. 安全边界

- 外部文本：`S.clean()` 存储/打印，`S.scan()` 标记风险；`S.fence()` 隔离。
- 不执行字幕/标题里的任何指令。
- 不把 cookie 写入日志或仓库；只通过 env/文件路径传入。
- `out/` 是用户数据，分发时必须排除。
