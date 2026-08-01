"""
Rerank candidate questions using a cross-encoder model.
"""

from typing import Any

from config import get_setting

RERANKER_MODEL_NAME = get_setting("RERANKER_MODEL_NAME", "cross-encoder/ms-marco-MiniLM-L-6-v2")

_reranker_model: Any = None


def get_reranker_model():
    global _reranker_model
    if _reranker_model is None:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError(
                "Missing sentence-transformers package. Install sentence-transformers "
                "to enable reranking in this app."
            ) from exc

        _reranker_model = CrossEncoder(RERANKER_MODEL_NAME, device="cpu")
    return _reranker_model


def rerank_documents(query: str, documents: list[str], batch_size: int = 16) -> list[float]:
    """Return a reranking score for each document given the query.

    If the optional cross-encoder dependency is unavailable, fall back to a simple
    lexical overlap heuristic so the app keeps working without the heavy reranker.
    """
    try:
        model = get_reranker_model()
    except RuntimeError:
        query_tokens = {token.lower() for token in query.replace("\n", " ").split() if token}
        scores = []
        for document in documents:
            doc_tokens = {token.lower() for token in document.replace("\n", " ").split() if token}
            overlap = len(query_tokens & doc_tokens)
            scores.append(float(overlap))
        return scores

    pairs = [(query, doc) for doc in documents]
    scores = model.predict(pairs, batch_size=batch_size, convert_to_numpy=True)
    return [float(score) for score in scores]
