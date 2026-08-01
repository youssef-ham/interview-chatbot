"""
Rewrite a bank question so it is personalized to the candidate's actual experience (projects, technologies).
Important: preserve the expected_points exactly as-is for evaluation consistency.
"""

from ai_service import clean_json
from providers import generate

REWRITE_SYSTEM_PROMPT = """You are a senior technical interviewer preparing for a candidate-specific interview.
Your task: rewrite the given question so it feels personalized to the candidate's experience without changing the core technical idea.

Strict rules:
- Return JSON only, with no extra text outside the JSON.
- Answer in English only.
- The format must be: {"question": "rewritten question"}
- If you can tie the question to a real project mentioned in the candidate profile, do so.
- If there is no obvious project match, rewrite the question in a more personal way without inventing details.
- Do not change the technical intent of the original question."""

REWRITE_PROMPT = (
    "Original question: {original_question}\n\n"
    "Candidate profile:\n{candidate_profile}\n\n"
    "Reference questions from the bank:\n{reference_text}\n\n"
    "Previous answers in this session:\n{previous_answers}\n\n"
    "Rewrite the question now in English so that it is personalized for this candidate, but do not change the technical idea or expected content."
)


async def rewrite_question(
    original_question: str,
    candidate_profile: dict,
    reference_questions: list[dict] | None = None,
    previous_answers: list[dict] | None = None,
) -> str:
    relevant_projects = candidate_profile.get("projects", [])
    projects_text = (
        "\n".join(
            f"- {p.get('name', 'Unnamed project')}: {p.get('description', '').strip()} (technologies: {', '.join(p.get('technologies_used', []))})"
            for p in relevant_projects
        )
        or "No projects listed"
    )

    reference_text = (
        "\n\n".join(
            f"- Question: {ref['question']} (topic: {ref.get('topic')}, difficulty: {ref.get('difficulty')})"
            for ref in (reference_questions or [])
        )
        or "No reference questions from the bank."
    )

    candidate_profile_text = (
        f"Skills: {', '.join(candidate_profile.get('skills', []))}\n"
        f"Technologies: {', '.join(candidate_profile.get('technologies', []))}\n"
        f"Programming languages: {', '.join(candidate_profile.get('programming_languages', []))}\n"
        f"Projects:\n{projects_text}"
    )

    previous_answers_text = (
        "\n\n".join(
            f"- Question: {answer['question']} | Score: {answer.get('score', 'N/A')} | Missing points: {answer.get('missing_points', [])}"
            for answer in (previous_answers or [])
        )
        or "No previous answers yet."
    )

    user_prompt = REWRITE_PROMPT.format(
        original_question=original_question,
        candidate_profile=candidate_profile_text,
        reference_text=reference_text,
        previous_answers=previous_answers_text,
    )

    raw_response = await generate(REWRITE_SYSTEM_PROMPT, user_prompt, temperature=0.5)
    result = clean_json(raw_response)
    return result["question"]
