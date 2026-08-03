"""
تقييم جودة الـ LLM في تقييم إجابات المرشحين، بمقارنة نسختين من الـ prompt
على مجموعة بيانات صغيرة "ذهبية" فيها الدرجة المتوقعة لكل إجابة.
المقياس: متوسط الخطأ المطلق (MAE) بين درجة الموديل والدرجة المتوقعة - كل ما قل كان أفضل.

شغّله بـ:
python scr/evaluate_llm.py
"""

import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_service import clean_json
from providers import generate

# مجموعة بيانات ذهبية صغيرة: سؤال + إجابة مرشح + الدرجة المتوقعة من مُقيّم بشري
GOLDEN_SET = [
    {
        "question": "What is the difference between a list and a tuple in Python?",
        "expected_points": ["list is mutable", "tuple is immutable", "performance difference"],
        "answer": "A list can be changed after creation, a tuple cannot. Tuples are usually faster.",
        "expected_score": 9,
    },
    {
        "question": "Explain the GIL in Python.",
        "expected_points": ["GIL limits one thread executing Python bytecode at a time", "affects CPU-bound multithreading", "multiprocessing as alternative"],
        "answer": "I don't know.",
        "expected_score": 0,
    },
    {
        "question": "What is a primary key in SQL?",
        "expected_points": ["uniquely identifies a row", "cannot be null", "used for relationships"],
        "answer": "It's a column that makes each row unique.",
        "expected_score": 6,
    },
    {
        "question": "What is dependency injection?",
        "expected_points": ["decouples object creation from usage", "improves testability", "common in frameworks like FastAPI"],
        "answer": "It's a design pattern where dependencies are passed in instead of created inside the class, which makes testing easier and reduces coupling.",
        "expected_score": 9,
    },
    {
        "question": "What does REST stand for and what is it?",
        "expected_points": ["Representational State Transfer", "stateless client-server architecture", "uses HTTP methods"],
        "answer": "REST APIs use HTTP.",
        "expected_score": 3,
    },
]

PROMPT_V1 = """You are a precise and objective technical evaluator.
Evaluate the candidate's answer only against the expected points.

Strict rules:
- Return JSON only, with no extra text outside the JSON.
- Answer in English only.
- The exact required format is:
{"score": number from 0 to 10, "missing_points": ["missing points"], "feedback": "short feedback in English"}
- If the answer is empty, score = 0."""

PROMPT_V2 = """You are a strict senior technical interviewer grading a candidate's answer.
Grade ONLY based on the expected points provided - do not reward generic or vague answers.
Partial credit is allowed proportionally to how many expected points are covered.

Rules:
- Return JSON only, no extra text.
- Format: {"score": number 0-10, "missing_points": ["..."], "feedback": "short, specific feedback"}
- An empty or "I don't know" answer must score 0.
- A vague answer that doesn't address any expected point should score 1-3 max."""

EVAL_PROMPT = (
    "Question: {question}\n\n"
    "Expected points:\n{expected_points}\n\n"
    "Candidate answer: {user_answer}\nEvaluate the answer now."
)


async def run_variant(system_prompt: str) -> float:
    errors = []
    for item in GOLDEN_SET:
        expected_points_text = "\n".join(f"- {p}" for p in item["expected_points"])
        user_prompt = EVAL_PROMPT.format(
            question=item["question"],
            expected_points=expected_points_text,
            user_answer=item["answer"],
        )
        raw = await generate(system_prompt, user_prompt, temperature=0.0)
        result = clean_json(raw)
        errors.append(abs(result["score"] - item["expected_score"]))
    return sum(errors) / len(errors)


async def main():
    for name, prompt in [("PROMPT_V1 (current)", PROMPT_V1), ("PROMPT_V2 (stricter)", PROMPT_V2)]:
        mae = await run_variant(prompt)
        print(f"{name:25s} -> MAE vs golden scores: {mae:.2f}")


if __name__ == "__main__":
    asyncio.run(main())
