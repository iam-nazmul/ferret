"""THE security test.

Never skip, xfail, or "temporarily" disable this. A change that breaks it is a
data-exposure bug regardless of how it was introduced.
"""


from app.retrieval.hybrid import HybridRetriever
from tests.fixtures.corpus import fake_embedding, seed_two_tenant_corpus


async def _retrieve(session, query: str, groups: set[str]):
    retriever = HybridRetriever(session)
    return await retriever.retrieve_with_vector(
        fake_embedding(query), query, frozenset(groups)
    )


async def test_each_group_sees_only_its_own_documents(clean_session):
    corpus = await seed_two_tenant_corpus(clean_session)

    eng_results = await _retrieve(clean_session, "deployment approval", {"eng"})
    finance_results = await _retrieve(clean_session, "refund window", {"finance"})

    assert eng_results, "eng user should retrieve their own documents"
    assert all(c.document_id == corpus["eng_doc"].id for c in eng_results)

    assert finance_results, "finance user should retrieve their own documents"
    assert all(c.document_id == corpus["finance_doc"].id for c in finance_results)


async def test_other_groups_text_never_appears_in_results(clean_session):
    """Not just filtered out of the ranking — absent from the payload entirely."""
    corpus = await seed_two_tenant_corpus(clean_session)

    # Query using the *other* group's exact wording, to make leaking as likely as possible.
    results = await _retrieve(clean_session, corpus["finance_secret"], {"eng"})

    blob = " ".join(c.text for c in results)
    assert corpus["finance_secret"] not in blob
    assert "invoice date" not in blob


async def test_empty_groups_return_nothing_not_everything(clean_session):
    """The classic failure: 'if not groups: skip the predicate'."""
    await seed_two_tenant_corpus(clean_session)
    assert await _retrieve(clean_session, "refund window", set()) == []


async def test_membership_in_one_group_does_not_grant_the_other(clean_session):
    corpus = await seed_two_tenant_corpus(clean_session)
    results = await _retrieve(clean_session, "deployment rollback approval", {"finance"})
    assert all(c.document_id != corpus["eng_doc"].id for c in results)


async def test_multi_group_membership_unions_access(clean_session):
    corpus = await seed_two_tenant_corpus(clean_session)
    results = await _retrieve(clean_session, "policy", {"eng", "finance"})
    seen = {c.document_id for c in results}
    assert seen <= {corpus["eng_doc"].id, corpus["finance_doc"].id}


async def test_unindexed_documents_are_invisible(clean_session):
    """Failed and pending documents must not be retrievable at any ACL level."""
    from app.models import DocumentStatus
    from tests.fixtures.corpus import seed_document, seed_source

    source = await seed_source(clean_session, ["eng"])
    await seed_document(
        clean_session,
        source,
        title="Draft Policy",
        texts=["This draft mentions the secret rollback procedure."],
        status=DocumentStatus.FAILED.value,
    )
    await clean_session.commit()

    results = await _retrieve(clean_session, "secret rollback procedure", {"eng"})
    assert all("secret rollback" not in c.text for c in results)
