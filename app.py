import tempfile
import time
from pathlib import Path

import streamlit as st

from db import (
    init_db, create_phase, list_phases, save_schema, get_items, get_demo_fields, get_phase,
    create_batch, list_batches, create_response, list_responses, get_response,
    save_response_items, get_response_items, update_response_item,
    save_response_demo_value, get_response_demo_values,
)
from parse_docx import parse_phase_docx, SchemaParseError
from checkbox_pipeline import align_document_to_items, crop_source_region, list_rendered_pages
from export import export_response_to_bytes, export_batch_to_bytes
from schema_loader import load_schemas_from_disk
from auth import require_login, logout_button
from PIL import Image

st.set_page_config(page_title="Questionnaire Digitizer", page_icon="\U0001F4CB")

require_login()
logout_button()

init_db()
load_schemas_from_disk()

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

        st.markdown("### Upload scanned questionnaire PDFs")
        st.caption("One PDF per respondent. Upload as many at once as you have for this batch of scans.")
        pdf_uploads = st.file_uploader(
            "Scanned PDFs", type=["pdf"], accept_multiple_files=True, key="pdf_upload"
        )
        if pdf_uploads and st.button(f"Process {len(pdf_uploads)} PDF(s)"):
            batch_dir = DATA_DIR / f"phase{phase_id}_{int(time.time())}"
            batch_dir.mkdir(parents=True, exist_ok=True)
            batch_id = create_batch(phase_id, label=f"{len(pdf_uploads)} file(s) uploaded {time.strftime('%Y-%m-%d %H:%M')}")

            results_summary = []
            for pdf_upload in pdf_uploads:
                response_dir = batch_dir / Path(pdf_upload.name).stem
                response_dir.mkdir(parents=True, exist_ok=True)
                pdf_path = response_dir / pdf_upload.name
                pdf_path.write_bytes(pdf_upload.getvalue())

                with st.spinner(f"Detecting checkbox grid in {pdf_upload.name}..."):
                    item_results, raw = align_document_to_items(str(pdf_path), phase_items, str(response_dir))

                if item_results is None:
                    results_summary.append({
                        "file": pdf_upload.name, "status": "FAILED to align",
                        "detail": f"detected {raw.total_ticks_detected}, expected {raw.total_expected}",
                    })
                else:
                    response_id = create_response(
                        batch_id, source_pdf_filename=pdf_upload.name, pages_dir=str(response_dir),
                        respondent_label=Path(pdf_upload.name).stem,
                    )
                    save_response_items(response_id, item_results)
                    n_flagged = sum(1 for r in item_results if r.confidence != "ok")
                    results_summary.append({
                        "file": pdf_upload.name, "status": f"response #{response_id}",
                        "detail": f"{len(item_results)} items, {n_flagged} flagged",
                    })

            st.success(f"Processed {len(pdf_uploads)} file(s) into batch #{batch_id}.")
            st.table(results_summary)

        st.markdown("### Review a response")
        batches = list_batches(phase_id)
        if not batches:
            st.write("No batches processed yet for this phase.")
        else:
            batch_options = {f"#{b['id']} — {b['label']} ({b['uploaded_at']})": b["id"] for b in batches}
            batch_label = st.selectbox("Batch", list(batch_options.keys()))
            batch_id = batch_options[batch_label]

            responses = list_responses(batch_id)
            if not responses:
                st.write("No responses in this batch.")
            else:
                phase_row = get_phase(phase_id)
                batch_excel_bytes = export_batch_to_bytes(phase_id, phase_row["name"], batch_id)
                st.download_button(
                    f"Download cumulative Excel export for this batch ({len(responses)} respondent(s))",
                    data=batch_excel_bytes,
                    file_name=f"{phase_row['name'].replace(' ', '_')}_batch{batch_id}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

                response_options = {
                    f"Response #{r['id']} — {r['respondent_label'] or r['source_pdf_filename']}": r["id"]
                    for r in responses
                }
                response_label = st.selectbox("Response", list(response_options.keys()))
                response_id = response_options[response_label]
                response_row = get_response(response_id)

                st.markdown("#### Demographic fields")
                st.caption(
                    "Not auto-detected in this version (no handwriting recognition — see PRODUCT.md). "
                    "Browse to the page with Part A: Demographic Information below and type in the values."
                )
                img_col, form_col = st.columns([1, 1])
                with img_col:
                    page_files = list_rendered_pages(response_row["pages_dir"])
                    if page_files:
                        page_choice = st.selectbox(
                            "Reference page", page_files, key=f"demo_page_{response_id}"
                        )
                        st.image(
                            str(Path(response_row["pages_dir"]) / page_choice),
                            width="stretch",
                        )
                    else:
                        st.write("No rendered pages found for this response.")

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
                        crop = crop_source_region(response_row["pages_dir"], ri["source"], ri["y"])
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

                n_unresolved = sum(1 for ri in response_items if ri["confidence"] != "ok")
                if n_unresolved:
                    st.warning(f"{n_unresolved} item(s) above are still flagged — export will include them as-is.")
                excel_bytes = export_response_to_bytes(
                    phase_id, phase_row["name"], response_row["source_pdf_filename"], response_id
                )
                st.download_button(
                    "Download Excel export for this response only",
                    data=excel_bytes,
                    file_name=f"{phase_row['name'].replace(' ', '_')}_response{response_id}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
