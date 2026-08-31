"""What Ferret knows about me."""

import streamlit as st


def render(client) -> None:
    st.subheader("What Ferret knows about you")
    st.caption(
        "Facts kept across conversations to make follow-ups useful. Document contents are "
        "never stored here. Deleting a conversation does not delete these."
    )

    try:
        memories = client.memories()
    except Exception as exc:
        st.error(f"Couldn't load memories: {exc}")
        return

    if not memories:
        st.info("Nothing stored yet.")
        return

    for m in memories:
        cols = st.columns([8, 1])
        with cols[0]:
            st.markdown(f"- {m['data']}")
        with cols[1]:
            if st.button("✕", key=f"del_{m['id']}", help="Delete"):
                client.delete_memory(m["id"])
                st.rerun()

    st.divider()
    if st.button("Clear everything", type="secondary"):
        count = client.clear_memories()
        st.success(f"Deleted {count} memories.")
        st.rerun()
