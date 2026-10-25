# BUG_LEDGER — vidlens

> 索引：只读本区 + 最近 ≤10 条 + 相关条目（grep）。状态写在「现象」前：`[OPEN]` / `[FIXED]` / `[WONTFIX]`。

| # | 现象 | 根因 | 防御规则 |
|---|---|---|---|
| B-001 | `[FIXED]` `plan()` 在 CLI 形态 pauses.json 下抛 `AttributeError: 'str' object has no attribute 'get'` | `gaps` 读到整个字典，遍历到键字符串 | 读外部 JSON 先归一化形态；用 `read_pauses()`，坏字段跳过不抛 |
| B-002 | `[FIXED]` MCP brief 可能静默缺「分步建议」 | `_do_brief` 调 `plan()` 后 `except Exception: pass`；章节又追加在 9000 字截断之后 | 不吞异常；章节在「结构」后早输出；用已算出的 cuts/gaps，不再二次 `fetch_meta` |
| B-003 | `[FIXED]` MCP 从不用平台字幕，docstring 却承诺“有字幕零下载” | `_rows_with_media` 只走 `download_audio` + ASR；字幕只存在于 CLI `cmd_grab` | MCP 字幕优先；无字幕才 ASR；source 标清 `subs(name)` / `asr(...)`；新增 `video_subs` |
| B-004 | `[FIXED]` 抖音等需匿名 cookie 的站点在 MCP 直接失败 | `run_yt` 无 cookie 参数；MCP 无入口 | `VIDLENS_COOKIES` / `VIDLENS_COOKIES_FROM_BROWSER`；识别 `Fresh cookies` 给可执行提示 |
| B-005 | `[FIXED]` 后台 job 绕过串行化锁，可能并发写同一 out 目录 | `_do_brief` 不持锁；同步工具持 `_LOCK` | `_MEDIA_LOCK` 管下载/ASR/写盘，`_JOB_LOCK` 串行 job，同 URL 在跑时返回已有 job |
| B-006 | `[FIXED]` MCP 转写行只 `clean` 不 `scan`，注入特征不进风险清单 | CLI 逐行 `S.scan`，MCP 漏了 | 共用 `_annotate_rows`；风险项带时间码；缓存行也补扫 |
| B-007 | `[FIXED]` 音频缓存只要 >100KB 就复用，半截文件会被当素材 | `download_audio` 不校验时长/完整性 | 复用前 `media_duration`；与 meta 时长差 >max(5s,2%) 则重下 |
| B-008 | `[FIXED]` `video_frames` 共用 `tmp_sec`，可能取到旧片段 | 目录固定，`download_section` 取最大文件 | 每次 `mkdtemp` 唯一子目录；用完 `rmtree`；sheet 同样隔离 |
| B-009 | `[FIXED]` `visual_scan` 只删视频，抽帧 jpg 留存 | `work/` 未清理 | 拼图后删单帧/标签，保留 sheet；开始前清旧产物 |
| B-010 | `[FIXED]` `quiet()` 死代码，README 却称所有库函数都被它包住 | 实现改为非 verbose + 锁，文档未更新 | 删除死代码；文档写真实机制，禁止长时间 `redirect_stdout` |
| B-011 | `[FIXED]` `av>=11` 无上界，与注释意图矛盾 | requirements 未卡上界 | `av>=11,<19`；注释写明原因 |
| B-012 | `[FIXED]` 负时间/超时长取帧不夹紧 | `_clamp_range` 不处理负数；`video_frames` 静默丢坏点 | 统一夹紧 `[0,dur]`；坏点明确列出；全部越界返回 ERROR |
| B-013 | `[FIXED]` 根目录遗留 `_meta3.py` / `_run_three.ps1`，含硬编码路径 | 一次性调试脚本未归档 | 移到 `tools/manual/`；新脚本禁止硬编码用户路径 |
| B-014 | `[FIXED]` 多处魔法数字（9000 字、200MB、100KB、0.25、360/480、300s、60s） | 直接写字面量 | 命名常量集中定义；`HARDCODE_AUDIT.md` 登记剩余领域常量 |
| B-015 | `[FIXED]` 长视频默认全量 ASR，与“人类会加速/跳过”不符 | `video_brief` 没有深浅档；MCP 无 `plan` 工具 | 新增 `video_plan`；>20 分钟且无字幕默认只给章节；`full=true` 才全量 |
| B-016 | `[FIXED]` 40 分钟连续解说被算成 1 个章节，误报“视频不长” | 章节只认切点/≥2s 静音；该片最长静音 1.1s | 长空洞按固定窗口补网格；长视频 1 章时也按固定窗口提示 |
| B-017 | `[FIXED]` `video_plan` 对 40 分钟视频说“视频不长” | 只看章节数，没看时长 | 时长 > 20 分钟时改为“按固定窗口分段” |
| B-018 | `[FIXED]` 广告数字正则把“毫克”写成“毫光” | 笔误 | 单测直接断言 `NUM_PROMO` 匹配“2毫克”、不匹配“2毫光” |
| B-019 | `[FIXED]` 字幕文件散落在 out 根目录，重复调用可能读到旧字幕 | `download_subs` 用 `sub.%(ext)s` 且不清理 | 统一写 `subs/`；下载前清旧 `sub*.vtt/srt`；人工字幕优先 |
| B-020 | `[FIXED]` `video_frames` 对负数时间显示成 `00:00` | `hms()` 会 clamp 到 0，丢失原值 | 跳过项用原始秒数显示；合法点单独夹紧 |
| B-021 | `[FIXED]` 长视频已有缓存时仍被抽样守卫拦住 | 守卫只看时长/字幕，不看 `transcript.jsonl` | 有完整缓存就直接出 brief（不再产生下载成本） |
| B-022 | `[FIXED]` `video_window` 无缓存时下整片音频再转写 | 复用了 `_rows_with_media` 的全量路径 | 新增 `download_audio_section`：只下该窗口音频；时间码加偏移；临时目录清理 |
| B-023 | `[FIXED]` 每次新进程/新对话都看到“下载模型” | faster-whisper 加载前走 HF 联网检查（不是重下 483MB 权重） | 本地缓存存在时 `local_files_only=True`；失败再回退联网；实测 1.68s 加载 |
| B-024 | `[FIXED]` 用户已有 SenseVoice ONNX（937MB），工具却只认 Whisper | 没接 sherpa-onnx 后端 | 新增 `vidlens_sensevoice.py`；复用现成模型 + 308KB 词表；实测 1.54s 加载 |
| B-025 | `[FIXED]` 没有音频情感/事件/节拍信号 | 只做 ASR 和静音检测 | SenseVoice 的 emotion/event + numpy 节拍估计；`video_audio`；全部标启发式 |
| B-026 | `[OPEN]` B 站 AI 字幕没有专门入口 | 只走 yt-dlp 通用字幕；匿名 `player/v2` 为空，`need_login_subtitle=true` | 字幕语言已加 `ai-zh`；代码路径已就绪；正例需登录 cookie（Edge 锁定中） |
| B-027 | `[FIXED]` SenseVoice 跑完来源仍写 `model=small` | `_rows_with_media`/`cmd_grab` 用入参 model 拼来源 | 读 `info["backend"]`，来源写 `asr(sensevoice, ...)` / `asr(whisper, ...)` |
| B-028 | `[FIXED]` 有语音+背景音乐时只显示“背景音乐”，易误读为无语音 | SenseVoice 每块只给一个 event 标签 | brief 加注“有语音的段落也可能同时有背景音乐” |
| B-029 | `[FIXED]` 默认字幕语言不含 `ai-zh`，B 站 AI 字幕匹配不到 | 默认列表只有 zh.* / en.* | 加 `ai-zh,ai-en,ai-ja,ai-ko,ai-yue,ai-*` |
| B-030 | `[FIXED]` 平台已给 BGM 歌名，工具却不显示 | `fetch_meta` 没取 `player/wbi/v2` 的 `bgm_info` | `video_meta`/`video_brief`/`video_audio` 统一显示；简介关键词兜底 |
| B-031 | `[FIXED]` 字幕登录门槛不透明 | 只显示 0 种字幕，用户不知道为什么 | `video_meta` 显示 `need_login_subtitle=true` |
| B-032 | `[FIXED]` 不知道本机该用/能下哪个模型 | 没有模型目录与硬件建议 | `vidlens_models` + `vl models`：只读目录/推荐，不自动下载 |
| B-033 | `[FIXED]` CED-mini 未接入（V-007 接入） | 9.7M 参数 AudioSet 分类，不是 ASR；曾缺 mel 前端与 527 类标签表 | 用 sherpa-onnx `AudioTagging` + `k2-fsa` int8 模型（10.4MB）+ `class_labels_indices.csv`；新增 `vidlens_audioevents.py`、MCP `video_soundscape`、插件 `vidlens_soundscape`；实测加载 0.14s、28s 音频推理 43ms |
| B-034 | `[WONTFIX]` AcoustID 未接入 | 需 fpcalc + API key，3 req/s、非商业；平台 BGM 更直接 | 先用平台元数据；确有需要再做指纹查询 |
| B-035 | `[FIXED]` 两个进程（DSH 会话 / MCP 服务器 / 插件桥）同时处理同一视频会争 `out/<id>/` | `_MEDIA_LOCK` 是进程内 `threading.Lock`，跨进程不可见 | 新增 `vidlens_web.CrossProcessLock`（进程内 RLock + `out/.media.lock` 文件锁，msvcrt/flock，超时 `VIDLENS_LOCK_TIMEOUT` 默认 900s）；`vl_mcp._MEDIA_LOCK` 换成它；实测两进程真实 `video_sheet` 串行（第二个 acq 在第一个 end 之后） |
| B-036 | `[FIXED]` 装成 wheel 后会往 site-packages 写 `out/` 与 `bin/` | 路径默认取模块目录，源码与安装两种形态混在一起 | `vidlens.project_root()`：有 checkout 标记用工程目录（保持现状），否则用 `%LOCALAPPDATA%\vidlens` / `~/.local/share/vidlens`；`out_root()` 与 `ffmpeg_dir()` 都走它 |
| B-037 | `[FIXED]` Linux（GitHub CI）上 `video_sheet` 整张失败：`No such filter: 'drawtext'` | imageio-ffmpeg 的 Linux 构建没编 libfreetype；代码只判断「有字体」就加 drawtext | 新增 `vidlens.has_drawtext()` 探测（`ffmpeg -filters`，只探一次）；`cmd_sheet` 与 `extra._label_frame` 都改判 `font and has_drawtext()`；回执里注明「未烧时间码」；新增 `test_sheet_survives_ffmpeg_without_drawtext` 复现该场景 |
