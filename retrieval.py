"""
اختيار أقرب سؤال من بنك الأسئلة لمهارات المرشح.
الآن يستخدم متجهات محليًا عبر Chroma و SentenceTransformers.
"""

import csv
import datetime
from pathlib import Path
from typing import Any

from chromadb import Client
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

from config import get_setting
from db.database import SessionLocal
from db.models import Job, Question
from reranker import rerank_documents

PERSIST_DIRECTORY = get_setting("CHROMA_PERSIST_DIR", "./chroma_store")
EMBEDDING_MODEL_NAME = get_setting("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
COLLECTION_NAME = get_setting("CHROMA_COLLECTION_NAME", "interview_documents")
RERANKER_TOP_N = int(get_setting("RERANKER_TOP_N", "20"))
RERANK_FUSION_ALPHA = float(get_setting("RERANK_FUSION_ALPHA", "0.7"))
RERANK_FEEDBACK_FILE = get_setting("RERANK_FEEDBACK_FILE", "./data/rerank_feedback.csv")

_embedding_model: SentenceTransformer | None = None
_client: Any = None


def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _embedding_model


def get_chroma_client():
    global _client
    if _client is None:
        _client = Client(
            settings=Settings(
                persist_directory=PERSIST_DIRECTORY,
                is_persistent=True,
                anonymized_telemetry=False,
            )
        )
    return _client


def get_collection():
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"source": "interview_documents"},
    )


def _ensure_feedback_file():
    path = Path(RERANK_FEEDBACK_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "timestamp",
                    "session_id",
                    "topic",
                    "difficulty",
                    "query_text",
                    "top_before",
                    "top_after",
                    "chosen_id",
                ]
            )


def log_rerank_feedback(
    session_id: str | int | None,
    topic: str,
    difficulty: str,
    query_text: str,
    top_before: str | None,
    top_after: str | None,
    chosen_id: str | None,
) -> None:
    _ensure_feedback_file()
    with Path(RERANK_FEEDBACK_FILE).open("a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                datetime.datetime.utcnow().isoformat(),
                session_id or "",
                topic,
                difficulty,
                query_text,
                top_before or "",
                top_after or "",
                chosen_id or "",
            ]
        )


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = get_embedding_model()
    embeddings = model.encode(texts, show_progress_bar=False, convert_to_numpy=False)
    return [emb.tolist() if hasattr(emb, "tolist") else emb for emb in embeddings]


def build_job_text(job: Job) -> str:
    required_topics = ", ".join(job.required_topics or []) if job.required_topics else ""
    return (
        f"{job.title}\n\n{job.description}\n\n"
        f"المواضيع المطلوبة: {required_topics}\n"
        f"المستوى: {job.difficulty}"
    )


def build_profile_text(candidate_profile: dict) -> str:
    if not candidate_profile:
        return ""

    lines = [
        f"مهارات: {', '.join(candidate_profile.get('skills', []))}",
        f"تقنيات: {', '.join(candidate_profile.get('technologies', []))}",
        f"لغات برمجة: {', '.join(candidate_profile.get('programming_languages', []))}",
        f"أطر عمل: {', '.join(candidate_profile.get('frameworks', []))}",
        f"سنوات خبرة تقريبية: {candidate_profile.get('work_experience_years', '')}",
        f"مشاريع: {', '.join([p.get('name', '') for p in candidate_profile.get('projects', []) if p.get('name')])}",
    ]
    return "\n".join([line for line in lines if line and not line.endswith(": ")])


def build_query_text(
    topic: str,
    candidate_profile: dict | None,
    candidate_keywords: list[str],
    job_context: str | None = None,
) -> str:
    profile_text = build_profile_text(candidate_profile or {})
    base = [f"الموضوع: {topic}"]
    if job_context:
        base.append(f"سياق الوظيفة:\n{job_context}")
    if candidate_keywords:
        base.append(f"الكلمات المفتاحية: {' '.join(candidate_keywords)}")
    if profile_text:
        base.append(f"بيانات المرشح:\n{profile_text}")
    return "\n".join(base).strip()


def _normalize_scores(scores: list[float]) -> list[float]:
    if not scores:
        return []
    min_score = min(scores)
    max_score = max(scores)
    if max_score == min_score:
        return [1.0 for _ in scores]
    return [(score - min_score) / (max_score - min_score) for score in scores]


