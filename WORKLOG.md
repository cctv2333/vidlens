# WORKLOG — vidlens

> 索引：只读本区 + 最近 ≤10 条 + 相关条目（grep）。更早条目按 `WORKLOG-archive-YYYYMM.md` 归档。

## 索引

| # | 日期 | 标题 | 状态 | 归档 |
|---|---|---|---|---|
| V-020 | 2026-10-28 | 另一台机器的真实故障：模型清单/下载/校验/锁/目录 七连修（B-074…B-080）+ 疑难杂症表 | 已完成 | — |
| V-019 | 2026-10-26 | 回应「爆缓存」质疑：量化实测 + 堵 video_subs 唯一无上限出口 + 缓存占用可见（B-072、B-073） | 已完成 | — |
| V-018 | 2026-10-26 | cookie 读不到的两种失败给出可执行提示（B-071）+ 实测本机无 Chrome / Edge 占用 | 已完成 | — |
| V-017 | 2026-10-26 | 真实站点实测（B站/爱奇艺/抖音）：抖音 modal_id 归一化 + 解析器失败可执行提示 + 中英双 README | 已完成 | — |
| V-016 | 2026-10-26 | 本地视频接进工具层（B-068）：local_path() 一处判定 + 五处短路 + 禁止删源文件 + 13 条回归 | 已完成 | — |
| V-015 | 2026-10-26 | 交接文档更新到 V-014 + 用量口径（clone ≠ 安装）+ 插件 README 去掉本机路径 | 已完成 | — |
| V-014 | 2026-10-26 | 音频模型也接下载链路：`vidlens_models(action="download")` + whisper 不再静默下载 + 乱码提示修复 | 已完成 | — |
| V-013 | 2026-10-26 | 去掉发布物里的本机路径（B-065）+ 清 4 处死代码 + 两条"无个人路径"护栏 | 已完成 | — |
| V-012 | 2026-10-26 | 内置本地 OCR（RapidOCR）：`video_ocr` + 水印/图表帧判定 + 许可证登记 | 已完成 | — |
| V-011 | 2026-10-26 | 外部 AI 实测反馈修复：无人声误判 / 摘要取样偏差 / 大图 base64 / 成本自述 / 口径时间戳 | 已完成 | — |
| V-010 | 2026-10-26 | awesome-dsh-plugin 收录 PR #9422 转绿（age 门槛 / 手动触发路径 / README 自动生成） | 已完成 | — |
| V-009 | 2026-10-26 | 上下文预算治理：digest 默认 / 分段 watch / 预算台账 / 调用去重 / schema 瘦身 | 已完成 | — |
| V-008 | 2026-10-25 | PyPI 打包 + 跨进程媒体锁 + 两仓库拆分（vidlens / dsh-vidlens） | 已完成 | — |
| V-007 | 2026-10-25 | 声音事件接入（CED-mini + AudioSet 527）：video_soundscape + DSH 插件 | 已完成 | — |
| V-006 | 2026-10-25 | 工程交接与可分发包（handover/ + dist zip） | 已完成 | — |
| V-005 | 2026-10-25 | B站 AI字幕/平台 BGM 元数据、模型目录与 CED-mini/AcoustID 调研 | 已完成 | — |
| V-004 | 2026-10-25 | 本地 ASR 复用：SenseVoice/Whisper 模型不重复联网 + 情感/事件调研 | 已完成 | — |
| V-003 | 2026-10-25 | 硬编码/魔法数字审计与字幕/抽样能力验收 | 已完成 | — |
| V-002 | 2026-10-25 | 审计 P1/P2 修复：字幕优先、cookie、锁、注入扫描、缓存与边界 | 已完成 | — |
| V-001 | 2026-10-25 | plan() / pauses.json 双形态崩溃修复 | 已完成 | — |

---

## 2026-10-28 另一台机器的真实故障（V-020 / B-074…B-080）

- **触发**：用户在另一台电脑上跑实测，让那边的 AI 写了 245 行报告发过来：一个 26 分钟的 B 站视频，
  从 `doctor` 到出转写，中间卡了 4 小时。核心不是「不会用」，是**工具自己前后矛盾**。
- **逐条对照报告修掉的（都是我们这边真错）**：
  1. `models list` 与 `download` 两张表不同步 → 合并成一张 `REGISTRY`（B-074）。
  2. whisper 写死 small 不降级 → `resolve_whisper()` 按 显式→env→small→base→tiny 取第一个完整的（B-075）。
  3. 下载不校验完整性（62MB 的 tiny 也算装好）→ 校验 4 个必需文件（B-076）。
  4. 并发下载排队 8 分钟、超时后无状态 → 非阻塞锁 + `download.state.json` + `action="status"`（B-077）。
  5. 落点不听指挥（权重去 F 盘 HT 缓存）、Windows symlink 双份 → 显式 `cache_dir` + `HF_HUB_DISABLE_SYMLINKS=1`，
     并且**不再为了下载把 484MB 模型加载进内存**（B-078）。
  6. doctor 的 `find_spec` 撒谎 → 真 import + tokenizers/av/模型目录/文件完整性四项新检查（B-079）。
  7. 顺手抓到自己埋的雷：`os.kill(pid, 0)` 在 Windows 上是**杀掉进程**，用它探活等于杀正在下载的进程（B-080）。
- **报告里我们能采纳、但没做的**：下载进度条（只做了状态，不做百分比）；超时后自动 cancel（不做自动动作，
  只给 status 让人判断）。理由一样：自动行为越界。
- **报告里不成立的**：P2-15「图片返回 base64 文本、没进视觉通道」——我们返回的是标准 `Image` 内容块，
  是那边客户端把图片块渲染成了文本；插件路径走 `attachments.saveImage` 不受影响。
- **ASR 质量那段是对的**：whisper-small 中文金融术语同音错字率高（财报→彩报、估值→固执、铜→同）。
  这是模型特性，不是 bug；已在 README 与提示里强调「术语密集内容优先看画面/OCR，别引用 ASR 原话」。
- **验收**：228 项测试（+17：注册表 5 / whisper 文件 6 / 下载闸门 4 / av 补丁 2）；
  并且在真机上重跑了 list/status/doctor 三条。
