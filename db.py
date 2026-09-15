"""SQLite storage layer for the Questionnaire Digitizer.

Schema is laid out in full now (phases/items/demo_fields/batches/responses/
response_items) even though component 1 only exercises `phases`, so later
components don't need a migration step. Each function opens and closes its
own connection - this is a low-concurrency local tool, not a pooled service.
"""
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).parent / "questionnaire_digitizer.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS phases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    source_docx_filename TEXT NOT NULL,
    uploaded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phase_id INTEGER NOT NULL REFERENCES phases(id),
    position INTEGER NOT NULL,
    code TEXT NOT NULL,
    statement TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS demo_fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phase_id INTEGER NOT NULL REFERENCES phases(id),
    position INTEGER NOT NULL,
    label TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phase_id INTEGER NOT NULL REFERENCES phases(id),
    source_pdf_filename TEXT NOT NULL,
    uploaded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES batches(id),
    respondent_label TEXT
);

CREATE TABLE IF NOT EXISTS response_demo_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    response_id INTEGER NOT NULL REFERENCES responses(id),
    demo_field_id INTEGER NOT NULL REFERENCES demo_fields(id),
    value TEXT
);

CREATE TABLE IF NOT EXISTS response_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    response_id INTEGER NOT NULL REFERENCES responses(id),
    item_id INTEGER NOT NULL REFERENCES items(id),
    value INTEGER,
    confidence TEXT NOT NULL DEFAULT 'ok',
    note TEXT
);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def create_phase(name: str, source_docx_filename: str) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO phases (name, source_docx_filename, uploaded_at) VALUES (?, ?, ?)",
            (name, source_docx_filename, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_phases() -> list[sqlite3.Row]:
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT id, name, source_docx_filename, uploaded_at FROM phases ORDER BY id DESC"
        ).fetchall()
    finally:
        conn.close()
