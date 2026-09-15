import tempfile
from pathlib import Path

import streamlit as st

from db import init_db, create_phase, list_phases, save_schema, get_items, get_demo_fields
from parse_docx import parse_phase_docx, SchemaParseError

st.set_page_config(page_title="Questionnaire Digitizer", page_icon="\U0001F4CB")

init_db()

st.title("Questionnaire Digitizer")
st.caption("Import a phase's .docx template to define its schema (demographic fields + Likert items).")

uploaded = st.file_uploader("Phase template (.docx)", type=["docx"])

if uploaded is not None:
    default_name = uploaded.name.rsplit(".", 1)[0]
    phase_name = st.text_input("Phase name", value=default_name)
    if st.button("Save phase"):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / uploaded.name
            tmp_path.write_bytes(uploaded.getvalue())
            try:
                items, demo_fields = parse_phase_docx(str(tmp_path))
            except SchemaParseError as e:
                st.error(f"Couldn't read this as a phase template: {e}")
                items = None

        if items is not None:
            phase_id = create_phase(name=phase_name, source_docx_filename=uploaded.name)
            save_schema(
                phase_id,
                items=[
                    {
                        "position": it.position,
                        "code": it.code,
                        "statement_en": it.statement_en,
                        "statement_hi": it.statement_hi,
                    }
                    for it in items
                ],
                demo_fields=[
                    {
                        "position": df.position,
                        "label_en": df.label_en,
                        "label_hi": df.label_hi,
                        "field_type": df.field_type,
                        "options": df.options,
                    }
                    for df in demo_fields
                ],
            )
            st.success(
                f"Saved phase #{phase_id}: {phase_name} — {len(items)} Likert items, "
                f"{len(demo_fields)} demographic fields."
            )

st.subheader("Phases stored so far")
phases = list_phases()
if not phases:
    st.write("No phases yet.")
else:
    for p in phases:
        with st.expander(f"#{p['id']} — {p['name']} ({p['source_docx_filename']}, {p['uploaded_at']})"):
            items = get_items(p["id"])
            demo_fields = get_demo_fields(p["id"])
            st.write(f"**{len(items)} Likert items**, **{len(demo_fields)} demographic fields**")

            st.markdown("**Demographic fields**")
            st.table(
                [
                    {
                        "label": df["label_en"],
                        "type": df["field_type"],
                        "options": ", ".join(df["options"]) if df["options"] else "",
                    }
                    for df in demo_fields
                ]
            )

            st.markdown("**Likert items**")
            st.dataframe(
                [
                    {"pos": it["position"], "code": it["code"], "statement": it["statement_en"]}
                    for it in items
                ],
                hide_index=True,
                width="stretch",
            )
