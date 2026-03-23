import sqlite3
import uuid
import json
import os
import time
from datetime import datetime, timezone

DB_PATH = os.environ.get("LUMEWAY_LOG_DB", "lumeway_logs.db")


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            transition_category TEXT,
            user_state TEXT,
            disclaimer_displayed INTEGER DEFAULT 0,
            boundary_redirection_count INTEGER DEFAULT 0,
            crisis_resources_provided INTEGER DEFAULT 0,
            templates_mentioned TEXT DEFAULT '[]',
            duration_seconds REAL,
            flagged_for_review INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS boundary_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            user_message TEXT NOT NULL,
            boundary_category TEXT NOT NULL,
            redirect_response_summary TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        );

        CREATE INDEX IF NOT EXISTS idx_sessions_flagged
            ON sessions(flagged_for_review) WHERE flagged_for_review = 1;

        CREATE INDEX IF NOT EXISTS idx_sessions_category
            ON sessions(transition_category);

        CREATE INDEX IF NOT EXISTS idx_boundary_session
            ON boundary_events(session_id);
    """)
    conn.close()


def log_session_start():
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    conn.execute(
        "INSERT INTO sessions (session_id, started_at) VALUES (?, ?)",
        (session_id, now),
    )
    conn.commit()
    conn.close()
    return session_id


def update_session(session_id, **fields):
    allowed = {
        "transition_category",
        "user_state",
        "disclaimer_displayed",
        "crisis_resources_provided",
        "templates_mentioned",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    if "templates_mentioned" in updates and isinstance(updates["templates_mentioned"], list):
        updates["templates_mentioned"] = json.dumps(updates["templates_mentioned"])
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [session_id]
    conn = _connect()
    conn.execute(f"UPDATE sessions SET {set_clause} WHERE session_id = ?", values)
    conn.commit()
    conn.close()


def log_boundary_redirection(session_id, user_message, boundary_category, redirect_response_summary):
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    conn.execute(
        """INSERT INTO boundary_events
           (session_id, timestamp, user_message, boundary_category, redirect_response_summary)
           VALUES (?, ?, ?, ?, ?)""",
        (session_id, now, user_message, boundary_category, redirect_response_summary),
    )
    conn.execute(
        "UPDATE sessions SET boundary_redirection_count = boundary_redirection_count + 1 WHERE session_id = ?",
        (session_id,),
    )
    conn.commit()
    conn.close()
    flag_session_for_review(session_id)


def log_session_end(session_id):
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    row = conn.execute(
        "SELECT started_at FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    duration = None
    if row:
        started = datetime.fromisoformat(row["started_at"])
        duration = (datetime.now(timezone.utc) - started).total_seconds()
    conn.execute(
        "UPDATE sessions SET ended_at = ?, duration_seconds = ? WHERE session_id = ?",
        (now, duration, session_id),
    )
    conn.commit()
    conn.close()


def flag_session_for_review(session_id):
    conn = _connect()
    row = conn.execute(
        "SELECT boundary_redirection_count FROM sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if row and row["boundary_redirection_count"] >= 3:
        conn.execute(
            "UPDATE sessions SET flagged_for_review = 1 WHERE session_id = ?",
            (session_id,),
        )
        conn.commit()
    conn.close()


def get_session(session_id):
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    conn.close()
    if row:
        result = dict(row)
        result["templates_mentioned"] = json.loads(result.get("templates_mentioned") or "[]")
        return result
    return None


def get_boundary_events(session_id):
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM boundary_events WHERE session_id = ? ORDER BY timestamp",
        (session_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_flagged_sessions():
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM sessions WHERE flagged_for_review = 1 ORDER BY started_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
