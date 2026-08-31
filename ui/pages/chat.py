"""Chat page."""

import streamlit as st

from ui.components.citations import render_answer
from ui.components.sources import render_sources
from ui.state import EXAMPLE_QUESTIONS, FILTERS, MESSAGES, THREAD_ID


def render(client) -> None:
    messages = st.session_state.setdefault(MESSAGES, [])

    chat_col, source_col = st.columns([3, 2], gap="large")

    with chat_col:
        if not messages:
            _empty_state()

        for msg in messages:
            with st.chat_message(msg["role"]):
                if msg["role"] == "assistant":
                    render_answer(
                        msg["content"], msg.get("citations", []), msg.get("violation", False)
                    )
                    _feedback_buttons(client, msg)
                else:
                    st.markdown(msg["content"])

        _filters()

        if prompt := st.chat_input("Ask about your documents…"):
            _ask(client, prompt)
            st.rerun()

    with source_col:
        last = next((m for m in reversed(messages) if m["role"] == "assistant"), None)
        render_sources(last.get("sources", []) if last else [])


def _empty_state() -> None:
    st.markdown("#### Ask about your documents")
    st.caption("Every answer comes with sources you can check. Try one of these:")
    for q in EXAMPLE_QUESTIONS:
        if st.button(q, use_container_width=True, key=f"ex_{hash(q)}"):
            st.session_state["_pending"] = q
            st.rerun()


def _filters() -> None:
    with st.expander("Filters"):
        cols = st.columns(2)
        with cols[0]:
            doc_type = st.multiselect(
                "Document type", ["policy", "contract", "report", "manual"], key="f_doc_type"
            )
        with cols[1]:
            effective_after = st.date_input("Effective after", value=None, key="f_after")

        filters: dict = {}
        if doc_type:
            filters["doc_type"] = doc_type
        if effective_after:
            filters["effective_after"] = str(effective_after)
        st.session_state[FILTERS] = filters


def _ask(client, prompt: str) -> None:
    messages = st.session_state[MESSAGES]
    messages.append({"role": "user", "content": prompt})

    result = {"answer": "", "sources": [], "citations": [], "run_id": "", "violation": False}
    placeholder = st.empty()

    for event, payload in client.chat(
        prompt, st.session_state.get(THREAD_ID), st.session_state.get(FILTERS)
    ):
        if event == "status":
            placeholder.caption(f"{payload['stage'].title()}…")
        elif event == "sources":
            result["sources"] = payload["sources"]
        elif event == "token":
            result["answer"] += payload["text"]
            placeholder.markdown(result["answer"])
        elif event == "citation":
            result["citations"].append(payload)
        elif event == "done":
            result["run_id"] = payload["run_id"]
            result["violation"] = payload.get("groundedness_violation", False)
        elif event == "error":
            result["answer"] = f"⚠️ {payload['message']}"
        # Unknown events are ignored by design — forward compatibility with the API.

    placeholder.empty()
    messages.append({"role": "assistant", **result})


def _feedback_buttons(client, msg: dict) -> None:
    run_id = msg.get("run_id")
    if not run_id or msg.get("_rated"):
        return

    cols = st.columns([1, 1, 8])
    with cols[0]:
        if st.button("👍", key=f"up_{run_id}"):
            client.feedback(run_id, st.session_state.get(THREAD_ID, ""), 1)
            msg["_rated"] = True
            st.rerun()
    with cols[1]:
        if st.button("👎", key=f"down_{run_id}"):
            st.session_state[f"comment_{run_id}"] = True

    if st.session_state.get(f"comment_{run_id}"):
        comment = st.text_input("What went wrong?", key=f"c_{run_id}")
        if st.button("Send", key=f"send_{run_id}"):
            client.feedback(run_id, st.session_state.get(THREAD_ID, ""), -1, comment)
            msg["_rated"] = True
            st.session_state[f"comment_{run_id}"] = False
            st.rerun()
