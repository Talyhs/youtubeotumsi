"""SQLite state store for resumable production, calendar and asset credits."""
from __future__ import annotations
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DEFAULT_DB = Path(__file__).resolve().parents[1] / "studio_data" / "studio.db"

def connect(db_path=DEFAULT_DB):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db(db_path=DEFAULT_DB):
    with connect(db_path) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS jobs(
          id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT NOT NULL, language TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'queued', output_path TEXT, error TEXT,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS steps(
          id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER NOT NULL,
          name TEXT NOT NULL, status TEXT NOT NULL, details TEXT DEFAULT '',
          updated_at TEXT NOT NULL, UNIQUE(job_id,name),
          FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS calendar(
          id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT NOT NULL, language TEXT NOT NULL DEFAULT 'az',
          planned_date TEXT, status TEXT NOT NULL DEFAULT 'planned', notes TEXT DEFAULT '',
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS assets(
          id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT NOT NULL, source TEXT DEFAULT '',
          source_url TEXT DEFAULT '', creator TEXT DEFAULT '', license_name TEXT DEFAULT '',
          license_url TEXT DEFAULT '', attribution TEXT DEFAULT '', checked_at TEXT NOT NULL
        );
        """)
    return str(db_path)

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def create_job(topic, language="az", db_path=DEFAULT_DB):
    stamp = now()
    with connect(db_path) as db:
        cur = db.execute("INSERT INTO jobs(topic,language,status,created_at,updated_at) VALUES(?,?, 'running', ?, ?)",
                         (topic, language, stamp, stamp))
        return cur.lastrowid

def update_job(job_id, status, output_path=None, error=None, db_path=DEFAULT_DB):
    with connect(db_path) as db:
        db.execute("UPDATE jobs SET status=?, output_path=COALESCE(?,output_path), error=?, updated_at=? WHERE id=?",
                   (status, output_path, error, now(), job_id))

def set_step(job_id, name, status, details="", db_path=DEFAULT_DB):
    with connect(db_path) as db:
        db.execute("""INSERT INTO steps(job_id,name,status,details,updated_at) VALUES(?,?,?,?,?)
          ON CONFLICT(job_id,name) DO UPDATE SET status=excluded.status,details=excluded.details,updated_at=excluded.updated_at""",
          (job_id, name, status, details, now()))

def completed_step(job_id, name, db_path=DEFAULT_DB):
    with connect(db_path) as db:
        row = db.execute("SELECT status FROM steps WHERE job_id=? AND name=?", (job_id,name)).fetchone()
    return bool(row and row["status"] == "done")

def list_jobs(limit=30, db_path=DEFAULT_DB):
    with connect(db_path) as db:
        return [dict(r) for r in db.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]

def add_calendar_item(topic, language="az", planned_date="", notes="", db_path=DEFAULT_DB):
    with connect(db_path) as db:
        cur = db.execute("INSERT INTO calendar(topic,language,planned_date,notes,created_at) VALUES(?,?,?,?,?)",
                         (topic, language, planned_date or None, notes, now()))
        return cur.lastrowid

def list_calendar(db_path=DEFAULT_DB):
    with connect(db_path) as db:
        return [dict(r) for r in db.execute("SELECT * FROM calendar ORDER BY COALESCE(planned_date,'9999-12-31'), id DESC").fetchall()]

def delete_calendar_item(item_id, db_path=DEFAULT_DB):
    with connect(db_path) as db:
        db.execute("DELETE FROM calendar WHERE id=?", (int(item_id),))

def record_asset(path, source="", source_url="", creator="", license_name="", license_url="", attribution="", db_path=DEFAULT_DB):
    with connect(db_path) as db:
        db.execute("""INSERT INTO assets(path,source,source_url,creator,license_name,license_url,attribution,checked_at)
                      VALUES(?,?,?,?,?,?,?,?)""",
                   (str(path), source, source_url, creator, license_name, license_url, attribution, now()))