def build_question_text(question: Question) -> str:
    expected_points = question.expected_points or []
    points_text = "\n".join(
        f"- {item['point']} (الوزن: {item.get('weight', 0):.0%})" for item in expected_points
    )
    text = f"{question.question}\n\nالنقاط المتوقعة:\n{points_text}"
    if question.sample_answer:
        text += f"\n\nمثال للإجابة:\n{question.sample_answer}"
    return text


def index_question_bank():
    db = SessionLocal()
    questions = db.query(Question).all()
    db.close()

    if not questions:
        return

    client = get_chroma_client()
    collection = get_collection()
    texts = []
    metadatas = []
    ids = []

    for question in questions:
        ids.append(f"question_{question.id}")
        texts.append(build_question_text(question))
        metadatas.append(
            {
                "source": "question",
                "question_id": question.id,
                "topic": question.topic,
                "difficulty": question.difficulty,
                "tags": question.tags or [],
            }
        )

    embeddings = embed_texts(texts)
    collection.upsert(
        ids=ids,
        documents=texts,
        metadatas=metadatas,
        embeddings=embeddings,
    )
    # Persist via the client for the current Chroma API
    try:
        client.persist()
    except Exception:
        pass


def index_job_descriptions():
    db = SessionLocal()
    jobs = db.query(Job).all()
    db.close()

    if not jobs:
        return

    client = get_chroma_client()
    collection = get_collection()
    ids = []
    texts = []
    metadatas = []

    for job in jobs:
        ids.append(f"job_{job.id}")
        texts.append(build_job_text(job))
        metadatas.append(
            {
                "source": "job",
                "job_id": job.id,
                "topic": ", ".join(job.required_topics or []),
                "difficulty": job.difficulty,
                "title": job.title,
            }
        )

    embeddings = embed_texts(texts)
    collection.upsert(
        ids=ids,
        documents=texts,
        metadatas=metadatas,
        embeddings=embeddings,
    )
    try:
        client.persist()
    except Exception:
        pass


def index_single_question(question) -> None:
    """
    فهرسة سؤال واحد بس - بتتنادى فورًا لحظة إضافة السؤال (من seed_questions.py مثلًا)
    بدل ما نستنى تشغيل index_documents.py يدوي على كل البنك.
    """
    client = get_chroma_client()
    collection = get_collection()

    text = build_question_text(question)
    embedding = embed_texts([text])[0]

    collection.upsert(
        ids=[f"question_{question.id}"],
        documents=[text],
        metadatas=[
            {
                "source": "question",
                "question_id": question.id,
                "topic": question.topic,
                "difficulty": question.difficulty,
                "tags": question.tags or [],
            }
        ],
        embeddings=[embedding],
    )
    try:
        client.persist()
    except Exception:
        pass


def index_single_job(job) -> None:
    """فهرسة وظيفة واحدة بس - بتتنادى فورًا لحظة إضافة الوظيفة من الـ API أو صفحة الإدارة"""
    client = get_chroma_client()
    collection = get_collection()

    text = build_job_text(job)
    embedding = embed_texts([text])[0]

    collection.upsert(
        ids=[f"job_{job.id}"],
        documents=[text],
        metadatas=[
            {
                "source": "job",
                "job_id": job.id,
                "topic": ", ".join(job.required_topics or []),
                "difficulty": job.difficulty,
                "title": job.title,
            }
        ],
        embeddings=[embedding],
    )
    try:
        client.persist()
    except Exception:
        pass


def index_candidate_profile(session_id: int | str, candidate_profile: dict):
    if not candidate_profile:
        return

    client = get_chroma_client()
    collection = get_collection()
    doc_id = f"cv_{session_id}"
    text = build_profile_text(candidate_profile)
    embedding = embed_texts([text])[0]

    collection.upsert(
        ids=[doc_id],
        documents=[text],
        metadatas=[
            {
                "source": "cv",
                "session_id": str(session_id),
                "skills": candidate_profile.get("skills", []),
                "technologies": candidate_profile.get("technologies", []),
                "programming_languages": candidate_profile.get("programming_languages", []),
                "frameworks": candidate_profile.get("frameworks", []),
            }
        ],
        embeddings=[embedding],
    )
    try:
        client.persist()
    except Exception:
        pass


