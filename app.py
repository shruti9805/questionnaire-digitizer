import tempfile
import time
from pathlib import Path

import streamlit as st

from db import (
    init_db, create_phase, list_phases, save_schema, get_items, get_demo_fields, get_phase,
    create_batch, list_batches, create_response, list_responses,
    save_response_items, get_response_items, update_response_item,
    save_response_demo_value, get_response_demo_values,
)
from parse_docx import parse_phase_docx, SchemaParseError
from checkbox_pipeline import align_document_to_items, crop_source_region, list_rendered_pages
from PIL import Image

st.set_page_config(page_title="Questionnaire Digitizer", page_icon="\U0001F4CB")

init_db()

DATA_DIR = Path(__file__).parent / "data" / "batches"

st.title("Questionnaire Digitizer")

tab_phases, tab_process = st.tabs(["Phases", "Process & review"])

# ---------------------------------------------------------------------------
# Phases tab
# ---------------------------------------------------------------------------
with tab_phases:
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
                        {"position": it.position, "code": it.code,
                         "statement_en": it.statement_en, "statement_hi": it.statement_hi}
                        for it in items
                    ],
                    demo_fields=[
                        {"position": df.position, "label_en": df.label_en, "label_hi": df.label_hi,
                         "field_type": df.field_type, "options": df.options}
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
                        {"label": df["label_en"], "type": df["field_type"],
                         "options": ", ".join(df["options"]) if df["options"] else ""}
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

# ---------------------------------------------------------------------------
# Process & review tab
# ---------------------------------------------------------------------------
with tab_process:
    phases = list_phases()
    if not phases:
        st.info("Import a phase template on the Phases tab first.")
    else:
        phase_options = {f"#{p['id']} — {p['name']}": p["id"] for p in phases}
        phase_label = st.selectbox("Phase", list(phase_options.keys()))
        phase_id = phase_options[phase_label]
        phase_items = get_items(phase_id)
        phase_demo_fields = get_demo_fields(phase_id)

        st.markdown("### Upload a scanned questionnaire PDF")
        pdf_upload = st.file_uploader("Scanned PDF (one or more filled questionnaires)", type=["pdf"], key="pdf_upload")
        if pdf_upload is not None and st.button("Process PDF"):
            batch_dir = DATA_DIR / f"phase{phase_id}_{int(time.time())}"
            batch_dir.mkdir(parents=True, exist_ok=True)
            pdf_path = batch_dir / pdf_upload.name
            pdf_path.write_bytes(pdf_upload.getvalue())

            with st.spinner("Detecting checkbox grid..."):
                item_results, raw = align_document_to_items(str(pdf_path), phase_items, str(batch_dir))

            batch_id = create_batch(phase_id, pdf_upload.name, str(batch_dir))

            if item_results is None:
                st.error(
                    f"Couldn't automatically align marks to the schema: detected "
                    f"{raw.total_ticks_detected} marks but expected {raw.total_expected} "
                    f"({len(phase_items)} items). This usually means the scan has an unusual "
                    f"page break or a page is missing. Per-half detail:"
                )
                st.table(
                    [{"source": h.source, "n_ticks": len(h.ticks)} for h in raw.per_half]
                )
            else:
                response_id = create_response(batch_id)
                save_response_items(response_id, item_results)
                n_flagged = sum(1 for r in item_results if r.confidence != "ok")
                st.success(
                    f"Saved response #{response_id}: {len(item_results)} items detected, "
                    f"{n_flagged} flagged for review."
                )

        st.markdown("### Review a response")
        batches = list_batches(phase_id)
        if not batches:
            st.write("No batches processed yet for this phase.")
        else:
            batch_options = {f"#{b['id']} — {b['source_pdf_filename']} ({b['uploaded_at']})": b["id"] for b in batches}
            batch_label = st.selectbox("Batch", list(batch_options.keys()))
            batch_id = batch_options[batch_label]
            batch_row = next(b for b in batches if b["id"] == batch_id)

            responses = list_responses(batch_id)
            if not responses:
                st.write("No responses in this batch.")
            else:
                response_options = {f"Response #{r['id']}": r["id"] for r in responses}
                response_label = st.selectbox("Response", list(response_options.keys()))
                response_id = response_options[response_label]

                st.markdown("#### Demographic fields")
                st.caption(
                    "Not auto-detected in this version (no handwriting recognition — see PRODUCT.md). "
                    "Browse to the page with Part A: Demographic Information below and type in the values."
                )
                img_col, form_col = st.columns([1, 1])
                with img_col:
                    page_files = list_rendered_pages(batch_row["pages_dir"])
                    if page_files:
                        page_choice = st.selectbox(
                            "Reference page", page_files, key=f"demo_page_{response_id}"
                        )
                        st.image(
                            str(Path(batch_row["pages_dir"]) / page_choice),
                            width="stretch",
                        )
                    else:
                        st.write("No rendered pages found for this batch.")

                with form_col:
                    existing_demo = get_response_demo_values(response_id)
                    demo_input_values = {}
                    with st.form(key=f"demo_form_{response_id}"):
                        for df in phase_demo_fields:
                            current = existing_demo.get(df["id"], "")
                            if df["field_type"] == "single_choice" and df["options"]:
                                options_with_blank = [""] + df["options"]
                                idx = options_with_blank.index(current) if current in options_with_blank else 0
                                demo_input_values[df["id"]] = st.selectbox(
                                    df["label_en"], options_with_blank, index=idx, key=f"demo_{response_id}_{df['id']}"
                                )
                            else:
                                demo_input_values[df["id"]] = st.text_input(
                                    df["label_en"], value=current, key=f"demo_{response_id}_{df['id']}"
                                )
                        if st.form_submit_button("Save demographic fields"):
                            for demo_field_id, value in demo_input_values.items():
                                if value:
                                    save_response_demo_value(response_id, demo_field_id, value)
                            st.success("Demographic fields saved.")

                st.markdown("#### Likert items needing review")
                response_items = get_response_items(response_id)
                flagged = [ri for ri in response_items if ri["confidence"] != "ok"]
                if not flagged:
                    st.write("Nothing flagged — every item was detected with high confidence.")
                for ri in flagged:
                    with st.container(border=True):
                        st.markdown(f"**{ri['code']}** — {ri['statement_en']}")
                        st.caption(f"{ri['confidence']}: {ri['note']}")
                        crop = crop_source_region(batch_row["pages_dir"], ri["source"], ri["y"])
                        if crop is not None:
                            st.image(crop, width="stretch")
                        col1, col2 = st.columns([1, 3])
                        with col1:
                            corrected = st.selectbox(
                                "Value", [1, 2, 3, 4, 5],
                                index=(ri["value"] - 1) if ri["value"] else 0,
                                key=f"correct_{ri['id']}",
                            )
                        with col2:
                            st.write("")
                            if st.button("Confirm this value", key=f"confirmbtn_{ri['id']}"):
                                update_response_item(ri["id"], corrected, confidence="ok")
                                st.success(f"{ri['code']} confirmed as {corrected}.")
                                st.rerun()

                st.markdown("#### Full response")
                st.dataframe(
                    [
                        {"code": ri["code"], "value": ri["value"], "confidence": ri["confidence"]}
                        for ri in response_items
                    ],
                    hide_index=True,
                    width="stretch",
                )
