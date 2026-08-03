"""
اختيار أقرب سؤال من بنك الأسئلة لمهارات المرشح.
الآن يستخدم متجهات محليًا عبر Chroma و SentenceTransformers.
"""

import csv
import datetime
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from config import get_setting

logger = logging.getLogger("interview_bot.retrieval")
from db.database import SessionLocal
from db.models import Job, Question
from reranker import rerank_documents

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

_chromadb_import_error = None
try:
    from chromadb import Client
    from chromadb.config import Settings
except ImportError as exc:  # pragma: no cover
    Client = None
    Settings = None
    _chromadb_import_error = exc

try:
    from sentence_transformers import SentenceTransformer
except ImportError as exc:  # pragma: no cover
    SentenceTransformer = None
    _sentence_transformers_import_error = exc

try:
    from rank_bm25 import BM25Okapi
except ImportError as exc:  # pragma: no cover
    BM25Okapi = None
    _bm25_import_error = exc

PERSIST_DIRECTORY = get_setting("CHROMA_PERSIST_DIR", "./chroma_store")
EMBEDDING_MODEL_NAME = get_setting("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
COLLECTION_NAME = get_setting("CHROMA_COLLECTION_NAME", "interview_documents")
RERANKER_TOP_N = int(get_setting("RERANKER_TOP_N", "20"))
RERANK_FUSION_ALPHA = float(get_setting("RERANK_FUSION_ALPHA", "0.7"))
# وزن الدمج بين البحث النصي (BM25) والبحث بالمتجهات (vector). 1.0 = اعتماد كامل على vector،
# 0.0 = اعتماد كامل على BM25. القيمة الافتراضية توزيع متوازن بين الاتنين.
HYBRID_FUSION_ALPHA = float(get_setting("HYBRID_FUSION_ALPHA", "0.5"))
RERANK_FEEDBACK_FILE = get_setting("RERANK_FEEDBACK_FILE", "./data/rerank_feedback.csv")

_embedding_model: Any = None
_client: Any = None


def get_embedding_model():
    global _embedding_model
    if SentenceTransformer is None:
        raise RuntimeError(
            "SentenceTransformers is not installed. Install sentence-transformers to enable embedding generation."
        )
    if _embedding_model is None:
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _embedding_model


def get_chroma_client():
    global _client
    if Client is None or Settings is None:
        message = (
            "chromadb is not installed. Install chromadb in your environment "
            "to enable RAG retrieval and indexing."
        )
        if _chromadb_import_error is not None:
            raise RuntimeError(message) from _chromadb_import_error
        raise RuntimeError(message)

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
    """Return a textual representation of the job for use in embedding/ranking.

    This is intentionally plain English so generated questions and context are
    in English for downstream models and prompts.
    """
    required_topics = ", ".join(job.required_topics or []) if job.required_topics else ""
    return (
        f"{job.title}\n\n{job.description}\n\n"
        f"Required topics: {required_topics}\n"
        f"Level: {job.difficulty}"
    )


def build_profile_text(candidate_profile: dict) -> str:
    if not candidate_profile:
        return ""

    lines = [
        f"Skills: {', '.join(candidate_profile.get('skills', []))}",
        f"Technologies: {', '.join(candidate_profile.get('technologies', []))}",
        f"Programming languages: {', '.join(candidate_profile.get('programming_languages', []))}",
        f"Frameworks: {', '.join(candidate_profile.get('frameworks', []))}",
        f"Approx. years of experience: {candidate_profile.get('work_experience_years', '')}",
        f"Projects: {', '.join([p.get('name', '') for p in candidate_profile.get('projects', []) if p.get('name')])}",
    ]
    return "\n".join([line for line in lines if line and not line.endswith(": ")])


def build_query_text(
    topic: str,
    candidate_profile: dict | None,
    candidate_keywords: list[str],
    job_context: str | None = None,
) -> str:
    """Assemble the user query text used for retrieval (English).

    Contains topic, optional job context, candidate keywords, and a short
    profile summary when available.
    """
    profile_text = build_profile_text(candidate_profile or {})
    base = [f"Topic: {topic}"]
    if job_context:
        base.append(f"Job context:\n{job_context}")
    if candidate_keywords:
        base.append(f"Candidate keywords: {' '.join(candidate_keywords)}")
    if profile_text:
        base.append(f"Candidate profile:\n{profile_text}")
    return "\n".join(base).strip()


def _normalize_scores(scores: list[float]) -> list[float]:
    if not scores:
        return []
    min_score = min(scores)
    max_score = max(scores)
    if max_score == min_score:
        return [1.0 for _ in scores]
    return [(score - min_score) / (max_score - min_score) for score in scores]


def bm25_scores(query_text: str, candidate_texts: list[str]) -> list[float]:
    """يحسب درجة تطابق نصي (lexical) بين الـ query ومجموعة مرشحين باستخدام BM25.
    ده بيمثل شق الـ 'text search' في الـ hybrid search - بيمسك تطابق كلمات حرفي
    (زي اسم تقنية أو مصطلح تقني بالظبط) اللي ممكن الـ vector search يفوّته أحيانًا.

    لو مكتبة rank_bm25 مش متاحة، بيرجع أصفار (يعني الاعتماد الكامل هيبقى على vector).
    """
    if BM25Okapi is None or not candidate_texts:
        return [0.0 for _ in candidate_texts]

    tokenized_corpus = [text.lower().split() for text in candidate_texts]
    bm25 = BM25Okapi(tokenized_corpus)
    tokenized_query = query_text.lower().split()
    return list(bm25.get_scores(tokenized_query))


def build_question_text(question: Question) -> str:
    expected_points = question.expected_points or []
    points_text = "\n".join(
        f"- {item['point']} (weight: {item.get('weight', 0):.0%})" for item in expected_points
    )
    text = f"{question.question}\n\nExpected points:\n{points_text}"
    if question.sample_answer:
        text += f"\n\nSample answer:\n{question.sample_answer}"
    return text


def _fallback_questions_from_db(
    topic: str,
    difficulty: str,
    exclude_ids: list | None = None,
    k: int = 5,
) -> list[dict[str, Any]]:
    exclude_ids = {str(item) for item in (exclude_ids or [])}
    db = SessionLocal()
    try:
        query = db.query(Question)
        if difficulty:
            query = query.filter(Question.difficulty == difficulty)
        if topic:
            query = query.filter(Question.topic == topic)
        candidates = query.order_by(Question.id.asc()).all()
        if not candidates and topic:
            candidates = (
                db.query(Question).filter(Question.topic == topic).order_by(Question.id.asc()).all()
            )
        if not candidates:
            candidates = db.query(Question).order_by(Question.id.asc()).all()

        filtered = [question for question in candidates if str(question.id) not in exclude_ids]
        selected = filtered[:k]
        if not selected and filtered:
            selected = filtered[:1]

        matches = []
        for question in selected:
            matches.append(
                {
                    "id": question.id,
                    "question": question.question,
                    "expected_points": question.expected_points,
                    "topic": question.topic,
                    "difficulty": question.difficulty,
                    "match_score": 1.0,
                }
            )
        return matches
    finally:
        db.close()


def index_question_bank():
    db = SessionLocal()
    questions = db.query(Question).all()
    db.close()

    if not questions:
        return

    try:
        client = get_chroma_client()
        collection = get_collection()
    except Exception:
        return

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

    try:
        client = get_chroma_client()
        collection = get_collection()
    except Exception:
        return

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
    try:
        client = get_chroma_client()
        collection = get_collection()
    except Exception:
        return

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
    try:
        client = get_chroma_client()
        collection = get_collection()
    except Exception:
        return

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

    try:
        client = get_chroma_client()
        collection = get_collection()
    except Exception:
        return

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
    query_text = build_query_text(topic, candidate_profile, candidate_keywords, job_context)

    try:
        collection = get_collection()
    except Exception:
        logger.exception(
            "Failed to get Chroma collection - falling back to plain DB questions "
            "(no semantic matching, no personalization based on retrieval)"
        )
        return _fallback_questions_from_db(topic, difficulty, exclude_ids, k)

    try:

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
    except Exception:
        logger.exception(
            "Chroma query failed - falling back to plain DB questions "
            "(no semantic matching, no personalization based on retrieval)"
        )
        return _fallback_questions_from_db(topic, difficulty, exclude_ids, k)
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

        # Hybrid search: ندمج البحث النصي (BM25) مع البحث بالمتجهات (vector similarity)
        # قبل ما ندخل على الـ cross-encoder reranker. كده الدرجة النهائية بتاخد في الاعتبار
        # التطابق الدلالي (vector) والتطابق الحرفي في الكلمات (BM25) مع بعض.
        lexical_scores = bm25_scores(query_text, candidate_texts)
        normalized_lexical = _normalize_scores(lexical_scores)
        normalized_similarity_raw = _normalize_scores(similarity_scores)
        hybrid_scores = [
            HYBRID_FUSION_ALPHA * v + (1 - HYBRID_FUSION_ALPHA) * b
            for v, b in zip(normalized_similarity_raw, normalized_lexical)
        ]

        rerank_scores = rerank_documents(query_text, candidate_texts)
        normalized_similarity = _normalize_scores(hybrid_scores)
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