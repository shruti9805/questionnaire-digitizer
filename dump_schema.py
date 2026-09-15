"""Parse a phase's .docx template and write its schema to schemas/<slug>.json
for committing to the repo (see schema_loader.py for why).

Usage: python3 dump_schema.py path/to/template.docx "Phase Name"
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

from parse_docx import parse_phase_docx

SCHEMAS_DIR = Path(__file__).parent / "schemas"


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "phase"


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 dump_schema.py path/to/template.docx \"Phase Name\"")
        sys.exit(1)
    docx_path, phase_name = sys.argv[1], sys.argv[2]

    items, demo_fields = parse_phase_docx(docx_path)

    data = {
        "name": phase_name,
        "source_docx_filename": Path(docx_path).name,
        "items": [
            {"position": it.position, "code": it.code,
             "statement_en": it.statement_en, "statement_hi": it.statement_hi}
            for it in items
        ],
        "demo_fields": [
            {"position": df.position, "label_en": df.label_en, "label_hi": df.label_hi,
             "field_type": df.field_type, "options": df.options}
            for df in demo_fields
        ],
    }

    SCHEMAS_DIR.mkdir(exist_ok=True)
    out_path = SCHEMAS_DIR / f"{slugify(phase_name)}.json"
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"Wrote {out_path} ({len(items)} items, {len(demo_fields)} demo fields)")


if __name__ == "__main__":
    main()
