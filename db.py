"""SQLite 归档层：视频文案入库、改名、检索、删除。

单文件 sqlite（`data/transcripts.db`），正文（txt/srt）直接入库，
同时把 txt/srt 落一份到 `outputs/` 便于直接下载。
"""
from __future__ import annotations

import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUTS = ROOT / "outputs"
DATA_DIR.mkdir(exist_ok=True)
OUTPUTS.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "transcripts.db"

_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS transcripts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT    NOT NULL,
    source_url      TEXT    NOT NULL,
    video_title     TEXT,
    text            TEXT    NOT NULL DEFAULT '',
    srt             TEXT    NOT NULL DEFAULT '',
    segments_count  INTEGER NOT NULL DEFAULT 0,
    duration        REAL,
    engine          TEXT,
    quality         TEXT,
    txt_path        TEXT,
    srt_path        TEXT,
    char_count      INTEGER NOT NULL DEFAULT 0,
    created_at      REAL    NOT NULL,
    updated_at      REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transcripts_created ON transcripts(created_at DESC);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _lock, _connect() as conn:
        conn.executescript(_SCHEMA)


def _safe_stem(name: str) -> str:
    """把标题清成安全的文件名主体。"""
    stem = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", (name or "").strip())
    stem = stem.strip(". ")
    return (stem or "transcript")[:80]


def _write_output_files(record_id: int, title: str, text: str, srt: str) -> tuple[str, str]:
    """把 txt/srt 落盘到 outputs/，返回 (txt_rel_url, srt_rel_url)。"""
    stem = f"{record_id:04d}_{_safe_stem(title)}"
    txt_name = f"{stem}.txt"
    srt_name = f"{stem}.srt"
    (OUTPUTS / txt_name).write_text(text or "", encoding="utf-8")
    (OUTPUTS / srt_name).write_text(srt or "", encoding="utf-8")
    return f"/outputs/{txt_name}", f"/outputs/{srt_name}"


def _cleanup_output_files(row: sqlite3.Row) -> None:
    for key in ("txt_path", "srt_path"):
        rel = row[key] if key in row.keys() else None
        if rel:
            fname = rel.rsplit("/", 1)[-1]
            try:
                (OUTPUTS / fname).unlink(missing_ok=True)
            except Exception:
                pass


def create_archive(
    *,
    title: str,
    source_url: str,
    video_title: str | None,
    text: str,
    srt: str,
    segments_count: int,
    duration: float | None,
    engine: str | None,
    quality: str | None,
) -> dict[str, Any]:
    now = time.time()
    with _lock, _connect() as conn:
        cur = conn.execute(
            """INSERT INTO transcripts
               (title, source_url, video_title, text, srt, segments_count,
                duration, engine, quality, char_count, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                title,
                source_url,
                video_title,
                text,
                srt,
                segments_count,
                duration,
                engine,
                quality,
                len((text or "").replace("\n", "").replace(" ", "")),
                now,
                now,
            ),
        )
        record_id = int(cur.lastrowid)
        txt_url, srt_url = _write_output_files(record_id, title, text, srt)
        conn.execute(
            "UPDATE transcripts SET txt_path=?, srt_path=? WHERE id=?",
            (txt_url, srt_url, record_id),
        )
        conn.commit()
    return get_archive(record_id)  # type: ignore[return-value]


def _row_to_dict(row: sqlite3.Row, with_text: bool = True) -> dict[str, Any]:
    d = dict(row)
    if not with_text:
        d.pop("text", None)
        d.pop("srt", None)
    return d


def get_archive(record_id: int, with_text: bool = True) -> dict[str, Any] | None:
    with _lock, _connect() as conn:
        row = conn.execute("SELECT * FROM transcripts WHERE id=?", (record_id,)).fetchone()
    return _row_to_dict(row, with_text) if row else None


def list_archives(query: str = "", limit: int = 200) -> list[dict[str, Any]]:
    sql = "SELECT * FROM transcripts"
    params: list[Any] = []
    if query.strip():
        sql += " WHERE title LIKE ? OR text LIKE ? OR source_url LIKE ?"
        like = f"%{query.strip()}%"
        params += [like, like, like]
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with _lock, _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    # 列表不带全文，避免 payload 过大；给一段预览
    out = []
    for r in rows:
        d = _row_to_dict(r, with_text=False)
        text = r["text"] or ""
        d["preview"] = text[:120]
        out.append(d)
    return out


def rename_archive(record_id: int, new_title: str) -> dict[str, Any] | None:
    new_title = (new_title or "").strip()
    if not new_title:
        raise ValueError("标题不能为空")
    with _lock, _connect() as conn:
        row = conn.execute("SELECT * FROM transcripts WHERE id=?", (record_id,)).fetchone()
        if not row:
            return None
        # 重命名同时把落盘文件也换名，旧文件删掉
        _cleanup_output_files(row)
        txt_url, srt_url = _write_output_files(record_id, new_title, row["text"], row["srt"])
        conn.execute(
            "UPDATE transcripts SET title=?, txt_path=?, srt_path=?, updated_at=? WHERE id=?",
            (new_title, txt_url, srt_url, time.time(), record_id),
        )
        conn.commit()
    return get_archive(record_id)


def update_text(record_id: int, text: str) -> dict[str, Any] | None:
    """允许人工修订文案正文（同步刷新落盘 txt 与字数）。"""
    with _lock, _connect() as conn:
        row = conn.execute("SELECT * FROM transcripts WHERE id=?", (record_id,)).fetchone()
        if not row:
            return None
        txt_url, srt_url = _write_output_files(record_id, row["title"], text, row["srt"])
        conn.execute(
            "UPDATE transcripts SET text=?, txt_path=?, char_count=?, updated_at=? WHERE id=?",
            (
                text,
                txt_url,
                len((text or "").replace("\n", "").replace(" ", "")),
                time.time(),
                record_id,
            ),
        )
        conn.commit()
    return get_archive(record_id)


def delete_archive(record_id: int) -> bool:
    with _lock, _connect() as conn:
        row = conn.execute("SELECT * FROM transcripts WHERE id=?", (record_id,)).fetchone()
        if not row:
            return False
        _cleanup_output_files(row)
        conn.execute("DELETE FROM transcripts WHERE id=?", (record_id,))
        conn.commit()
    return True


def stats() -> dict[str, Any]:
    with _lock, _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(char_count),0) AS chars FROM transcripts"
        ).fetchone()
    return {"count": int(row["n"]), "total_chars": int(row["chars"])}
