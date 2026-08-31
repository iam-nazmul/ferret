"""Ferret UI entry point.

Streamlit reruns the whole script on every interaction, so anything expensive goes
behind a cache decorator.
"""

import os

import streamlit as st

from ui.client import FerretClient
from ui.pages import admin, chat, memory
from ui.state import MESSAGES, THREAD_ID, TOKEN

st.set_page_config(page_title="Ferret", page_icon="🦡", layout="wide")

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")


@st.cache_resource
def get_client(token: str | None) -> FerretClient:
    return FerretClient(API_BASE, token)


def main() -> None:
    token = st.session_state.get(TOKEN) or os.environ.get("FERRET_TOKEN")
    client = get_client(token)

    with st.sidebar:
        st.title("🦡 Ferret")
        st.caption("Answers from your documents, with sources.")

        page = st.radio(
            "Navigation",
            ["Chat", "What Ferret knows about me", "Admin"],
            label_visibility="collapsed",
        )

        st.divider()
        if st.button("New conversation", use_container_width=True):
            st.session_state[MESSAGES] = []
            st.session_state[THREAD_ID] = None
            st.rerun()

    if page == "Chat":
        chat.render(client)
    elif page == "What Ferret knows about me":
        memory.render(client)
    else:
        admin.render(client)


if __name__ == "__main__":
    main()
