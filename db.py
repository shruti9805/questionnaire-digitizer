"""SQLite storage layer for the Questionnaire Digitizer.

Schema is laid out in full now (phases/items/demo_fields/batches/responses/
response_items) even though component 1 only exercises `phases`, so later
components don't need a migration step. Each function opens and closes its
own connection - this is a low-concurrency local tool, not a pooled service.
"""
import json
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
    statement_en TEXT NOT NULL,
    statement_hi TEXT
);

CREATE TABLE IF NOT EXISTS demo_fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phase_id INTEGER NOT NULL REFERENCES phases(id),
    position INTEGER NOT NULL,
    label_en TEXT NOT NULL,
    label_hi TEXT,
    field_type TEXT NOT NULL DEFAULT 'text',
    options_json TEXT
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


def save_schema(phase_id: int, items: list[dict], demo_fields: list[dict]) -> None:
    """Persist a parsed schema (see parse_docx.parse_phase_docx) for a phase.
    Replaces any existing items/demo_fields for that phase (re-importing the
    same phase's docx should not duplicate rows)."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM items WHERE phase_id = ?", (phase_id,))
        conn.execute("DELETE FROM demo_fields WHERE phase_id = ?", (phase_id,))
        conn.executemany(
            "INSERT INTO items (phase_id, position, code, statement_en, statement_hi) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (phase_id, it["position"], it["code"], it["statement_en"], it["statement_hi"])
                for it in items
            ],
        )
        conn.executemany(
            "INSERT INTO demo_fields (phase_id, position, label_en, label_hi, field_type, options_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    phase_id,
                    df["position"],
                    df["label_en"],
                    df["label_hi"],
                    df["field_type"],
                    json.dumps(df["options"]) if df["options"] is not None else None,
                )
                for df in demo_fields
            ],
        )
        conn.commit()
    finally:
        conn.close()


def get_items(phase_id: int) -> list[sqlite3.Row]:
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT id, position, code, statement_en, statement_hi FROM items "
            "WHERE phase_id = ? ORDER BY position",
            (phase_id,),
        ).fetchall()
    finally:
        conn.close()


def get_demo_fields(phase_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, position, label_en, label_hi, field_type, options_json FROM demo_fields "
            "WHERE phase_id = ? ORDER BY position",
            (phase_id,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["options"] = json.loads(d["options_json"]) if d["options_json"] else None
            del d["options_json"]
            result.append(d)
        return result
    finally:
        conn.close()
