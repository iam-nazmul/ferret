"""Principal derivation. Groups come from the verified claim and nowhere else."""

from app.api.auth import principal_from_claims
from app.api.schemas import ChatRequest
from app.config import settings


def test_groups_come_from_the_configured_claim():
    p = principal_from_claims({"sub": "u1", settings.oidc_group_claim: ["eng", "all"]})
    assert p.groups == frozenset({"eng", "all"})
    assert p.user_id == "u1"


def test_comma_separated_claim_is_supported():
    p = principal_from_claims({"sub": "u1", settings.oidc_group_claim: "eng, all"})
    assert p.groups == frozenset({"eng", "all"})


def test_missing_claim_yields_no_groups_not_all_groups():
    """Fail closed: no group claim must mean no access, never universal access."""
    assert principal_from_claims({"sub": "u1"}).groups == frozenset()


def test_admin_requires_the_admin_group():
    assert not principal_from_claims({"sub": "u", settings.oidc_group_claim: ["eng"]}).is_admin
    assert principal_from_claims(
        {"sub": "u", settings.oidc_group_claim: [settings.oidc_admin_group]}
    ).is_admin


def test_chat_request_schema_has_no_acl_fields():
    """If a caller could pass groups, a caller could forge them."""
    fields = set(ChatRequest.model_fields)
    assert not fields & {"user_id", "user_groups", "groups", "acl_groups", "is_admin"}


def test_unknown_request_fields_are_ignored_not_bound():
    req = ChatRequest.model_validate(
        {"message": "hi", "user_groups": ["admin"], "is_admin": True}
    )
    assert not hasattr(req, "user_groups")
    assert not hasattr(req, "is_admin")
