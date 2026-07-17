# AGENTS.md — video_transcript（视频文案归档）

> 面向把本模块接入其他项目的 AI/开发者。

## 注册（唯一真源）

**本文件夹的 `module.json` 是唯一注册文件**（schema 见仓库根 `MODULE_SPEC.md`）。
宿主扫描 Desktop / `mo_kuai` 下的 `module.json` 自动接线端口 / launcher / Vite 代理，**不要**改宿主硬编码表。

| 字段 | 值 |
|------|-----|
| serviceId（`module.json` id） | `transcript` |
| `local.label` / `/health.service` | `video_transcript` |
| 默认端口 | `8799` |
| 端口注册表 | `%USERPROFILE%\.scene-studio\ports.json` → `transcript.baseUrl` |
| 技术栈 | Python 3.10+ + FastAPI + requests + sqlite3（标准库） |

## 角色

**编排型**模块：输入视频链接 → 自动「下载 → 音频转文字 → 归档入库」。
本模块自身不下载、不识别，而是通过 HTTP 编排两个已有本机服务：

- `video_download`（serviceId `download`，:8789）：yt-dlp 下载视频/音频
- `audio_asr`（serviceId `asr`，:8791）：必剪 BcutASR 免费转文字

归档存 SQLite（`data/transcripts.db`），正文入库并同步落一份 txt/srt 到 `outputs/`。
标题默认取视频原标题，**可随时改名**（改名会同步重命名落盘文件）。

## 目录

```
video_transcript/
  module.json        ← 宿主自动发现
  AGENTS.md
  server.py          ← FastAPI 入口：/run 任务、/archives CRUD、/health、/ui
  pipeline.py        ← 服务发现 + 编排（download → asr）
  db.py              ← SQLite 归档层（入库/改名/检索/删除）
  web/index.html     ← /ui 归档管理台（提交/进度/列表/搜索/改名/下载/删除）
  requirements.txt
  start_api.ps1|.bat ← venv + 依赖 + 端口注册 + uvicorn
  start_web.ps1|.bat ← 启动（若未运行）并打开 /ui
  port_utils.ps1
  data/              ← sqlite 数据库
  outputs/           ← 落盘的 txt/srt
```

## 前置依赖（编排型模块）

本模块是**编排型**：自身不下载不识别，通过 HTTP 调用两个下游服务：
`video_download`(:8789) 与 `audio_asr`(:8791)。这**不违反**「模块独立」——
`MODULE_SPEC §1.1` 的独立指「不依赖宿主壳」，而非「模块间不可互调」。

**自动拉起（v1.1+）**：`start_api.ps1` 启动前会探测两个下游，未在线则自动到
同级 / `Desktop/mo_kuai` / `Desktop` 下找到 `video_download`、`audio_asr` 文件夹并拉起它们。
因此**通常只需启动本模块一个**（双击 `start_web.bat` / `start_api.bat`）。

自动拉起失败时（未找到文件夹 / 首启装依赖较久）会打印 warn，此时手动启动即可：

1. `video_download`：双击其 `start.bat`
2. `audio_asr`：双击其 `start_api.bat`（视频转写需要 ffmpeg 在 PATH）

服务发现顺序：环境变量 `DOWNLOAD_BASE_URL` / `ASR_BASE_URL` → `ports.json` → 默认端口探活。
`GET /health.downstream` 显示两个下游是否在线。

## 启动

```bat
start_api.bat   :: 起服务
start_web.bat   :: 起服务（若未运行）并打开 /ui
```

## HTTP API

| Method | Path | 用途 |
|--------|------|------|
| GET | `/health` | `service=video_transcript`，含 `downstream`（下游在线状态）、`archives`（统计） |
| POST | `/run` | **主 endpoint**：JSON `{url, title?, quality?, cookiesFromBrowser?, proxy?}` → `{job_id, status_url}` |
| GET | `/jobs/{id}` | 任务进度（下载→转写→归档），`status`=queued/running/done/error |
| GET | `/jobs` | 最近任务列表 |
| GET | `/archives?q=` | 归档列表（带预览，不含全文），可搜索标题/正文/链接 |
| GET | `/archives/{id}` | 单条归档详情（含全文 text/srt） |
| PATCH | `/archives/{id}` | 改名 `{title}` 或修订正文 `{text}` |
| DELETE | `/archives/{id}` | 删除归档（连带删除落盘文件） |
| GET | `/archives/{id}/download?fmt=txt\|srt` | 下载文案文件 |
| GET/POST/DELETE | `/cookies/*` | Cookie 管理（`sites`/`login`/`save`/`close`/`list`/`file`），**代理**到下载服务(:8789) |
| GET | `/ui` | 归档管理台 |
| GET | `/docs` | OpenAPI |

## 数据流

```
POST /run {url}
  → pipeline.discover('download') / discover('asr')
  → download: POST /download (async) → 轮询 /jobs/:id → GET /files/:name 取回音频
  → asr: POST /run (multipart audio) → {text, srt, segments_count}
  → db.create_archive(title=自定义||视频标题, text, srt, ...)
  → job.status=done, archive_id
```

## 独立验收（MODULE_SPEC §1.1）

1. 先启动 `video_download` 与 `audio_asr` 两个服务
2. 双击 `start_web.bat` → 打开 `/ui`
3. 状态栏三个圆点全绿（本服务 / 下载 / 转写）
4. 粘贴一个视频链接（如 B站短视频）→ 点「开始下载并转写」
5. 进度跑到「完成 ✓」→ 下方列表出现新归档，标题为视频原标题
6. 点「查看」可改名、修订正文、下载 TXT/SRT
7. `GET /health` 中 `service === "video_transcript"`

## Capabilities & 接入自检（防小功能漏接）

所有能力（含 `cookie-passthrough` cookie 透传、`rename-sync-download` 改名同步落盘这类小功能）
登记在 `module.json` → `capabilities[]`，为接入完成定义(DoD)。`must_keep: true` 的能力不得在接入中丢失。
**最易漏的是 `/cookies/*` 透传**——宿主接入时必须一并代理。

```bat
start_api.bat        :: 先起服务（并启动 download/asr 下游）
verify.bat           :: 逐条探测 capabilities（自动项变红=没接通）
```

或 `python verify.py`；过宿主代理自检：`python verify.py --base http://localhost:5173 --prefix /transcript-api`。
`manual` 项脚本会列出，接入时逐条人工确认。规范见根 `MODULE_SPEC.md §10`。

## 注意

- 文案场景默认 `quality=audio`（只下音频，最快最省）；需要留存视频再选清晰度。
- B站等风控站点若报 412，选 `cookiesFromBrowser`（edge/chrome/firefox）或在下载模块放 cookies.txt。
- 转写走必剪公开端点（免费、非官方 SLA），偶发限流可重试；音频会上传到 bilibili 识别服务。
- 改名不改 `id`（发布后永久）；展示名用 `name`。