- **版本**：1.6.3 → **1.7.0**；插件 1.4.2 → **1.4.3**（schema 说明补 status）。
## 2026-10-26 「会不会爆缓存」的量化回答（V-019 / B-072、B-073）

- **触发**：用户转述有 AI 说这套东西会爆缓存，判断是幻觉。
- **先分两种「缓存」**，不能混着吵：
  - **上下文（token）**：digest 默认 1600 字、segment 1200、OCR 3200、brief 9000；插件侧还有
    per-Agent 台账（12k 提示 / 24k 硬钳）+ 相同参数去重 + 图片不内联。实测一次 brief 回 **383–622 tok**。
  - **磁盘（out/）**：本机跑了 23 个视频 = **28.2MB**，媒体用完即删，留下的是拼图/转写/brief。
- **但对方有一半是对的**：翻代码找到唯一没有总字数上限的出口 —— `video_subs(limit=200)`，
  每行最多 300 字，理论最坏 61k 字 ≈ 40k tokens 一次吐完。→ B-072，加 `MAX_SUB_CHARS=6000` + 「另有 N 条」。
- **另一半也对**：缓存只增不报。没有任何界面告诉你 out/ 现在多大。→ B-073，
  `doctor` 增 cache 行、插件 `library` 头部报总 MB + 清理命令。**不做自动删除**（删别人的东西比不删更坏）。
- **结论口径**：不是「不会爆」，是「每一处都有数、且都看得出来」。
- **版本**：1.6.2 → **1.6.3**；插件 1.4.1 → **1.4.2**。
## 2026-10-26 cookie 读不到时说什么（V-018 / B-071）

- **触发**：用户同意"试一试"抖音/爱奇艺的 cookie 路径，同时预告"我从来不在电脑上看抖音"。
  实测两个硬事实：`C:\Users\<user>\AppData\Local\Google\Chrome\User Data` **不存在**（Chrome 没装，
  所以 cookie 库根本没得读）；Edge 装了、有 cookie 库，但**21 个进程正在跑**，库被锁住 →
  `Could not copy Chrome cookie database`。
- **修法**：`cookie_hint()` 原来只覆盖"需要 cookie"，不覆盖"读不到 cookie"。补两条：
  - 占用型：先**完全退出浏览器**（含托盘/后台进程）；新版 Chrome/Edge 的 App-Bound 加密下，
    导出 `cookies.txt` + `VIDLENS_COOKIES` 更稳；
  - 缺失型：这台机器没装/没运行过该浏览器，换浏览器名或导出文件。
- **判断**：即使关掉 Edge，本机也大概率没有抖音 cookie（用户从不在电脑上刷抖音）。
  真实价值在于：**下一次别人遇到同样两句话，能得到能做的事**，而不是一个 GitHub issue 链接。
- **顺手**：两份 README 的 cookie 段落都写明"浏览器必须关闭"这条前提。
- **版本**：1.6.1 → **1.6.2**（插件无代码改动，不发 npm）。
## 2026-10-26 真实站点实测 + 双语 README（V-017 / B-069、B-070）

- **触发**：用户给了三个真链接要"先查 bug 再改 README"。查出来的不是崩溃，是**可用性**：
  - B 站 BV1fbHg6UEiB：全链路通（meta → brief，SenseVoice 1.9MB 音频、516 字台词、100% 覆盖）。
  - 爱奇艺 v_eienwprun0：`[iqiyi] Can't find any video` —— 解析器拿不到（站点改版/DRM），
    但提示只有 yt-dlp 的抱怨，用户不知道下一步。→ B-070，加 `extractor_hint()`。
  - 抖音 `jingxuan?modal_id=…`：`Unsupported URL` —— 地址栏形式解析器不认。→ B-069，
    在 `run_yt()` 单点归一化成 `/video/<id>`；归一到的那一层返回的是"需要 cookie"（这才是真实状态）。
- **为什么修在 `run_yt`**：那是"一个 URL 变成 yt-dlp 参数"的唯一咽喉，五处下载全部经过它，
  以后新增调用点不会再各自忘一次。
- **未做**：不给抖音/爱奇艺做绕过。需要 cookie 就明说需要 cookie；DRM 就说 DRM。
- **README 双语**：`README.md`（中文，canonical）+ `README.en.md`（English），顶部互相链接；
  两个仓库都做。顺手修掉文档里的**陈旧断言**：工具数 18/16 → 实际 18（核心）/21（插件）、
  测试 104 → 209、插件自检 96/98 → 130、"工程默认在 `D:\vidlens\vidlens`"（代码早已改成
  config → env → 同级目录 → cwd）、模型默认路径写成 `D:\dev\models`（现在是仅当存在才沿用）、
  文档示例里的 `C:\Users\yu\...` 与 `D:\vidlens\ocr`。
- **验收**：测试 209（+4 URL 形状）；插件自检 130/130；本地中文/空格/大写扩展名路径实跑通过。
- **版本**：PyPI 1.6.0 → **1.6.1**；插件 1.4.0 → **1.4.1**。
## 2026-10-26 本地视频接进工具层（V-016 / B-068）

- **触发**：用户说「不能看本地视频？明明可以看——这就是硬编码的问题」。上一轮我说成"vidlens 不能看本地视频"，
  把工具层的限制说成了工具的能力，错得比较外行：CLI 的 8 个原语（probe/shots/frames/sheet/speech/pauses/env/report）
  **一直是吃本地文件的**，`install.cmd` 里的自检就是 `vl.cmd probe demo\meeting.mp4`。
- **断点**：`vidlens_web` 只认 URL（"fetch the minimum bytes needed to understand a public video"），
  `vl_mcp` 的每个工具入口都先过 `web.fetch_meta` → yt-dlp，于是 `D:\a.mp4` 被解析成 scheme `d`：
  `Unsupported url scheme: "d"`。`file://` 则被 yt-dlp 以"安全原因默认关闭"挡掉。
