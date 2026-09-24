"""
SQLite persistence. Vectors are stored as float32 blobs next to each report, so a
restart doesn't re-run the models. Delete lostfound.db to start fresh.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

import numpy as np

from matcher import Report

# DATA_DIR: where the database and photos live, e.g. a persistent volume when hosted.
DATA_DIR = Path(os.getenv("DATA_DIR") or Path(__file__).parent)
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "lostfound.db"
_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, description TEXT NOT NULL, category TEXT,
    colors TEXT, brand TEXT, marks TEXT, location TEXT, time TEXT, image_path TEXT,
    text_on_item TEXT, secret_details TEXT, status TEXT, contact TEXT, kept_at TEXT,
    created_at TEXT, text_vec BLOB, caption_vec BLOB, image_vec BLOB
);
CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY, lost_id TEXT, found_id TEXT NOT NULL, question TEXT,
    attempts INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL, pickup_code TEXT UNIQUE,
    created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT, lost_id TEXT NOT NULL, found_id TEXT NOT NULL,
    confidence REAL, message TEXT, created_at TEXT
);
"""

REPORT_COLS = ["id", "kind", "description", "category", "colors", "brand", "marks", "location",
               "time", "image_path", "text_on_item", "secret_details", "status", "contact",
               "kept_at", "created_at", "text_vec", "caption_vec", "image_vec"]
CLAIM_COLS = ["id", "lost_id", "found_id", "question", "attempts", "status", "pickup_code",
              "created_at", "updated_at"]


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn


def init() -> None:
    with _lock:
        conn().executescript(SCHEMA)
        conn().commit()


def _write(sql: str, params: tuple) -> None:
    with _lock:
        conn().execute(sql, params)
        conn().commit()


def _vec(v) -> bytes | None:
    return None if v is None else np.asarray(v, dtype=np.float32).tobytes()


def _unvec(b: bytes | None) -> np.ndarray | None:
    return None if b is None else np.frombuffer(b, dtype=np.float32).copy()


def _iso(t: datetime | None) -> str | None:
    return t.isoformat(timespec="minutes") if t else None


def _dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


# ----------------------------------------------------------------------------- reports
def save_report(r: Report) -> None:
    row = (r.id, r.kind, r.description, r.category, json.dumps(r.colors), r.brand,
           json.dumps(r.marks), r.location, _iso(r.time), r.image_path, r.text_on_item,
           r.secret_details, r.status, r.contact, r.kept_at, _iso(r.created_at),
           _vec(r.text_vec), _vec(r.caption_vec), _vec(r.image_vec))
    _write(f"INSERT OR REPLACE INTO reports ({','.join(REPORT_COLS)}) "
           f"VALUES ({','.join('?' * len(REPORT_COLS))})", row)


def load_reports() -> list[Report]:
    out = []
    for x in conn().execute("SELECT * FROM reports").fetchall():
        out.append(Report(
            id=x["id"], kind=x["kind"], description=x["description"], category=x["category"],
            colors=json.loads(x["colors"] or "[]"), brand=x["brand"],
            marks=json.loads(x["marks"] or "[]"), location=x["location"], time=_dt(x["time"]),
            image_path=x["image_path"], text_on_item=x["text_on_item"],
            secret_details=x["secret_details"], status=x["status"], contact=x["contact"],
            kept_at=x["kept_at"], created_at=_dt(x["created_at"]),
            text_vec=_unvec(x["text_vec"]), caption_vec=_unvec(x["caption_vec"]),
            image_vec=_unvec(x["image_vec"])))
    return out


# ----------------------------------------------------------------------------- claims
def save_claim(c: dict) -> None:
    _write(f"INSERT OR REPLACE INTO claims ({','.join(CLAIM_COLS)}) "
           f"VALUES ({','.join('?' * len(CLAIM_COLS))})", tuple(c[k] for k in CLAIM_COLS))


def get_claim(claim_id: str) -> dict | None:
    row = conn().execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
    return dict(row) if row else None


def claim_by_code(code: str) -> dict | None:
    row = conn().execute("SELECT * FROM claims WHERE pickup_code = ?", (code,)).fetchone()
    return dict(row) if row else None


def list_claims(limit: int = 50) -> list[dict]:
    rows = conn().execute("SELECT * FROM claims ORDER BY created_at DESC LIMIT ?", (limit,))
    return [dict(r) for r in rows.fetchall()]


# ----------------------------------------------------------------------------- owner alerts
def add_notification(lost_id: str, found_id: str, confidence: float, message: str) -> None:
    _write("INSERT INTO notifications (lost_id, found_id, confidence, message, created_at) "
           "VALUES (?, ?, ?, ?, ?)",
           (lost_id, found_id, round(confidence, 3), message, _iso(datetime.now())))


def notifications_for(lost_id: str) -> list[dict]:
    rows = conn().execute("SELECT found_id, confidence, message, created_at FROM notifications "
                          "WHERE lost_id = ? ORDER BY id DESC", (lost_id,))
    return [dict(r) for r in rows.fetchall()]


def count_notifications(found_id: str | None = None) -> int:
    if found_id:
        row = conn().execute("SELECT COUNT(*) FROM notifications WHERE found_id = ?", (found_id,))
    else:
        row = conn().execute("SELECT COUNT(*) FROM notifications")
    return int(row.fetchone()[0])
