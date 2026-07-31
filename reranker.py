"""
Rerank candidate questions using a cross-encoder model.
"""

import os
from typing import Any

from sentence_transformers import CrossEncoder

RERANKER_MODEL_NAME = os.getenv("RERANKER_MODEL_NAME", "cross-encoder/ms-marco-MiniLM-L-6-v2")

_reranker_model: Any = None


def get_reranker_model():
    global _reranker_model
    if _reranker_model is None:
        _reranker_model = CrossEncoder(RERANKER_MODEL_NAME, device="cpu")
    return _reranker_model


def rerank_documents(query: str, documents: list[str], batch_size: int = 16) -> list[float]:
    """Return a reranking score for each document given the query."""
    model = get_reranker_model()
    pairs = [(query, doc) for doc in documents]
    scores = model.predict(pairs, batch_size=batch_size, convert_to_numpy=True)
    return [float(score) for score in scores]
