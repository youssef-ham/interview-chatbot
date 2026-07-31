"""
هنا الدوال اللي بتستخدم الموديل عشان تعمل مهام محددة:
توليد سؤال، تقييم إجابة، عمل تقرير.
"""

import json
import random
import re

from db.database import SessionLocal
from db.models import Question
from providers import generate


def clean_json(raw_text: str) -> dict:
    cleaned = re.sub(r"```json\s*|\s*```", "", raw_text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        json_block = re.search(r"\{.*\}", cleaned, flags=re.S)
        if json_block:
            return json.loads(json_block.group(0))
        raise


# ---------------------------------------------------------------------------
# جديد: جيب سؤال حقيقي من بنك الأسئلة بدل ما الموديل يخترعه
# ---------------------------------------------------------------------------
def get_question_from_bank(topic: str, difficulty: str, exclude_ids: list = None) -> dict | None:
    """
    بتدور في جدول questions عن سؤال بنفس الموضوع والمستوى، ومش من ضمن
    اللي اتسألوا قبل كده في نفس الجلسة (exclude_ids).
    بترجع None لو مفيش سؤال متاح (عشان نعرف نرجع لخطة بديلة).
    """
    exclude_ids = exclude_ids or []
    db = SessionLocal()

    query = db.query(Question).filter_by(topic=topic, difficulty=difficulty)
    if exclude_ids:
        query = query.filter(~Question.id.in_(exclude_ids))

    candidates = query.all()
    db.close()

    if not candidates:
        return None

    chosen = random.choice(candidates)
    return {
        "id": chosen.id,
        "question": chosen.question,
        # بنسيب النقاط بشكلها الكامل [{"point": "...", "weight": 0.4}, ...]
        # عشان نستخدم الوزن فعليًا وقت التقييم، مش بس النص
        "expected_points": chosen.expected_points,
    }


QUESTION_SYSTEM_PROMPT = """أنت interviewer تقني محترف.
مهمتك: توليد سؤال مقابلة واحد فقط.

قواعد صارمة:
- رجّع JSON فقط، بدون أي نص أو شرح خارج الـ JSON.
- أجب بالعربية فقط، ولا تخلط بين العربية والإنجليزية.
- الشكل المطلوب بالظبط:
{"question": "نص السؤال", "expected_points": [{"point": "نقطة 1", "weight": 0.5}, {"point": "نقطة 2", "weight": 0.3}, {"point": "نقطة 3", "weight": 0.2}]}
- 3 نقاط تقنية واضحة، والأوزان لازم يجمعوا 1.0 بالظبط.
- الوزن الأعلى للنقطة الأهم تقنيًا."""


async def generate_question(topic: str, difficulty: str, exclude_ids: list = None) -> dict:
    """
    بتحاول الأول تجيب سؤال حقيقي من بنك الأسئلة (get_question_from_bank).
    لو مفيش سؤال متاح، بترجع لتوليد سؤال بالموديل كخطة بديلة.
    لو السؤال جاي من البنك، بنستخدم نفس آلية إعادة الصياغة بالعربية فقط
    حتى لو كان نص السؤال الأصلي بالإنجليزية.
    """
    bank_question = get_question_from_bank(topic, difficulty, exclude_ids)
    if bank_question is not None:
        try:
            from question_rewriter import rewrite_question

            bank_question["question"] = await rewrite_question(
                bank_question["question"],
                {},
                reference_questions=[bank_question],
                previous_answers=[],
            )
        except Exception:
            pass
        return bank_question

    # خطة بديلة: مفيش أسئلة متاحة في البنك، نولّد واحد بالموديل
    user_prompt = f"الموضوع: {topic}\nالمستوى: {difficulty}\nولّد سؤال واحد الآن."
    raw_response = await generate(QUESTION_SYSTEM_PROMPT, user_prompt)
    question_data = clean_json(raw_response)
    question_data["id"] = None  # مفيش id لأنه مش من البنك
    return question_data


EVAL_SYSTEM_PROMPT = """أنت مقيّم تقني دقيق وموضوعي.
قيّم إجابة المرشح بناءً على النقاط المتوقعة فقط.

قواعد صارمة:
- رجّع JSON فقط بدون أي نص خارجه.
- أجب بالعربية فقط.
- الشكل المطلوب بالظبط:
{"score": رقم من 0 إلى 10, "missing_points": ["النقاط الناقصة"], "feedback": "تعليق قصير بالعربي"}
- لو الإجابة فاضية، الدرجة = 0."""

EVAL_PROMPT = (
    "السؤال: {question}\n\n"
    "النقاط المتوقعة (وزّع الدرجة حسب وزن كل نقطة):\n{expected_points}\n\n"
    "إجابة المرشح: {user_answer}\nقيّم الإجابة الآن."
)


def _format_expected_points(expected_points: list) -> str:
    """بتحول قائمة النقاط لنص واضح يوضح وزن كل نقطة، عشان الموديل يوزّع الدرجة صح"""
    lines = []
    for p in expected_points:
        if isinstance(p, dict):
            weight_pct = round(p["weight"] * 100)
            lines.append(f"- {p['point']} (الوزن: {weight_pct}%)")
        else:
            lines.append(f"- {p}")  # دعم النسخة القديمة (نص بس، من غير وزن)
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


REPORT_SYSTEM_PROMPT = """أنت مسؤول توظيف تقني خبير.
بناءً على نتائج مقابلة كاملة، اكتب تقرير تقييم شامل.

قواعد صارمة:
- رجّع JSON فقط بدون أي نص خارجه.
- أجب بالعربية فقط.
- الشكل المطلوب بالظبط:
{"overall_score": رقم من 0 إلى 10, "strengths": ["نقاط قوة"], "weaknesses": ["نقاط ضعف"], "recommendation": "hire او maybe او no_hire", "summary": "ملخص قصير بالعربي"}"""

REPORT_PROMPT = "{summary_text}\n\n" "اكتب تقرير تقييم كامل استنادًا لهذا الملخص."


async def generate_report(answered_questions: list) -> dict:
    summary_text = "\n\n".join(
        f"سؤال: {q['question']}\nدرجة: {q['score']}/10\nنقاط ناقصة: {q['missing_points']}"
        for q in answered_questions
    )
    user_prompt = REPORT_PROMPT.format(summary_text=summary_text)

    raw_response = await generate(REPORT_SYSTEM_PROMPT, user_prompt)
    return clean_json(raw_response)


# ---------------------------------------------------------------------------
# جديد: نسخة مخصصة من generate_question بتستخدم بروفايل المرشح
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
    لو عندنا بروفايل مرشح (من cv_analyzer)، بنستخدم retrieval.py نجيب أقرب سؤال
    لمهاراته، وبعدين question_rewriter.py يعيد صياغته ليبدو موجّه له شخصيًا.
    لو مفيش سؤال مناسب في البنك، بترجع لـ generate_question العادية.
    """
    from question_rewriter import rewrite_question
    from retrieval import find_best_matching_question

    keywords = (
        candidate_profile.get("skills", [])
        + candidate_profile.get("technologies", [])
        + candidate_profile.get("programming_languages", [])
    )

    matches = find_best_matching_question(
        topic,
        difficulty,
        keywords,
        exclude_ids,
        candidate_profile=candidate_profile,
        session_id=session_id,
    )

    if not matches:
        # مفيش أسئلة متاحة أصلاً في البنك لنفس الموضوع/المستوى - نرجع للخطة العادية
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
