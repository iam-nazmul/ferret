"""Cross-encoder reranking service.

Separate from the API so it can be scheduled onto a GPU node independently, and so a
cold start degrades ranking rather than taking the API down.
"""

import os

from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import CrossEncoder

MODEL_NAME = os.environ.get("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")

app = FastAPI(title="ferret-reranker")
_model: CrossEncoder | None = None


class RerankRequest(BaseModel):
    query: str
    documents: list[str]
    top_k: int = 8


@app.on_event("startup")
def load_model() -> None:
    global _model
    _model = CrossEncoder(MODEL_NAME, max_length=512)


@app.get("/healthz")
def healthz() -> dict:
    # Readiness only after the model is loaded — cold start is ~30s.
    return {"status": "ok" if _model is not None else "loading"}


@app.post("/rerank")
def rerank(body: RerankRequest) -> dict:
    if _model is None:
        return {"results": [{"index": i, "score": 0.0} for i in range(len(body.documents))]}

    scores = _model.predict([(body.query, d) for d in body.documents])
    ranked = sorted(enumerate(scores), key=lambda p: p[1], reverse=True)[: body.top_k]
    return {"results": [{"index": i, "score": float(s)} for i, s in ranked]}
