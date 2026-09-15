import streamlit as st
from db import init_db, create_phase, list_phases

st.set_page_config(page_title="Questionnaire Digitizer", page_icon="\U0001F4CB")

init_db()

st.title("Questionnaire Digitizer")
st.caption("Component 1 walking skeleton: upload a phase's .docx template, confirm it's stored.")

uploaded = st.file_uploader("Phase template (.docx)", type=["docx"])

if uploaded is not None:
    default_name = uploaded.name.rsplit(".", 1)[0]
    phase_name = st.text_input("Phase name", value=default_name)
    if st.button("Save phase"):
        phase_id = create_phase(name=phase_name, source_docx_filename=uploaded.name)
        st.success(f"Saved phase #{phase_id}: {phase_name} ({uploaded.name})")

st.subheader("Phases stored so far")
phases = list_phases()
if not phases:
    st.write("No phases yet.")
else:
    st.table(
        [
            {
                "id": p["id"],
                "name": p["name"],
                "source file": p["source_docx_filename"],
                "uploaded at": p["uploaded_at"],
            }
            for p in phases
        ]
    )
