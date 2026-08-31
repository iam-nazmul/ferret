"""Admin tab. Hidden here AND role-gated server-side — hiding alone is not authorization."""

import streamlit as st


def render(client) -> None:
    st.subheader("Sources")

    try:
        sources = client.sources()
    except Exception as exc:
        st.error(f"Couldn't load sources: {exc}")
        return

    for s in sources:
        with st.container(border=True):
            cols = st.columns([4, 2, 2, 2])
            with cols[0]:
                st.markdown(f"**{s['uri']}**")
                st.caption(s["kind"])
            with cols[1]:
                st.metric("Documents", s["document_count"])
            with cols[2]:
                st.metric("Failed", s["failed_count"])
            with cols[3]:
                st.caption(f"Last run: {s['last_run_at'] or 'never'}")
                if st.button("Reindex now", key=f"ri_{s['id']}"):
                    client.reindex(s["id"])
                    st.success("Queued.")

            if s["failed_count"]:
                with st.expander(f"{s['failed_count']} failures"):
                    for f in client.failures(s["id"]):
                        st.markdown(f"- `{f['uri']}` — {f['error']}")

    st.divider()
    st.subheader("Upload a PDF")
    with st.form("upload"):
        file = st.file_uploader("PDF", type=["pdf"])
        acl = st.text_input("ACL groups (comma-separated)", value="")
        doc_type = st.selectbox("Document type", ["policy", "contract", "report", "manual"])
        submitted = st.form_submit_button("Upload")

    if submitted:
        if not file:
            st.error("Choose a file.")
        elif not acl.strip():
            # Deliberately no default: an over-broad ACL is a data-exposure bug.
            st.error("ACL groups are required — set who should be able to see this document.")
        else:
            try:
                result = client.upload(file.name, file.getvalue(), acl, doc_type)
                st.success(f"Indexed {result['chunks']} chunks.")
            except Exception as exc:
                st.error(f"Upload failed: {exc}")
