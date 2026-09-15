"""A minimal shared-password gate for the deployed app.

Streamlit Community Cloud's free tier no longer offers native private-app /
per-viewer access control (that moved to the paid "Streamlit in Snowflake"
product - verified directly against the actual deploy UI, not just docs,
2026-09-15). This is the fallback: one shared password for the whole team,
stored in Streamlit secrets (APP_PASSWORD) - never in code or git. Locally,
set it in .streamlit/secrets.toml (gitignored); on Streamlit Cloud, set it
in the app's Settings -> Secrets.

This is deliberately simple - one password, no per-person accounts, no
password hashing/rotation. Good enough for "a small named team, not the
public," not a substitute for real auth if the audience or sensitivity
changes later.
"""
import streamlit as st


def require_login() -> None:
    if st.session_state.get("authenticated"):
        return

    st.title("Questionnaire Digitizer")
    st.subheader("Sign in")

    if "APP_PASSWORD" not in st.secrets:
        st.error(
            "No APP_PASSWORD configured. Set it in .streamlit/secrets.toml locally, "
            "or in this app's Settings -> Secrets on Streamlit Cloud."
        )
        st.stop()

    password = st.text_input("Password", type="password")
    if st.button("Sign in"):
        if password == st.secrets["APP_PASSWORD"]:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    st.stop()


def logout_button() -> None:
    with st.sidebar:
        if st.button("Log out"):
            st.session_state["authenticated"] = False
            st.rerun()
