"""
AI helper functions for question generation, answer evaluation, and report creation.
"""

import json
import re

from db.database import SessionLocal
from db.models import InterviewSession, Job
from providers import generate
from retrieval import build_job_text, find_best_matching_question


def clean_json(raw_text: str) -> dict:
    cleaned = re.sub(r"```json\s*|\s*```", "", raw_text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        json_block = re.search(r"\{.*\}", cleaned, flags=re.S)
        if json_block:
            return json.loads(json_block.group(0))
        raise


QUESTION_SYSTEM_PROMPT = """You are a senior technical interviewer.
Your task: generate exactly one interview question.

Strict rules:
- Return JSON only, with no extra text outside the JSON.
- Answer in English only.
- The exact required format is:
{"question": "question text", "expected_points": [{"point": "point 1", "weight": 0.5}, {"point": "point 2", "weight": 0.3}, {"point": "point 3", "weight": 0.2}]}
- Provide 3 clear technical expected points, and weights must sum to exactly 1.0.
- Place the highest weight on the most important technical point."""


async def generate_question(topic: str, difficulty: str, exclude_ids: list = None) -> dict:
    """
    First attempt to fetch a real question from the question bank using RAG.
    If no suitable bank question exists, fall back to model generation.
    If the question is from the bank, use question rewriting to personalize it.
    """
    matches = find_best_matching_question(topic, difficulty, [], exclude_ids)
    if matches:
        selected = matches[0]
        try:
            from question_rewriter import rewrite_question

            selected["question"] = await rewrite_question(
                selected["question"],
                {},
                reference_questions=matches[:3],
                previous_answers=[],
            )
        except Exception:
            pass
        return selected

    # Fallback path: no matching questions in the bank, generate one with the model
    user_prompt = f"Topic: {topic}\nDifficulty: {difficulty}\nGenerate one interview question now."
    raw_response = await generate(QUESTION_SYSTEM_PROMPT, user_prompt)
    question_data = clean_json(raw_response)
    question_data["id"] = None  # No id because it is not from the bank
    return question_data


EVAL_SYSTEM_PROMPT = """You are a precise and objective technical evaluator.
Evaluate the candidate's answer only against the expected points.

Strict rules:
- Return JSON only, with no extra text outside the JSON.
- Answer in English only.
- The exact required format is:
{"score": number from 0 to 10, "missing_points": ["missing points"], "feedback": "short feedback in English"}
- If the answer is empty, score = 0."""

EVAL_PROMPT = (
    "Question: {question}\n\n"
    "Expected points (distribute score by weight):\n{expected_points}\n\n"
    "Candidate answer: {user_answer}\nEvaluate the answer now."
)


def _format_expected_points(expected_points: list) -> str:
    """Convert expected points into a clear text block that includes weight information."""
    lines = []
    for p in expected_points:
        if isinstance(p, dict):
            weight_pct = round(p["weight"] * 100)
            lines.append(f"- {p['point']} (weight: {weight_pct}%)")
        else:
            lines.append(f"- {p}")  # support legacy plain point text
    return "\n".join(lines)


async def evaluate_answer(question: str, expected_points: list, user_answer: str) -> dict:
    formatted_points = _format_expected_points(expected_points)
    user_prompt = EVAL_PROMPT.format(
        question=question,
        expected_points=formatted_points,
        user_answer=user_answer,
    )

    raw_response = await generate(EVAL_SYSTEM_PROMPT, user_prompt)
    return clean_json(raw_response)


REPORT_SYSTEM_PROMPT = """You are an expert technical hiring manager.
Based on a full interview summary, write a complete evaluation report.

Strict rules:
- Return JSON only, with no extra text outside the JSON.
- Answer in English only.
- The exact required format is:
{"overall_score": number from 0 to 10, "strengths": ["strength points"], "weaknesses": ["weakness points"], "recommendation": "hire or maybe or no_hire", "summary": "short summary in English"}"""

REPORT_PROMPT = "{summary_text}\n\n" "Write a complete evaluation report based on this summary."


async def generate_report(answered_questions: list) -> dict:
    summary_text = "\n\n".join(
        f"Question: {q['question']}\nScore: {q['score']}/10\nMissing points: {q['missing_points']}"
        for q in answered_questions
    )
    user_prompt = REPORT_PROMPT.format(summary_text=summary_text)

    raw_response = await generate(REPORT_SYSTEM_PROMPT, user_prompt)
    return clean_json(raw_response)


# ---------------------------------------------------------------------------
# New: personalized version of generate_question that uses the candidate profile
# ---------------------------------------------------------------------------
async def generate_personalized_question(
    topic: str,
    difficulty: str,
    candidate_profile: dict,
    exclude_ids: list = None,
    previous_answers: list[dict] | None = None,
    session_id: int | str | None = None,
) -> dict:
    """
    If we have a candidate profile (from cv_analyzer), use retrieval.py to find the closest question
    for their skills, then use question_rewriter.py to personalize it.
    If there is no suitable bank question, fall back to the standard generate_question path.
    """
    from question_rewriter import rewrite_question
    from retrieval import find_best_matching_question

    keywords = (
        candidate_profile.get("skills", [])
        + candidate_profile.get("technologies", [])
        + candidate_profile.get("programming_languages", [])
    )

    job_context = ""
    if session_id:
        db = SessionLocal()
        try:
            session = db.get(InterviewSession, session_id)
            if session and session.job_id:
                job = db.get(Job, session.job_id)
                if job:
                    job_context = build_job_text(job)
        finally:
            db.close()

    matches = find_best_matching_question(
        topic,
        difficulty,
        keywords,
        exclude_ids,
        candidate_profile=candidate_profile,
        session_id=session_id,
        job_context=job_context,
    )

    if not matches:
        # No matching bank questions for this topic/level; fall back to the regular generation strategy.
        return await generate_question(topic, difficulty, exclude_ids)

    best_match = matches[0]
    if best_match.get("match_score", 0) > 0:
        personalized_text = await rewrite_question(
            best_match["question"],
            candidate_profile,
            reference_questions=matches[:3],
            previous_answers=previous_answers,
        )
        best_match["question"] = personalized_text

    best_match.pop("match_score", None)
    return best_match
