# 模型与“非模型”能力清单

## 1. 本工程已用/已登记

| 名称 | 体积 | 能力 | 状态 | 备注 |
|---|---|---|---|---|
| SenseVoice（FlashVoice ONNX） | 937MB | ASR + 语种 + 情感 + 音频事件 | **默认** | 本机已有；sherpa-onnx 加载 1.5s |
| SenseVoice int8 | 228MB | 同上 | 未下载 | 弱机/省磁盘可选；env 指过去即可 |
| faster-whisper small | 484MB | ASR | 回退 | 中文偏繁体；专名也需核对 |
| faster-whisper tiny | 75MB | ASR | 未下载 | 弱机应急 |
| CED-mini（k2-fsa sherpa 版 int8） | 10.4MB | AudioSet 527 类声音事件 | **已接**（V-007） | sherpa-onnx `AudioTagging`；标签表 14.7KB；加载 0.14s；**不是 ASR** |
| AcoustID | — | 音频指纹检索 | 未接 | 需 fpcalc + API key；检索库，不是模型 |

## 2. 还可以关注的开源模型

| 模型 | 用途 | 体积/门槛 | 备注 |
|---|---|---|---|
| Paraformer / Zipformer（sherpa-onnx） | 中文 ASR | 数十–数百 MB | 中文强、CPU 友好；需另测 |
| FireRedASR2（sherpa-onnx 模型列表） | 中英/粤语/四川/上海等 | 需查具体包 | 方言场景可评估；未安装 |
| Moonshine | 英文 ASR | 小 | 英文短音频；中文非强项 |
| PANNs / AST / BEATs | 音频事件/声学场景 | 数十–数百 MB | 比 CED-mini 重；事件分类 |
| emotion2vec / SER 模型 | 语音情感 | 中等 | SenseVoice 已给情感标签，暂不必要 |
| Qwen2-Audio / Qwen3-ASR | 音频理解/ASR | 大 | 与“不要大模型”冲突，仅备选 |

> 原则：**先平台字幕/元数据，再小模型；不要为了模型而模型。**

## 2.5 怎么在 HuggingFace 上找（避免踩坑）

1. 先按任务过滤：`pipeline_tag=automatic-speech-recognition`（ASR）或
   `audio-classification`（声音事件/情感）。
2. 看体积：模型页 API 的 `safetensors.total` / `usedStorage` 比 README 的“小模型”口号可靠。
3. 看是否有 `model.onnx`；没有 ONNX 就要自己导出（PyTorch→ONNX），多一层风险。
4. 看许可证和是否 gated；不要下载需要 `trust_remote_code` 的未知自定义代码。
5. 优先选 **sherpa-onnx 已支持的架构**（SenseVoice / Paraformer / Zipformer / Whisper /
   FireRedASR2 等），这样只需 `model.onnx + tokens.txt`，不用装 torch。
6. 音频分类模型（CED-mini 等）还要确认：采样率、mel 前端、标签表、输出维度。

常用入口：

- `https://hf-mirror.com/models?pipeline_tag=automatic-speech-recognition`
- `https://hf-mirror.com/models?pipeline_tag=audio-classification`
- `https://k2-fsa.github.io/sherpa/onnx/pretrained_models/index.html`

## 3. 不通过模型也能做的

| 能力 | 来源 | 状态 |
|---|---|---|
| 平台字幕（含 B 站 AI 字幕） | yt-dlp `subtitles` / `automatic_captions` | 已做；AI 字幕需登录 cookie |
| 平台 BGM 歌名 | B 站 `player/wbi/v2` `bgm_info` | 已接 `video_meta/brief/audio` |
| 简介音乐线索 | `BGM：`、`配乐：`、`《…》` 正则 | 已接 |
| 章节/切点 | B 站 chapters + ffmpeg scene | 已做 |
| 静音/停顿 | ffmpeg `silencedetect` | 已做 |
| 节拍/能量 | numpy 频谱通量 + 自相关 | 已做（近似） |
| 听音识曲 | AcoustID/Chromaprint | 未接；平台元数据优先 |
| 画面硬字幕 | 取帧后由 LLM 自己看 | 已做（`video_frames`） |

## 4. 本机实测

| 输入 | 加载 | 解码/分析 | 输出 |
|---|---|---|---|
| 28.4s 会议语音（SenseVoice） | 1.54s | 0.53s | `zh / NEUTRAL / Speech` |
| 20s 音乐（SenseVoice） | 复用 | 0.35s | `EMO_UNKNOWN / BGM` |
| 28.4s 语音（Whisper small） | 1.68s（local only） | 2.60s | 可用；中文偏繁体 |
| 20s BGM（节拍） | — | <0.1s | 125 BPM |
| 合成 120 BPM 点击轨 | — | <0.1s | 121 BPM |

## 5. 模型路径与选择

```
VIDLENS_ASR=auto|sensevoice|whisper
VIDLENS_SENSEVOICE_MODEL=C:\...\sense-voice-large.onnx
VIDLENS_SENSEVOICE_TOKENS=D:\dev\models\sensevoice\tokens.txt
VIDLENS_MODEL_DIR=D:\dev\models\whisper
VIDLENS_MODEL_ROOT=D:\dev\models
```

优先级：

1. `VIDLENS_ASR=whisper` → 强制 Whisper；
2. `auto` + SenseVoice 文件齐全 → SenseVoice；
3. `auto` + 不齐全 → Whisper；
4. 两者都没有 → 报错，提示跑 `vl models` / `doctor`。

## 6. 下载政策

- **绝不自动下载**。`vidlens_models` / `vl models` 只列目录、给硬件建议。
- 下载前由 AI 明确问用户：模型名、体积、用途、许可证、放哪里。
- 模型权重不进源码包；用户自己放 `D:\dev\models` 或 env 指向。
- 本工程已装的权重：Whisper 484MB、SenseVoice 937MB（用户已有）、tokens 308KB。

## 7. 许可证

- SenseVoice 模型：上游 `iic/SenseVoiceSmall`，许可证以上游为准；本工程不随包分发权重。
- sherpa-onnx：Apache-2.0。
- faster-whisper：MIT；Whisper 权重 MIT。
- CED-mini：Apache-2.0（HF 元数据）。
- AcoustID：服务非商业、限速；Chromaprint 单独许可证。
- 再分发前读 `NOTICE.md`，并确认模型许可证。
