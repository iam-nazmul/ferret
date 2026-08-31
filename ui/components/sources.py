"""The sources panel — transparency, and the fastest debugging surface we have."""

import streamlit as st


def render_sources(sources: list[dict]) -> None:
    if not sources:
        st.caption("No sources used.")
        return

    st.subheader(f"Sources ({len(sources)})")
    for i, s in enumerate(sources, 1):
        title = s.get("title") or s.get("uri", "")
        heading = " > ".join(s.get("heading_path") or [])
        score = s.get("rerank_score")

        with st.container(border=True):
            st.markdown(f"**{i}. {title}**")
            if heading:
                st.caption(heading)
            st.caption(s.get("snippet", "")[:220] + "…")
            cols = st.columns([3, 1])
            with cols[0]:
                st.link_button("Open", _link(s), use_container_width=True)
            with cols[1]:
                if score is not None:
                    st.caption(f"{score:.2f}")


def _link(source: dict) -> str:
    uri = source.get("uri", "#")
    loc = source.get("locator") or {}
    if "page" in loc:
        return f"{uri}#page={loc['page']}"
    if loc.get("anchor"):
        return f"{uri}#{str(loc['anchor']).lstrip('#')}"
    return uri