- **修法（一处判定、五处短路）**：`vidlens_web.local_path()`
  - 认：纯路径、带引号、`file:///D:/…`、`~/x.mov`、正斜杠、相对路径；目录给明确报错；
  - 不认：`http(s)://`、`bilibili://`、`mailto:`、`BV…`（真 scheme 一律走网络老路）。
  然后 `fetch_meta` 用 ffmpeg banner（和 `vl probe` 同一份正则行为）、`download_subs` 返回空让调用方落回 ASR、
  `download_audio` 抽 16kHz 单声道 m4a、`download_video_lowest` 直接返回源文件、
  `download_section`／`download_audio_section` 用 ffmpeg 重编码切片（**不用 `-c copy`**：那会漂到关键帧，时间码全偏）。
- **顺手堵的洞（比修 bug 更要紧）**：`download_video_lowest` 在本地模式下返回**用户自己的文件**，
  而 `_rows_with_media`、`visual_scan`、`shot_cuts` 之后都有 `unlink`——那等于把用户的电影删了。
  新增 `vl_mcp._drop_temp(p, url)`：目的路径 == 源路径时**不删**；`vidlens_extra.visual_scan` 同样加守卫。
- **文案**：本地输入不再打印 `播放/点赞: None / None`（会被读成 0 播放），改为文件路径+规格+音轨；
  `brief` 的"来源"块同理。`video_subs` / `video_comments` / `video_full` 对本地输入直接说明"没有这个东西"，不编造。
- **验收**：`demo\meeting.mp4` 上跑通 probe / brief（ASR 覆盖 100%、77 字）/ sheet（4×3 带时间码）/ OCR（3 帧，无字=0 段）；
  测试 192 → **205**（+10 LocalSourceTests、+3 MCP `_drop_temp`/本地 meta/subs）；插件 selftest 128 → **130**。
- **版本**：PyPI 1.5.3 → **1.6.0**（功能新增）；插件 1.3.3 → **1.4.0**；`vl_mcp` server version 1.4.0 → 1.6.0（一直是陈的）。两仓均已发布（tag `v1.6.0` / `v1.4.0`，OIDC 自动发；从 PyPI 拉下 1.6.0 的 wheel 复核过 `local_path` 与 `_drop_temp` 都在里面）。
## 2026-10-26 音频模型也接上下载链路（V-014）

- **触发**：用户问「OCR 建立了下载链路。那音频模型呢？也是这样做的吗？我们只能在我们的环境上实现，
  要看很多结果只能看别人的环境」。
- **事实（先查再改）**：三个音频模型、三条完全不同的路——
  - **whisper**：`transcribe()` 先 `local_files_only=True`，失败就 `local_files_only=False`
    → 第一次转写**静默拉 484MB**。没有提示、没有大小、没有落点。
  - **CED-mini**：只有一句人工提示，指向插件里的 `tools/fetch_sound_model.py`（而那个脚本
    `default_dir()` 还硬编码 `D:\dev\models`，提示行本身是 GBK/UTF-8 混写的乱码）。
  - **SenseVoice**：根本没有下载路径，只能"你机器上已经有 FlashVoice"。
- **改动**：
  - `vidlens_models.ACQUIRABLE` + `acquire(name, confirm)` + `install_dir()` + `install_notice()`：
    规则与 OCR 完全一致——先报「大小 / 落点 / 换目录 / 怎么确认」，`confirm=true` 才下，
    下完回报真实路径。`VIDLENS_MODEL_AUTO_DOWNLOAD=ask|auto|off`，`auto` **只对 ≤20MB 生效**。
  - 工具 `vidlens_models(action="download", name=..., confirm=...)`；`list` 现在同时打印
    `MODEL_ROOT` / whisper 目录 / 声音事件目录 —— AI 可以直接把这些路径告诉用户。
  - whisper 静默下载改为 `acquire()`，不再自己 `local_files_only=False`。
  - CED 的 `install_hint()` 改为指向 `action=download`（手动说明保留）。
  - 插件脚本的乱码提示行与硬编码 `D:\dev\models` 一起修掉。
- **验证**：
  - `Ran 192 tests ... OK (skipped=1)`（新增 `ModelAcquireTests` 8 项：notice 字段、
    未知模型、ask 不下、auto 也不下 484MB、auto 下 10MB、confirm 覆盖 ask、模式解析、
    `install_dir` 与读取端一致）。
  - **真下了一次**：`VIDLENS_TAGGING_DIR=D:\vidlens\ced-download-test` + `confirm=True`
    → 10.0MB / 52.3s（先试 huggingface.co，失败自动换 hf-mirror），下完 `ae.available()`
    立刻为 True、`model_paths()` 指向该目录（装与读同一个函数，不会各说各话）。
  - 插件自检 128/128。
- **没做（并说明原因）**：SenseVoice（937MB，且需要 tokens.txt）只给说明不代下；whisper 的
  484MB 真下没在本机跑（会把仓库体积翻倍），但路径与 gating 都有测试覆盖。
- **状态**：已完成。

---

## 2026-10-26 去掉发布物里的本机路径（V-013）

- **触发**：用户看完 OCR 安装提示后问「人家怎么能跟我的环境一样呢？我怕你都有死代码」。
  这个质疑成立——提示里是运行时算出来的路径，但**代码里确实有本机路径**。
- **事实（逐条 grep + pyflakes）**：
  - `vidlens_models`：`r"D:\dev\models" if Path("D:/").exists()` —— 判据是"有没有 D 盘"，
    于是任何有 D 盘的机器都会被导向这个目录（不是我的机器，是不认识的人）。
  - `vidlens_sensevoice`：`C:\Users\<本人>\AppData\Roaming\com.flashvoices\...` 写死在源码里。
  - `index.js`：回退列表里带 `D:\vidlens\vidlens`。
  - 死代码：`vidlens.py` 里赋值未用的 `n` 与 `import array`；`vidlens_web.py` 里未用的
    `contextlib`、`shutil`；`vidlens_extra.py` 一处无占位符的 f-string；
    `vidlens_ocr.install(auto=...)` 的 `auto` 参数从头到尾没用，`video_ocr` 里还有一句
    死赋值 `ok = True`。
