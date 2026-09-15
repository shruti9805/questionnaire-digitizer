"""Load phase schemas that are committed to the repo as JSON (schemas/*.json)
into the local database on app startup.

Why this exists: on Streamlit Community Cloud, local disk (and so the local
SQLite file) is wiped on every restart/redeploy. Phase schemas (parsed from
a researcher's .docx template) are the one thing that needs to survive that
- but there's very little of this data and it changes rarely, so instead of
standing up an external database, the parsed schema is committed to the git
repo as JSON and re-loaded into local SQLite every time the app starts. This
is functionally "persistent" (it survives every restart, because the source
of truth is the repo, not the ephemeral disk) without adding a new service.

To add a new phase once deployed: parse the .docx with dump_schema.py,
commit the resulting JSON file under schemas/, push, and Streamlit Cloud
will redeploy with it available automatically.

response/batch data is NOT handled here - by design, that stays local and
ephemeral (see PRODUCT.md's deployment section): the expected workflow is
process -> review -> export within one sitting, before any restart.
"""
from __future__ import annotations

import json
from pathlib import Path

from db import create_phase, list_phases, save_schema

SCHEMAS_DIR = Path(__file__).parent / "schemas"


def load_schemas_from_disk() -> list[str]:
    """Loads every schemas/*.json file into the DB, skipping any phase name
    that already exists (so this is safe to call on every app startup
    without creating duplicate phases). Returns the names of phases newly
    loaded this call."""
    if not SCHEMAS_DIR.exists():
        return []

    existing_names = {p["name"] for p in list_phases()}
    loaded = []
    for path in sorted(SCHEMAS_DIR.glob("*.json")):
        data = json.loads(path.read_text())
        name = data["name"]
        if name in existing_names:
            continue
        phase_id = create_phase(name=name, source_docx_filename=data["source_docx_filename"])
        save_schema(phase_id, items=data["items"], demo_fields=data["demo_fields"])
        loaded.append(name)
    return loaded
