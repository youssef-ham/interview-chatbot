"""
تقييم طرق الاسترجاع المختلفة: vector-only مقابل vector + reranking.
المقياس: Hit Rate@5 و MRR، باستخدام كل سؤال في البنك كـ query لنفسه
(الافتراض: أفضل نتيجة السترجاع لسؤال ما هي السؤال نفسه أو سؤال قريب جدًا منه).

شغّله بـ:
python scr/evaluate_retrieval.py
"""

import os
import random
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import SessionLocal
from db.models import Question
from reranker import rerank_documents
from retrieval import embed_texts, get_collection

random.seed(42)
K = 5
SAMPLE_SIZE = 100  # عدد الأسئلة المستخدمة كعينة تقييم


def build_realistic_query(q: Question) -> str:
    """يبني query واقعي زي اللي بيتبني وقت الاستخدام الحقيقي (موضوع + كلمات دلالية من
    السؤال)، بدل استخدام نص السؤال بالكامل زي ما هو مفهرس - عشان التقييم يكون له معنى."""
    tags_text = " ".join(q.tags or [])
    return f"Topic: {q.topic}\nDifficulty: {q.difficulty}\nCandidate keywords: {tags_text} {q.subtopic or ''}".strip()


def load_eval_set():
    db = SessionLocal()
    questions = db.query(Question).all()
    db.close()
    sample = random.sample(questions, min(SAMPLE_SIZE, len(questions)))
    return sample


def evaluate(method: str, questions):
    collection = get_collection()
    hits, reciprocal_ranks = 0, []

    for q in questions:
        query_text = build_realistic_query(q)
        query_embedding = embed_texts([query_text])[0]

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=20,
            where={"$and": [{"source": "question"}, {"topic": q.topic}]},
            include=["documents", "metadatas", "distances"],
        )
        ids = [i.replace("question_", "") for i in results.get("ids", [[]])[0]]
        docs = results.get("documents", [[]])[0]

        if method == "rerank" and len(ids) > 1:
            scores = rerank_documents(query_text, docs)
            ids = [x for _, x in sorted(zip(scores, ids), reverse=True)]

        ids = ids[:K]
        rank = ids.index(q.id) + 1 if q.id in ids else None
        if rank:
            hits += 1
            reciprocal_ranks.append(1.0 / rank)
        else:
            reciprocal_ranks.append(0.0)

    hit_rate = hits / len(questions)
    mrr = sum(reciprocal_ranks) / len(reciprocal_ranks)
    return hit_rate, mrr


def main():
    questions = load_eval_set()
    print(f"Evaluating on {len(questions)} sampled questions (k={K})\n")

    for method in ["vector_only", "rerank"]:
        hit_rate, mrr = evaluate(method, questions)
        print(f"{method:15s} -> Hit Rate@{K}: {hit_rate:.3f} | MRR: {mrr:.3f}")


if __name__ == "__main__":
    main()