- **改动**：
  - 新增 `vidlens.models_root()`：`VIDLENS_MODEL_ROOT` → **legacy 目录仅当它真的存在** →
    按用户数据目录（Windows `%LOCALAPPDATA%\vidlens\models`，POSIX XDG）。whisper /
    audio-tagging / SenseVoice 三处统一走它；SenseVoice 改成候选列表探测（不再带用户名，
    FlashVoice 那份从 `%APPDATA%` 现算）。
  - `_model_dirs()` 只在 `plat == "nt"` 且 legacy 存在时才把 D 盘当候选；被问"POSIX 怎么算"
    时返回 POSIX 的答案，而不是本进程解析出来的值。
  - 插件回退删掉 `D:\vidlens\vidlens`（config → env → 同级仓库）。
  - OCR 换目录示例按目标盘符现算：C 盘机器给 `C:\vidlens\ocr`，不再给 D:。
  - 删除上述 4 处死代码 + `install()` 的无用参数 + 死赋值。
- **验证**：
  - `Ran 184 tests ... OK (skipped=1)`（新增 `NoPersonalPathsTests` 3 项；
    `ModelDirTests` 从"Windows 必须优先 D 盘"改成"legacy 只在存在时才是候选"）。
  - 现场演示：本机 `models_root -> D:\dev\models`（legacy 存在，行为不变）；把 legacy 换成
    不存在的路径 + `LOCALAPPDATA=C:\Users\someone\AppData\Local` 后
    `models_root -> C:\Users\someone\AppData\Local\vidlens\models`；设
    `VIDLENS_OCR_TARGET=C:\vidlens\ocr` 后提示里的示例同步变成 C:。
  - `pyflakes` 只剩 3 处 `# noqa: F401` 的可用性探测导入。
  - 插件自检 **128/128**（新增 "no personal paths baked into the shipped code"）。
- **状态**：已完成。

---

## 2026-10-26 内置本地 OCR（V-012）

- **目标**：三个测试视频里有 **2 个没有人声**（BV14Rnm6YEch 全程画面字幕、BV165Jv6EEbh 连字都没有），
  当时唯一的办法是下整片最低画质、让模型逐帧看图猜字。要把「画面上的字」变成可引用的文本。
