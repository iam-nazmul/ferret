"""The ENVIRONMENT=local backend: backend selection and document flattening.

No Ollama server is contacted — the suite must run offline.
"""

from app.config import Settings
from app.llm.client import LLMClient, get_client
from app.llm.documents import pack_context
from app.llm.ollama_client import OllamaClient, render_content
from tests.conftest import make_chunk


def _select(monkeypatch, environment: str):
    monkeypatch.setattr("app.llm.client.settings", Settings(environment=environment))
    get_client.cache_clear()
    try:
        return get_client()
    finally:
        get_client.cache_clear()


def test_local_environment_selects_ollama(monkeypatch):
    assert isinstance(_select(monkeypatch, "local"), OllamaClient)


def test_other_environments_stay_on_anthropic(monkeypatch):
    for env in ("development", "production"):
        assert isinstance(_select(monkeypatch, env), LLMClient)


def test_is_local_ignores_case_and_whitespace():
    assert Settings(environment=" Local ").is_local


def test_document_blocks_survive_flattening():
    content = pack_context([make_chunk(title="Refund Policy")], "How long is the window?")
    rendered = render_content(content)
    assert "Refund Policy" in rendered
    assert "How long is the window?" in rendered
    assert rendered.count("<document") == 1


def test_question_stays_after_the_documents():
    content = pack_context([make_chunk()], "q?", "memories")
    rendered = render_content(content)
    assert rendered.index("</document>") < rendered.index("q?")
