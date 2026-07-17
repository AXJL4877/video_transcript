# video_transcript · 视频文案归档

输入视频链接 → 自动**下载** → **音频转文字**（必剪 BcutASR，免费免密钥）→ **文案归档入库**（SQLite）。
按视频原标题命名，支持随时改名与正文修订，提供归档管理网页。

本模块是**编排型**服务，自身不下载、不识别，而是通过 HTTP 串联两个已有本机服务：

- [`video_download`](https://github.com/AXJL4877/video_download)（yt-dlp 下载，默认端口 8789）
- [`audio_asr`](https://github.com/AXJL4877/audio_asr)（必剪 BcutASR 转写，默认端口 8791）

## 快速开始（Windows）

```bat
:: 1) 先启动两个下游服务
::    video_download\start.bat
::    audio_asr\start_api.bat
:: 2) 启动本模块并打开管理页
start_web.bat
```

打开 `http://127.0.0.1:8799/ui`，粘贴视频链接（B站 / YouTube / 抖音 等）→「开始下载并转写」，
完成后即出现在归档列表，可查看 / 改名 / 修订正文 / 下载 TXT·SRT / 删除。

## 技术栈

Python 3.10+ · FastAPI · sqlite3（标准库）· requests。数据库 `data/transcripts.db`，
txt/srt 同时落盘到 `outputs/`。服务发现顺序：环境变量 → `%USERPROFILE%\.scene-studio\ports.json` → 默认端口探活。

## HTTP API

| Method | Path | 用途 |
|--------|------|------|
| GET | `/health` | 健康 + 下游在线状态 + 归档统计 |
| POST | `/run` | 主入口：`{url, title?, quality?, cookiesFromBrowser?, proxy?}` → `{job_id, status_url}` |
| GET | `/jobs/{id}` | 任务进度（下载 → 转写 → 归档） |
| GET | `/archives?q=` | 归档列表（可搜索） |
| GET | `/archives/{id}` | 归档详情（含全文） |
| PATCH | `/archives/{id}` | 改名 `{title}` / 修订正文 `{text}` |
| DELETE | `/archives/{id}` | 删除 |
| GET | `/archives/{id}/download?fmt=txt\|srt` | 下载文案 |
| GET | `/ui` | 归档管理台 |

详见 [`AGENTS.md`](./AGENTS.md)。

## 说明

- 文案场景默认 `quality=audio`（只下音频，最快最省）；需留存视频再选清晰度。
- B站等风控站点若报 412，选 `cookiesFromBrowser`（edge/chrome/firefox）。
- 转写走必剪公开端点（免费、非官方 SLA），音频会上传到 bilibili 识别服务，隐私敏感场景请自行评估。