- **事实（先查许可证再动手）**：
  - [Umi-OCR](https://github.com/hiroi-sora/Umi-OCR)：**MIT**，48k stars，Qt 桌面程序 + 可换引擎。
    价值在「离线 + 多引擎 + 批量」的做法，不在代码；整包 100MB+，不适合当 pip 依赖。
  - [RapidOCR](https://github.com/RapidAI/RapidOCR)：**Apache-2.0**，8.3k stars，纯 Python + ONNX Runtime；
    wheel 27.3MB，**PP-OCRv6 det/rec/cls 模型随包分发**（9.5+20.3+0.6MB），装完即离线、运行时不下载。
    依赖 pyclipper / opencv-python-headless / shapely / omegaconf，都是宽松许可证。
    模型权重版权归百度 / PaddleOCR 权利方，Apache-2.0，出处记在上游 `MODEL_LICENSES.md`。
  - 生态里同类做法有先例：`AB498/computer-control-mcp`（MIT）就是 RapidOCR + onnxruntime。
  - 本机 `onnxruntime 1.31.0` 已存在（sherpa-onnx 带），所以实际只新增 ~30MB 的引擎与模型。
- **改动**：
  - 新增 `vidlens_ocr.py`（约 170 行，懒加载）：`available()` / `ocr_image()` / `ocr_frames()` /
    `merge_captions()` / `overlay_texts()` / `looks_like_diagram()` / `timestamps()`。
  - 新增工具 `video_ocr(url, start, end, n=12, width=1280)`（MCP 第 18 个、插件第 21 个）：
    只下这段最低画质（720p 起步，480p 会把小字糊掉），n 帧识别，输出带时间码的字幕 + 全文。
  - 三条清洗规则，都是实测撞出来的：
    ① **静态叠加层**：同一短串出现在 ≥40% 帧 → 判为水印/固定 UI（实测「折光AI1996 bilibili」重复 8 次）；
    ② **图表帧**：一帧 ≥6 个文字框且中文字符占比 <45% → 归到「图表/界面文字」，不并入字幕
       （实测 Transformer 结构图吐出 Softmax/Add & Norm 等 15 个标签），但其中中文句子仍会捞回字幕；
    ③ **平台名**：短行里出现 bilibili/抖音/快手… 即水印；长句提到不算。
  - 接入提示：`_digest` 与 `brief.md` 在「几乎无人声」处先指向 `video_ocr`，再指向 `video_visual_scan`。
  - `vidlens_doctor` 多一行 `ocr (optional, screen text)`；**未装不算失败**（多数视频有人声，用不到）。
- **验证**：
  - `Ran 170 tests ... OK (skipped=1)`（新增 `tests/test_ocr.py` 20 项：懒加载、水印/叠加层、合并、
    图表帧、时间点、许可证登记）。
  - 真机：`video_ocr(BV14Rnm6YEch, n=12)` → 46.6s（下载+识别）、≈1.3k tokens、16 条字幕，
    内容与人工看拼图的读数一致（「全世界有195个主权国家 / 剩下的193个都在干嘛 / 瑞士的模型叫 Apertus /
    15个国家共同推出了 Latam-GPT」）。清洗后 51 段 → 16 条，水印 0 条。
  - 插件自检 127/127（新增工具被发现）。
- **许可证**：`NOTICE.md` 新增 RapidOCR / PP-OCRv6 / ONNX Runtime / OpenCV 四行，并在「设计借鉴」
  里写明与 Umi-OCR 的关系（只借做法，未复制代码）；`pyproject` 增 `ocr` extra。
- **状态**：已完成。

---

## 2026-10-26 外部 AI 实测反馈修复（V-011）

- **目标**：另一个模型用 v1.4.0 的 MCP 实测两个视频（一个 9:26 的语音视频、一个 3:30
  的纯音乐视频），反馈里指出的是**工具层的真问题**，不是模型措辞。逐条核实后修掉。
- **事实（先复现再改）**：
  - `out/BV1VtnX64ERM/transcript.jsonl` 11 行、`text` 全是「。」「哎。」，`track` 仍是
    `speech`；而 `build_brief` 的 `has_speech = any(text.strip())` 对「。」为真 →
    「语音覆盖 100%」，`_digest` 同样用 `strip()` 累加窗口时长 → 100%。
  - `_digest` 的 5 句是 `dur*(i+0.5)/5` 取最近行，纯时间等距；实测该视频 07:20 的
    结论句不在任何取样点上。
  - `visual_scan` 的拼图 338,531B，`Image(path=...)` 在 MCP 层就是 base64，≈45 万字符。
  - 结果里没有 token 估算；`video_meta` 75,336 与 `brief.md` 73,595 并存且无时间戳。
- **改动**：
  - `vidlens.speech_chars()`：去标点/空白后计有效字数；`build_brief` / `_digest` /
    `video_window` / `video_watch` 全改用它。
  - 无人声分支：digest 出「**⚠ 几乎无人声**（N 个窗口只有填充词/音乐，有效台词 0 字）」
    并指向 `video_visual_scan`；brief 出「未识别到语音」；转写区在无有效台词时只写一行
    说明，不再打印一串「。」。
  - `_pick_lines()`：章节收尾句 → 转折/结论词（但是/然而/总之/因此/问题在于…）→ 均匀补点，
    标题写明「不是全文证据」。
  - `_image_blocks()` + `VIDLENS_INLINE_IMAGES=auto|always|never`：auto 只内联 ≤200KB，
    其余留盘并给绝对路径；桥进程设 `always`（它把 Image 转成文件路径，不付 base64）。
  - `_cost()`：每个重结果末尾 `[成本] ≈N tok（估算）`，计入 digest 的 1600 字预算。
  - 缓存 meta 记 `_fetched_at`，brief 来源块输出「抓取于 …（播放/点赞是那一刻的快照）」。
  - `need_login_subtitle` 的提示改成可操作建议（cookies → 0 下载取字幕，比 ASR 准）。
- **验证**：
  - 全量 `Ran 150 tests ... OK (skipped=1)`（新增 14 项：NoSpeech / DigestSampling /
    InlineImage / MetaSnapshot / CostLine）。
  - 同一份缓存重算：BV1VtnX64ERM 现在输出「几乎无人声 / 台词 0 字」（574 字摘要）；
    BV1DxH366EhS 的输出新增 07:00「总之…」转折句（旧版 5 句里没有）。
  - 插件自检 122/122。
- **未做（记录在案）**：ASR 置信度仍是模型侧的空白（SenseVoice 不给逐词置信；
  brief 里已有「低置信词」段，digest 只加了一句免责）；`视频画面默认不看` 仍是默认，
  由覆盖行如实声明，不改默认路线。
- **状态**：已完成。

---

## 2026-10-26 awesome-dsh-plugin 收录 PR 转绿（V-010）

- **目标**：把条目合进 `awesome-dsh-plugin`（dsh-market / Discover 的数据源），
  确认「仓库满 1 天」这条硬门槛不会再卡住。
- **事实（先查后做）**：
  - gate 的红来自 `repository is 0.3 days old (needs 1)`，它的提示说「会自己重跑，
    约 18h 后清掉」——**这句偏乐观**：自助复查 `regate.yml` 是 `cron: 19 */6 * * *`
    （每 6 小时一轮），而且对 age 类失败有 **24h 冷却**（`ranAt + 24h`）。gate 跑在
    2026-10-25T14:35Z，所以最早能重跑的是 2026-10-26T20:19Z，不是 18h 后的 08:3xZ。
  - `regate.yml` 每轮 `MAX_RERUNS=20`、blocking 队列按 PR 号升序；本仓库每分钟都在进
    PR（同时开着的 ~100+），#9422 排在队尾，可能还要等好几天。
  - 我们不是该仓库协作者：`POST /actions/runs/<id>/rerun` 返回
    `403 Must have admin rights to Repository` —— 手动重跑这条路对 fork 作者不通。
  - 唯一可用的触发是给 PR 一个新事件：`pr-check.yml` 的 `on: pull_request`（默认含
    `reopened`），close+reopen 会重算 merge commit 并重跑 `PR check`，其完成事件再经
    `workflow_run` 拉起 `Submission gate`。
- **改动**：close（08:41:05Z）→ reopen（08:41:08Z）。没有 push、没有改条目。
- **验证**：
  - 新 `PR check` run 40293989025 起于 08:41:12Z，08:54:14Z **success**；
  - 新 `Submission gate` check run 121480730655 08:54:48Z **success**，
    结论原文 `Entries look good` / `All 1 submitted entry passes: dsh.bundle declared,
    repo old enough, enough commits.`；
  - PR：`state=open mergeable=True mergeable_state=clean changed_files=1`（只动
    `data/plugins/cctv2333__dsh-vidlens.yml`）。
- **顺带确认**：README 是**生成物**——合并进 main 后 `sync-readme.yml`（`on: push` 到
  `data/plugins/**`）自动重生成中英两份并提交；贡献者自己提交重生成也接受，但
  **不要手工改 README**（两仓同时改同一批生成行正是这个列表之前 218/296 冲突的原因）。
- **状态**：已完成（等维护者合并）。

---

## 2026-10-25 PyPI 打包 + 跨进程锁 + 两仓库拆分（V-008）

- **目标**：① 让 MCP 能 `pipx install` 而不是 clone；② 修掉多进程争 `out/` 的并发 bug；
  ③ 按「工程 / DSH 插件」拆两个公开仓库。
- **改动**：
  - `pyproject.toml`（setuptools，flat `py-modules` 10 个）；入口
    `vidlens = vidlens:main`、`vidlens-mcp = vl_mcp:main`；extras
    `sensevoice` / `whisper` / `audioevents` / `all`。
  - `vidlens.project_root()`：源码布局保持工程目录；wheel 安装后用
    `%LOCALAPPDATA%\vidlens`（POSIX `~/.local/share/vidlens`）。`out_root()` /
    `ffmpeg_dir()` 都改走它 —— 装成 wheel 不再往 site-packages 写数据。
  - `vidlens_web.CrossProcessLock` + `media_lock()`：进程内 RLock + 一个机器级文件锁
    （`out/.media.lock`，Windows `msvcrt` / POSIX `flock`，超时 `VIDLENS_LOCK_TIMEOUT`）。
    `vl_mcp._MEDIA_LOCK` 换成它；`video_comments` 补上媒体锁。
  - `tests/test_lock.py`（3 项）+ `tests/test_audioevents.py`（7 项）。
  - README 安装段改为「PyPI 优先，源码次之」；LICENSE 相关表述统一为 MIT。
  - 仓库拆分：`cctv2333/vidlens`（本仓库，Python + MCP）与
    `cctv2333/dsh-vidlens`（DSH 插件，18 工具）。
- **验证**：
  - `uv build --wheel` 成功，wheel 含 10 个模块 + `LICENSE`/`NOTICE.md` + 两个 console script；
  - 装到临时 target 后从空目录导入：`project_root = C:\Users\yu\AppData\Local\vidlens`，
    `out_root` / `ffmpeg_dir` 都落在用户目录，16 个 MCP 工具可加载；
  - 锁：3 项单测通过；两进程真实 `video_sheet` 实测串行（proc1 acq 4.66s→end 17.76s，
    proc0 acq 17.95s→end 30.47s）；
  - 全量 `Ran 104 tests ... OK (skipped=1)`。
- **状态**：已完成

---

## 2026-10-25 声音事件接入（V-007）

- **目标**：识别台词之外的声音——吃饭/咀嚼、敲桌子、水声、碰撞、拖拽；带时间码与概率。
- **事实（先查后做）**：
  - 本机 `sherpa_onnx 2.0.0` 自带 `AudioTagging`，且 `AudioTaggingModelConfig(ced=...)`
    可用（`ced` 是真字段，只是不在 `dir()` 里列出）；
  - 模型 `k2-fsa/sherpa-onnx-ced-mini-audio-tagging-2024-04-19`：
    `model.int8.onnx` 10,451,715B + `class_labels_indices.csv` 14,675B（Apache-2.0）；
  - AudioSet 527 类里**有** `Chewing, mastication`(#54)、`Knock`(#359)、`Tap`(#360)、
    `Wood block`(#173)、`Water`(#288)、`Water tap`(#370)、`Chink, clink`(#442)、
    `Scrape`(#475)、`Crumpling, crinkling`(#479)；
    **没有** Drinking/Sip/Gulp —— 喝水/吞咽只能靠水声 + 画面推断。
- **改动**：
  - 新增 `vidlens_audioevents.py`（懒加载、10s 窗/5s 跳、按 hop 合并成段、锁串行）；
  - `vl_mcp.py` 新增 `video_soundscape`（MCP 第 16 个工具）；
  - `vidlens_models.py` 的 ced-mini 行改为「已装/已接」，`available()` 走
    `VIDLENS_TAGGING_*` / `VIDLENS_MODEL_ROOT`；
  - `tests/test_mcp.py` 工具清单加 `video_soundscape`；新增 `tests/test_audioevents.py`（7 项）；
  - 插件侧（`D:\vidlens\vidlens-mcp-dsh`）：`vidlens_soundscape` 工具 + 桥分发 + 下载脚本；
  - 工程新增 `LICENSE`（MIT）。
- **验证**：
  - `Ran 101 tests ... OK (skipped=1)`；
  - 加载 0.14s；28.4s 音频推理 43ms；
  - 合成三下敲击 → `Wood block 0.18 / Drum 0.17 / Music 0.23`；
    水声噪声 → `Waterfall 0.17 / Stream 0.08`；静音 → `Silence 0.53`；
  - 真实视频 01:00–01:45 → `Music 0.89 / Speech 0.88 / Speech synthesizer 0.32`，与画面一致；
  - 插件端到端：`vidlens_soundscape` 返回逐窗 + 段 + 「怎么读」，105/105 自检通过。
- **限制**：概率整体偏低（AudioSet 多标签），>0.30 才当真；喝水/吞咽无类；
  声音事件暂未写进 `brief.md`（独立工具，按需调用）。
- **状态**：已完成

---

## 2026-10-25 工程交接与可分发包（V-006）

- **目标**：让下一位 AI/人不用重新摸索；评估并实际构建可分发包。
- **产出**：
  - `HANDOVER.md` + `handover/README.md`（入口）
  - `handover/ARCHITECTURE.md`（模块/数据流/锁/缓存/失败模式）
  - `handover/MODELS.md`（模型/非模型能力、体积、许可证、下载政策）
  - `handover/DISTRIBUTION.md`（分发清单、排除项、换机步骤）
  - `handover/ARCHIVE.md`（档案/验证/日志索引）
  - `handover/REPRODUCE.md`（复现命令）
  - `dist/vidlens-src-20261025.zip`（大小/HASH 见外部 `dist/SHA256SUMS.txt`，
    避免 zip 内自指）
- **验证**：zip 解压到临时目录后 `Ran 94 tests ... OK (skipped=1)`；
  包内无 `out/`、`.venv/`、`bin/`、`mcp.json`、模型权重、`__pycache__`。
- **状态**：已完成
- **分发限制**：仓库暂无 LICENSE（需项目所有者选；V-008 已定为 MIT）；模型权重不随包；
  Windows 优先；B 站 AI 字幕/抖音需要用户自己的 cookie。

---

## 2026-10-25 B站字幕/音乐元数据与模型目录（V-005）

- **目标**：测试用户给的 AI 字幕视频；接入平台 BGM 元数据；回答轻量模型/CED-mini/AcoustID。
- **事实**：
  - `BV1AxJ16QEeM` 的 `player/wbi/v2` 返回 `need_login_subtitle=true`、`login_mid=0`，
    匿名 `subtitles=[]`；AI 字幕存在，但需要登录态。
  - `BV1PvHX61EgV` 的 `bgm_info` 返回
    《Macarena (River Re-Mix 103 BPM)》+ music.bilibili.com 链接。
  - CED-mini：9,696,783 参数、usedStorage 49.7MB、Apache-2.0、AudioSet 音频分类，
    含 ONNX；**不是 ASR**。
  - AcoustID：Chromaprint 指纹检索，需 `fpcalc` + client API key，3 req/s、非商业；
    返回 MusicBrainz 记录，不是“听懂音乐”。
- **改动**：
  - `fetch_meta` 增加 B 站 `bgm_info` / `need_login_subtitle` / 简介音乐线索。
  - `video_meta` 显示平台音乐、音乐链接、字幕登录门槛。
  - `build_brief` 增加「音乐信息」章节；`video_audio` 带平台标注音乐。
  - 新增 `vidlens_models.py` + MCP `vidlens_models` + CLI `vl models`：
    模型目录/硬件建议，**只读、不自动下载**。
- **验证**：
  - `Ran 94 tests ... OK (skipped=1)`；`doctor 11/11`。
  - `video_meta(BV1PvHX61EgV)` 实测输出
    `平台音乐: Macarena (River Re-Mix 103 BPM)`。
  - `vl models --recommend`：`ram=14.9GB cpu=16cores recommended_asr=sensevoice`。
  - `video_audio(BV1PvHX61EgV 00:00-00:20)` 同时显示平台音乐 + `Speech` + 96.2 BPM。
- **状态**：已完成
- **待办**：AI 字幕正例需要登录 cookie；Edge 正在运行导致 cookie 库被锁，需用户关闭 Edge
  或导出 cookies.txt 后再测。CED-mini 未接（不是 ASR）；AcoustID 未接（需 fpcalc/key）。

---

## 2026-10-25 本地 ASR 复用与音频理解调研（V-004）

- **目标**：① 阻止每次新对话/新进程重复联网检查模型；② 评估并用上用户已有的
  `C:\Users\yu\AppData\Roaming\com.flashvoices\models\sense-voice-large.onnx`；
  ③ 调研音频情感/事件/节拍能力；④ 记录 B 站 AI 字幕限制。
- **事实**：Whisper small 权重 483.5MB 已在 `D:\dev\models\whisper`；新进程只是向
  HF 查版本（日志里的 GET），不是重下。SenseVoice 文件 937.6MB = 官方 float32
  `model.onnx`（894MiB），元数据 `sense_voice_ctc`、vocab 25055、`iic/SenseVoiceSmall`。
- **方案/改动**：
  - `vidlens_web.transcribe`：`VIDLENS_ASR=auto|sensevoice|whisper`；SenseVoice 优先，
    不可用回退 Whisper；Whisper 先 `local_files_only=True`，缓存缺失才联网。
  - 新增 `vidlens_sensevoice.py`：复用 FlashVoice 的 937MB ONNX + 308KB 词表，
    分块 ASR，返回 text/lang/emotion/event/timestamps。
  - 新增 `vidlens_audio.py`：numpy 频谱通量 + 自相关，估计 BPM/能量/动态/静音。
  - 新增 MCP `video_audio`：只听一段，返回语种/情感/事件/节拍/能量。
  - `build_brief` 增加「声音信号」章节；BGM 与语音并存时注明。
  - `DEFAULT_SUB_LANGS` 增加 `ai-zh,ai-en,ai-*`，覆盖 B 站 AI 字幕命名。
  - requirements 增加 `sherpa-onnx>=2.0.0,<3`。
- **验证**：
  - `Ran 91 tests ... OK (skipped=1)`。
  - SenseVoice：加载 1.54s，28.4s 音频解码 0.53s；输出 `zh/NEUTRAL/Speech`。
  - 音乐段 `video_audio`：`<|BGM|>`，125.0 BPM，20.4s。
  - 口播段 `video_audio`：`zh/NEUTRAL`，文本可用；对 Claude/Haiku 等英文专名仍会错。
  - 合成 120 BPM 点击轨 → 121.0 BPM；真实 BGM → 125 BPM。
  - Whisper `local_files_only=True`：加载 1.68s，不联网；`info.local_files_only=True`。
  - B 站匿名 `player/v2` 三个样本 `subtitle.subtitles=[]`；AI 字幕需登录 cookie。
- **状态**：已完成（研究 + 实装 + 实测）
- **限制**：SenseVoice 对英文品牌名/专名不如 Whisper；情感/事件/节拍是启发式，
  不当作事实；B 站 AI 字幕正例未拿到（无登录态）。

---

## 2026-10-25 硬编码审计与能力验收（V-003）

- **目标**：回答“有没有硬编码/魔法数字”；验证字幕、方言、默认抽样策略。
- **改动**：`HARDCODE_AUDIT.md`（AST 扫描 + 人工分类）；`vidlens_ads.py` 的 `毫光`→`毫克`；
  README 增补 cookie / 方言 / 默认抽样说明。
- **验证**：`Ran 90 tests ... OK (skipped=1)`；`doctor 11/11 ok`；
  真实 e2e：
  - 40 分钟无切点视频 → `video_plan` 8 个 5 分钟章节（修复了“整片 1 章”）；
  - 无缓存长视频 `video_brief` → 3.7s 返回抽样计划，out 目录 0 文件；
  - 无缓存 `video_window(02:00–02:20)` → 28.2s，只转写 20 秒，时间码 02:00 起，临时目录已清；
  - 有缓存 40 分钟视频 → `video_brief` 3.4s，含「分步看」，来源 `asr(cached)`；
  - `video_subs` 实际调用 yt-dlp，B 站匿名无 CC 时明确返回“没有可用字幕”。
- **状态**：已完成
- **限制**：B 站匿名通常只给 danmaku，不给 CC；正片字幕需 cookie/登录态，已提供 env 入口。

---

## 2026-10-25 审计 P1/P2 修复（V-002）

- **目标**：修掉审计报告里已核实的 P1/P2 问题；补字幕/方言能力；把“默认抽样、按需全量”写进工具行为与说明。
- **验收标准**：新增/修改行为有单测；全量测试绿；真实 MCP 握手与至少一条真实视频链路可用；`video_subs`/`video_plan` 可用；文档与行为一致。
- **排除项**：不部署本地大模型、不调云 API；不做爬虫/白名单；不改用户已有产物；不自动提交。
- **方案**：分批小步改，每批跑相关测试；先做字幕与默认抽样（主矛盾），再做锁/缓存/边界与魔法数字。
- **回退点**：每批改动前记录文件；若测试失败，回退该批。
- **改动**：
  - `vidlens_web.py`：`DEFAULT_SUB_LANGS`/`sub_langs_for`、cookie env + 报错提示、`media_duration`/音频完整性校验、`download_audio_section`、`subs/` 隔离目录、`plan_chapters` 长空洞兜底网格、展示上限常量。
  - `vl_mcp.py`：字幕优先 `_rows_with_media`、`video_subs`、`video_plan`、长视频默认抽样、`_MEDIA_LOCK`/`_JOB_LOCK`/同 URL job 去重、行级 `S.scan`、唯一临时目录、负时间夹紧、命名常量、删除 `quiet()` 死代码。
  - `vidlens_extra.py`：`plan(meta=)`、visual_scan 清理抽帧、命名常量。
  - `vidlens_ads.py`：`毫光` → `毫克`。
  - `requirements.txt`：`av>=11,<19`。
  - `tools/manual/`：归档 `_meta3.py`、`_run_three.ps1`。
  - `README.md`：13 个工具、字幕/方言、默认抽样、cookie、锁说明。
  - `tests/test_features.py`（18 项）+ `tests/test_plan.py`（10 项）。
- **验证**：`Ran 90 tests ... OK (skipped=1)`；`doctor 11/11 ok`；真实 MCP e2e 见 V-003。
- **状态**：已完成
- **待办**：无（P3 的可调阈值集中化见 `HARDCODE_AUDIT.md`，等用户明确再动）

---

## 2026-10-25 plan() / pauses.json 双形态崩溃修复（V-001）

- **目标**：修掉 `plan()` 在 CLI 形态 `{"threshold_db":...,"gaps":[...]}` 下抛 `AttributeError`，以及 `_do_brief` 静默吞异常。
- **验收标准**：两种 pauses.json 形态都能出章节；`_do_brief` 不再调用 `plan()`；真实 MCP job 可复现修复。
- **方案**：`vidlens_web.read_pauses()` 统一读取；`plan_chapters()` 抽出共用；`build_brief(chapters=)` 把「分步看」放在「结构」之后；同步/异步 brief 都补章节。
- **改动**：`vidlens_web.py`、`vidlens_extra.py`、`vl_mcp.py`、`tests/test_plan.py`、`README.md`。
- **验证**：`Ran 69 tests ... OK (skipped=1)`；真实 MCP job（临时字典形态缓存）输出 `HAS_PLAN_SECTION: True`、`HAS_ERROR: False`；证据 `out/plan_bug_evidence.md`。
- **状态**：已完成
- **回退点**：`out/plan_bug_evidence.md` 记录了改动点；缓存已恢复原样。
visual_scan 清理抽帧、命名常量。
  - `vidlens_ads.py`：`毫光` → `毫克`。
  - `requirements.txt`：`av>=11,<19`。
  - `tools/manual/`：归档 `_meta3.py`、`_run_three.ps1`。
  - `README.md`：13 个工具、字幕/方言、默认抽样、cookie、锁说明。
  - `tests/test_features.py`（18 项）+ `tests/test_plan.py`（10 项）。
- **验证**：`Ran 90 tests ... OK (skipped=1)`；`doctor 11/11 ok`；真实 MCP e2e 见 V-003。
- **状态**：已完成
- **待办**：无（P3 的可调阈值集中化见 `HARDCODE_AUDIT.md`，等用户明确再动）

---

## 2026-10-25 plan() / pauses.json 双形态崩溃修复（V-001）

- **目标**：修掉 `plan()` 在 CLI 形态 `{"threshold_db":...,"gaps":[...]}` 下抛 `AttributeError`，以及 `_do_brief` 静默吞异常。
- **验收标准**：两种 pauses.json 形态都能出章节；`_do_brief` 不再调用 `plan()`；真实 MCP job 可复现修复。
- **方案**：`vidlens_web.read_pauses()` 统一读取；`plan_chapters()` 抽出共用；`build_brief(chapters=)` 把「分步看」放在「结构」之后；同步/异步 brief 都补章节。
- **改动**：`vidlens_web.py`、`vidlens_extra.py`、`vl_mcp.py`、`tests/test_plan.py`、`README.md`。
- **验证**：`Ran 69 tests ... OK (skipped=1)`；真实 MCP job（临时字典形态缓存）输出 `HAS_PLAN_SECTION: True`、`HAS_ERROR: False`；证据 `out/plan_bug_evidence.md`。
- **状态**：已完成
- **回退点**：`out/plan_bug_evidence.md` 记录了改动点；缓存已恢复原样。

---

## 2026-10-26 上下文预算与工具调用治理（V-009）

- **目标**：解决「看一个视频就把模型上下文顶爆」。起因是一次真实会话：一轮内 4 个调用
  （meta / brief / comments / sheet），brief 9k 字在客户端出现两次，评论还带 4 张 base64 图。
- **改动**：
  - `vl_mcp`：`video_brief(level="digest"|"full")` 默认 digest（≤1.6k 字）；`video_watch`
    分段推进（每段 ≤1.2k 字、带进度、游标 per-session）；`video_window` 80 行上限；
    `video_comments(with_images=False)`；16 个工具 `structured_output=False`（去掉重复）；
    `_fit()` 截断保尾；`level` 校验提前到入口。
  - 插件：per-Agent 预算台账（12k 提示 / 24k 硬钳：brief 强制 digest、watch ≤5 分钟、
    评论禁图）；`vidlens_budget` 查询；相同参数调用去重 + 失败短路；提示词改为
    「默认粗看一次答完，细看才分段」；schema 8,590 → 6,768 字符。
  - 实测：单视频上下文从 ~14.2k 字符降到 ~5.8k；digest 741 字 vs full 9,052 字；
    watch 每段 491–522 字。
- **验证**：136 项测试、122 项插件自检、CI（ubuntu/windows × py3.10/3.12）全绿。
- **待办**：schema 仍可再降（要删参数）；失败 memo 的 20 分钟窗口可能挡住网络恢复后的重试；
  没有 dsh-ops 那种「证明上次正文确实在上下文里」的证据机制（见 HANDOVER）。
