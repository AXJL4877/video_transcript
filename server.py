"""视频文案归档模块 — 本机 HTTP 服务（MODULE_SPEC.md §8 local）。

流程：输入视频链接 → 编排 download 下载 → asr 转文字 → 归档入 SQLite（可改名）。
serviceId=transcript，label=video_transcript，默认端口 8799。
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

import db
import pipeline

ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"
WEB = ROOT / "web"
OUTPUTS.mkdir(exist_ok=True)

SERVICE_LABEL = "video_transcript"
SERVICE_ID = "transcript"
DEFAULT_PORT = int(os.environ.get("TRANSCRIPT_PORT", "8799"))
HOST = os.environ.get("TRANSCRIPT_HOST", "0.0.0.0")

db.init_db()

app = FastAPI(title="视频文案归档", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if WEB.exists():
    app.mount("/static", StaticFiles(directory=str(WEB)), name="static")


def _public_base() -> str:
    port = int(os.environ.get("TRANSCRIPT_PORT", str(DEFAULT_PORT)))
    pub = "127.0.0.1" if HOST in ("0.0.0.0", "::") else HOST
    return f"http://{pub}:{port}"


# ---------------- 任务管理（内存态，异步跑流水线） ----------------

_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def _new_job(params: dict[str, Any]) -> dict[str, Any]:
    job_id = uuid.uuid4().hex[:10]
    job = {
        "id": job_id,
        "status": "queued",
        "progress": 0,
        "stage": "排队中",
        "url": params.get("url"),
        "title": (params.get("title") or "").strip(),
        "archive_id": None,
        "error": None,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    with _jobs_lock:
        _jobs[job_id] = job
    return job


def _set_job(job_id: str, **fields: Any) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job:
            job.update(fields)
            job["updated_at"] = time.time()


def _run_job(job_id: str, params: dict[str, Any]) -> None:
    _set_job(job_id, status="running", stage="启动中", progress=1)

    def on_progress(pct: int, stage: str) -> None:
        _set_job(job_id, progress=pct, stage=stage)

    try:
        result = pipeline.run_pipeline(
            url=params["url"],
            quality=params.get("quality") or "audio",
            cookies_browser=params.get("cookiesFromBrowser") or "",
            proxy=params.get("proxy") or "",
            on_progress=on_progress,
        )
        title = (params.get("title") or "").strip() or result["video_title"] or "未命名文案"
        record = db.create_archive(
            title=title,
            source_url=params["url"],
            video_title=result["video_title"],
            text=result["text"],
            srt=result["srt"],
            segments_count=result["segments_count"],
            duration=result.get("duration"),
            engine=result.get("engine"),
            quality=result.get("quality"),
        )
        _set_job(
            job_id,
            status="done",
            progress=100,
            stage="完成",
            archive_id=record["id"],
            title=record["title"],
        )
    except Exception as e:  # noqa: BLE001
        _set_job(job_id, status="error", stage="失败", error=str(e))


# ---------------- 基础 ----------------

@app.get("/health")
async def health():
    return {
        "ok": True,
        "status": "ok",
        "service": SERVICE_LABEL,
        "serviceId": SERVICE_ID,
        "host": "127.0.0.1" if HOST in ("0.0.0.0", "::") else HOST,
        "bindHost": HOST,
        "port": int(os.environ.get("TRANSCRIPT_PORT", str(DEFAULT_PORT))),
        "pid": os.getpid(),
        "baseUrl": _public_base(),
        "downstream": pipeline.downstream_status(),
        "archives": db.stats(),
    }


# ---------------- 主 endpoint：发起归档任务 ----------------

@app.post("/run")
async def run(payload: dict[str, Any] = Body(...)):
    url = str((payload or {}).get("url") or "").strip()
    if not url:
        raise HTTPException(400, detail="缺少 url")
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(400, detail="url 须以 http:// 或 https:// 开头")
    job = _new_job(payload)
    threading.Thread(target=_run_job, args=(job["id"], payload), daemon=True).start()
    return {
        "ok": True,
        "async": True,
        "job_id": job["id"],
        "status_url": f"/jobs/{job['id']}",
        "message": "已开始：下载 → 转写 → 归档",
    }


@app.get("/jobs")
async def list_jobs():
    with _jobs_lock:
        jobs = sorted(_jobs.values(), key=lambda j: j["created_at"], reverse=True)[:50]
        return {"jobs": [dict(j) for j in jobs]}


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, detail="任务不存在")
        return dict(job)


# ---------------- 归档库增删改查 ----------------

@app.get("/archives")
async def archives(q: str = Query("", alias="q"), limit: int = 200):
    return {"items": db.list_archives(q, limit), "stats": db.stats()}


@app.get("/archives/{record_id}")
async def archive_detail(record_id: int):
    rec = db.get_archive(record_id)
    if not rec:
        raise HTTPException(404, detail="记录不存在")
    return rec


@app.patch("/archives/{record_id}")
async def archive_update(record_id: int, payload: dict[str, Any] = Body(...)):
    """支持改名（title）和修订正文（text）。"""
    rec = None
    if "title" in payload:
        try:
            rec = db.rename_archive(record_id, str(payload.get("title") or ""))
        except ValueError as e:
            raise HTTPException(400, detail=str(e)) from e
    if "text" in payload:
        rec = db.update_text(record_id, str(payload.get("text") or ""))
    if rec is None:
        rec = db.get_archive(record_id)
    if not rec:
        raise HTTPException(404, detail="记录不存在")
    return rec


@app.delete("/archives/{record_id}")
async def archive_delete(record_id: int):
    if not db.delete_archive(record_id):
        raise HTTPException(404, detail="记录不存在")
    return {"ok": True, "deleted": record_id}


@app.get("/archives/{record_id}/download")
async def archive_download(record_id: int, fmt: str = "txt"):
    rec = db.get_archive(record_id)
    if not rec:
        raise HTTPException(404, detail="记录不存在")
    rel = rec.get("txt_path") if fmt == "txt" else rec.get("srt_path")
    if not rel:
        raise HTTPException(404, detail="文件不存在")
    fname = rel.rsplit("/", 1)[-1]
    path = OUTPUTS / fname
    if not path.exists():
        raise HTTPException(404, detail="文件不存在")
    return FileResponse(path, filename=fname, media_type="text/plain; charset=utf-8")


@app.get("/outputs/{filename}")
async def get_output(filename: str):
    safe = Path(filename).name
    path = OUTPUTS / safe
    if not path.exists():
        raise HTTPException(404, detail="文件不存在")
    return FileResponse(path, filename=safe)


# ---------------- UI ----------------

@app.get("/ui")
async def ui():
    index = WEB / "index.html"
    if not index.exists():
        return HTMLResponse("<h1>video_transcript UI missing</h1>", status_code=404)
    return HTMLResponse(index.read_text(encoding="utf-8"))


@app.get("/")
async def root():
    return HTMLResponse('<meta http-equiv="refresh" content="0; url=/ui">')


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("TRANSCRIPT_PORT", str(DEFAULT_PORT)))
    uvicorn.run("server:app", host=HOST, port=port, reload=False)
