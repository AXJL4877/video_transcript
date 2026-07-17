"""编排层：发现 download / asr 两个本机服务，串起「下载 → 转写」。

- 服务发现：先读端口注册表 %USERPROFILE%/.scene-studio/ports.json，
  再在默认端口范围探活（校验 /health.service）。
- download：POST /download（异步 job）→ 轮询 /jobs/:id → 取回文件字节。
- asr：POST /run（multipart audio）→ 拿 text / srt / segments。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable

import requests

REGISTRY_FILE = Path(os.environ.get("SCENE_STUDIO_PORTS_FILE") or
                     (Path(os.path.expanduser("~")) / ".scene-studio" / "ports.json"))

# serviceId -> (health.service 值, 默认端口, 探测个数)
DOWNSTREAM = {
    "download": ("video_download", 8789, 12),
    "asr": ("audio_asr", 8791, 16),
}


def _self_port() -> int:
    try:
        return int(os.environ.get("TRANSCRIPT_PORT", "8799"))
    except Exception:
        return 8799


class PipelineError(Exception):
    pass


def _read_registry() -> dict[str, Any]:
    try:
        return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _probe(base_url: str, expect_service: str, timeout: float = 1.5) -> bool:
    try:
        r = requests.get(f"{base_url}/health", timeout=timeout)
        if not r.ok:
            return False
        svc = (r.json() or {}).get("service")
        return (not expect_service) or svc == expect_service
    except Exception:
        return False


def discover(service_id: str, deep: bool = True) -> str | None:
    """返回可用 baseUrl（如 http://127.0.0.1:8789），找不到返回 None。

    deep=False 时只查「环境变量 + 注册表 + 默认端口」（快，用于 /health）；
    deep=True 时再加默认端口范围扫描（用于真正发起任务）。
    绝不探测本服务自身端口，避免 /health 递归。
    """
    expect, default_port, tries = DOWNSTREAM[service_id]
    self_port = _self_port()
    # 下载服务 /health 会跑 yt-dlp/ffmpeg 探测，响应可能 1~2s；离线端口会立即拒绝，
    # 因此这里给较宽松的超时不影响离线判断速度。
    timeout = 5.0 if deep else 3.0

    # 优先级候选（去重、跳过自身端口）
    candidates: list[str] = []

    def add(url: str | None) -> None:
        if not url:
            return
        u = url.rstrip("/")
        if u not in candidates:
            candidates.append(u)

    add(os.environ.get(f"{service_id.upper()}_BASE_URL"))
    add((_read_registry().get(service_id) or {}).get("baseUrl"))
    if default_port != self_port:
        add(f"http://127.0.0.1:{default_port}")
    if deep:
        for i in range(tries):
            port = default_port + i
            if port != self_port:
                add(f"http://127.0.0.1:{port}")

    for base in candidates:
        if _probe(base, expect, timeout=timeout):
            return base
    return None


def downstream_status() -> dict[str, Any]:
    """/health 用：轻量、非递归、短超时。"""
    out: dict[str, Any] = {}
    for sid in DOWNSTREAM:
        base = discover(sid, deep=False)
        out[sid] = {"ok": bool(base), "baseUrl": base}
    return out


# ---------------- 下载 ----------------

def _download_start(base: str, url: str, quality: str, cookies_browser: str, proxy: str) -> str:
    body: dict[str, Any] = {"url": url, "quality": quality or "audio", "async": True}
    if quality == "audio":
        body["audioOnly"] = True
    if cookies_browser:
        body["cookiesFromBrowser"] = cookies_browser
    if proxy:
        body["proxy"] = proxy
    r = requests.post(f"{base}/download", json=body, timeout=30)
    if r.status_code not in (200, 202):
        raise PipelineError(f"下载服务拒绝任务：HTTP {r.status_code} {r.text[:300]}")
    data = r.json()
    job_id = data.get("job_id")
    if not job_id:
        raise PipelineError(f"下载服务未返回 job_id：{data}")
    return job_id


def _download_poll(
    base: str,
    job_id: str,
    on_progress: Callable[[int, str], None] | None,
    timeout_s: int = 1500,
) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = requests.get(f"{base}/jobs/{job_id}", timeout=15)
        if not r.ok:
            raise PipelineError(f"查询下载进度失败：HTTP {r.status_code}")
        j = r.json()
        status = j.get("status")
        prog = int(j.get("progress") or 0)
        if on_progress:
            # 下载阶段占整体 0~55%
            on_progress(min(55, int(prog * 0.55)), f"下载中 {prog}%（{j.get('stage', '')}）")
        if status == "done":
            return j
        if status in ("error", "cancelled"):
            raise PipelineError(j.get("error") or "下载失败")
        time.sleep(1.2)
    raise PipelineError("下载超时")


def _fetch_file(base: str, file_url: str, file_name: str) -> tuple[bytes, str]:
    """下载完成后把媒体文件字节取回。file_url 形如 /files/xxx。"""
    if not file_url:
        file_url = f"/files/{file_name}"
    r = requests.get(f"{base}{file_url}", timeout=600)
    if not r.ok:
        raise PipelineError(f"取回下载文件失败：HTTP {r.status_code}")
    return r.content, file_name


# ---------------- 转写 ----------------

def _transcribe(base: str, content: bytes, file_name: str,
                on_progress: Callable[[int, str], None] | None) -> dict[str, Any]:
    if on_progress:
        on_progress(60, "上传音频并识别中……")
    files = {"audio": (file_name, content, "application/octet-stream")}
    data = {"format": "txt", "engine": "bcut"}
    r = requests.post(f"{base}/run", files=files, data=data, timeout=1500)
    if not r.ok:
        raise PipelineError(f"转写失败：HTTP {r.status_code} {r.text[:300]}")
    return r.json()


# ---------------- 完整流程 ----------------

def run_pipeline(
    *,
    url: str,
    quality: str = "audio",
    cookies_browser: str = "",
    proxy: str = "",
    on_progress: Callable[[int, str], None] | None = None,
) -> dict[str, Any]:
    """执行 下载 → 转写，返回 {video_title, text, srt, segments_count, duration, engine, quality}。"""
    dl_base = discover("download")
    if not dl_base:
        raise PipelineError("未发现 video_download 服务（端口 8789）。请先启动下载模块。")
    asr_base = discover("asr")
    if not asr_base:
        raise PipelineError("未发现 audio_asr 服务（端口 8791）。请先启动音频转文字模块。")

    if on_progress:
        on_progress(3, "已连接下载 / 转写服务")

    job_id = _download_start(dl_base, url, quality, cookies_browser, proxy)
    dl = _download_poll(dl_base, job_id, on_progress)
    file_name = dl.get("file") or dl.get("title") or "media.m4a"
    file_url = dl.get("url_file") or dl.get("url")
    video_title = dl.get("title") or Path(file_name).stem

    if on_progress:
        on_progress(56, "下载完成，取回音频……")
    content, upload_name = _fetch_file(dl_base, file_url, file_name)

    asr = _transcribe(asr_base, content, upload_name, on_progress)
    if on_progress:
        on_progress(92, "识别完成，写入归档……")

    return {
        "video_title": video_title,
        "text": asr.get("text") or "",
        "srt": asr.get("srt") or "",
        "segments_count": int(asr.get("segments_count") or 0),
        "duration": dl.get("duration"),
        "engine": asr.get("engine") or "bcut",
        "quality": quality,
    }
