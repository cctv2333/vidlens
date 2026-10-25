# NOTICE — 第三方归属与许可证

本仓库**没有复制任何外部项目的源代码**。设计上借鉴了下列公开项目的**思路**（机制、接口划分、提示），
按开源惯例在此致谢。若将来真的复制代码，必须在本文件登记「文件路径 / 上游仓库 / 许可证 / 作者」。

## 一、运行时依赖（以包形式使用，未修改）

| 依赖 | 许可证 | 用途 | 备注 |
|---|---|---|---|
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Unlicense（公共领域） | 抓取公开视频/字幕 | 通过 `python -m yt_dlp` 调用，未修改 |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | MIT | 语音转文字（CPU） | 仅调用其 Python API |
| [CTranslate2](https://github.com/OpenNMT/CTranslate2) | MIT | faster-whisper 推理后端 | 间接依赖 |
| [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) | Apache-2.0 | SenseVoice ONNX 推理与 CTC 解码 | 通过 Python 包调用，未修改 |
| [SenseVoice 模型](https://github.com/FunAudioLLM/SenseVoice) | 见上游（iic/SenseVoiceSmall） | 语音识别/语种/情感/事件 | 用户本机已有，未随仓库分发；许可证以上游为准 |
| [SenseVoice tokens.txt](https://hf-mirror.com/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17) | 随 sherpa-onnx 模型包 | 25,055 行词表 | 308KB，未修改，存放于 `D:\dev\models\sensevoice` |
| [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) | BSD-2-Clause | 提供 ffmpeg 可执行文件 | 该包内附带的 ffmpeg 构建受 **LGPL/GPL** 约束；仅作为独立进程调用，不链接进本程序 |
| [Whisper 模型权重](https://huggingface.co/Systran/faster-whisper-small) | MIT（OpenAI Whisper） | 语音模型 | 下载至 `D:\dev\models\whisper` |
| Python 标准库 | PSF | 其余全部 | — |

**关于 ffmpeg 的许可证**：本程序以子进程方式调用 ffmpeg，不与之链接，因此本程序自身的许可证不受其 GPL 传染。
但若**再分发**包含 ffmpeg 二进制的整包，需遵守 ffmpeg 的 LGPL/GPL 条款（提供许可证文本与源码获取方式）。

## 二、设计借鉴（仅思路，无代码）

| 项目 | 许可证 | 借鉴了什么 |
|---|---|---|
| [OAMaestro/video-vision-mcp](https://github.com/OAMaestro/video-vision-mcp) | MIT | ①按场景切点取样而非固定间隔；②把时间码烧进画面；③字幕优先于 ASR |
| [coah80/youtube-mcp](https://github.com/coah80/youtube-mcp) | MIT | ①帧与台词按时间交织的表征；②控制喂给模型的帧数以控制 token |
| [JazerJu/video-miner](https://github.com/JazerJu/video-miner) | **无许可证**（保留所有权利） | 仅借鉴其 MCP 工具契约的划分方式；**未使用其任何代码，也不再依赖其行为** |
| [Breakthrough/PySceneDetect](https://github.com/Breakthrough/PySceneDetect) | BSD-3-Clause | 场景切分的思想（本实现改用 ffmpeg `scene` 分数，未引入其库） |

> 说明：`video-miner` 仓库未提供开源许可证，因此**不能复制其代码**，只能阅读其公开文档并借鉴思路。
> 这一点在评估时已明确记录。

## 三、被明确拒绝的做法

- 不绕过登录墙、付费墙、验证码。
- 不冒充已登录用户（不使用浏览器 cookie，除非用户显式指定 `--cookies-from-browser`）。
- 不做批量爬取（一次调用只处理一个视频），请求间强制 sleep。
- 不把外部文本当指令执行（见 `vidlens_sanitize.py`）。