def find_best_matching_question(
    topic: str,
    difficulty: str,
    candidate_keywords: list,
    exclude_ids: list | None = None,
    k: int = 5,
    candidate_profile: dict | None = None,
    session_id: int | str | None = None,
    job_context: str | None = None,
) -> list[dict[str, Any]]:
    """
    يبحث في الفهرس عن أفضل الأسئلة المتطابقة مع مهارات المرشح.
    يعيد قائمة من النتائج مع التشابه والبيانات الأصلية من قاعدة الأسئلة.
    """
    exclude_ids = exclude_ids or []
    collection = get_collection()
    query_text = build_query_text(topic, candidate_profile, candidate_keywords, job_context)

    def _query_with_filter(filter_metadata: dict[str, Any]) -> dict[str, Any]:
        query_embedding = embed_texts([query_text])[0]
        return collection.query(
            query_embeddings=[query_embedding],
            n_results=RERANKER_TOP_N + len(exclude_ids),
            where=filter_metadata,
            include=["documents", "metadatas", "distances"],
        )

    filter_metadata = {
        "$and": [
            {"source": "question"},
            {"topic": topic},
            {"difficulty": difficulty},
        ]
    }

    results = _query_with_filter(filter_metadata)

    ids = results.get("ids", [[]])[0]
    if not ids:
        fallback_filter = {
            "$and": [
                {"source": "question"},
                {"topic": topic},
            ]
        }
        results = _query_with_filter(fallback_filter)

    ids = results.get("ids", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]
    documents = results.get("documents", [[]])[0]

    filtered = []
    for question_id, metadata, score, document in zip(ids, metadatas, distances, documents):
        cleaned_id = question_id.replace("question_", "")
        if cleaned_id in exclude_ids:
            continue
        filtered.append((cleaned_id, metadata, score, document))

    if not filtered:
        return []

    db = SessionLocal()
    questions = {
        q.id: q
        for q in db.query(Question)
        .filter(Question.id.in_([item[0].replace("question_", "") for item in filtered]))
        .all()
    }
    db.close()

    if len(filtered) > 1:
        candidate_texts = []
        candidate_ids = []
        similarity_scores = []

        for question_id, metadata, score, document in filtered:
            question_id_clean = question_id.replace("question_", "")
            question = questions.get(question_id_clean)
            if question is None:
                continue
            candidate_ids.append(question_id_clean)
            candidate_texts.append(build_question_text(question))
            similarity_scores.append(1.0 / (1.0 + float(score)))

        rerank_scores = rerank_documents(query_text, candidate_texts)
        normalized_similarity = _normalize_scores(similarity_scores)
        normalized_rerank = _normalize_scores(rerank_scores)

        fused_scores = [
            RERANK_FUSION_ALPHA * r + (1 - RERANK_FUSION_ALPHA) * s
            for r, s in zip(normalized_rerank, normalized_similarity)
        ]

        reranked = sorted(
            zip(candidate_ids, candidate_texts, fused_scores, rerank_scores, similarity_scores),
            key=lambda item: item[2],
            reverse=True,
        )[:k]

        final_order = [
            (question_id, candidate_text, score)
            for question_id, candidate_text, score, *_ in reranked
        ]
        top_before = questions.get(candidate_ids[0]).question if candidate_ids else None
        top_after = questions.get(reranked[0][0]).question if reranked else None
        chosen_id = reranked[0][0] if reranked else None
        log_rerank_feedback(
            session_id, topic, difficulty, query_text, top_before, top_after, chosen_id
        )
    else:
        final_order = [
            (
                question_id,
                build_question_text(questions[question_id]),
                float(score),
            )
            for question_id, metadata, score, document in filtered
            if question_id in questions
        ]
        top_before = final_order[0][1] if final_order else None
        top_after = top_before
        chosen_id = final_order[0][0] if final_order else None
        log_rerank_feedback(
            session_id, topic, difficulty, query_text, top_before, top_after, chosen_id
        )

    matches = []
    for question_id, _, score in final_order:
        question = questions.get(question_id)
        if question is None:
            continue
        matches.append(
            {
                "id": question.id,
                "question": question.question,
                "expected_points": question.expected_points,
                "topic": question.topic,
                "difficulty": question.difficulty,
                "match_score": float(score),
            }
        )

    return matches
