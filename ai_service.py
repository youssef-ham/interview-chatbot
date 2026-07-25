"""
هنا الدوال اللي بتستخدم الموديل عشان تعمل مهام محددة:
توليد سؤال، تقييم إجابة، عمل تقرير.
"""
import json
import re
from providers import generate


def clean_json(raw_text: str) -> dict:
    """
    الموديل أحيانًا بيرجع الـ JSON ملفوف في نص زيادة أو ```json```.
    الدالة دي بتشيل أي حاجة زيادة وترجع بس الـ JSON نفسه كـ dict بايثون.
    """
    cleaned = re.sub(r"```json\s*|\s*```", "", raw_text).strip()
    return json.loads(cleaned)


QUESTION_SYSTEM_PROMPT = """أنت interviewer تقني محترف.
مهمتك: توليد سؤال مقابلة واحد فقط.

قواعد صارمة:
- رجّع JSON فقط، بدون أي نص أو شرح خارج الـ JSON.
- الشكل المطلوب بالظبط:
{"question": "نص السؤال", "expected_points": ["نقطة 1", "نقطة 2", "نقطة 3"]}
- expected_points لازم تكون 3 نقاط تقنية واضحة."""

async def generate_question(topic: str, difficulty: str) -> dict:
    user_prompt = f"الموضوع: {topic}\nالمستوى: {difficulty}\nولّد سؤال واحد الآن."

    raw_response = await generate(QUESTION_SYSTEM_PROMPT, user_prompt)
    question_data = clean_json(raw_response)

    return question_data



EVAL_SYSTEM_PROMPT = """أنت مقيّم تقني دقيق وموضوعي.
قيّم إجابة المرشح بناءً على النقاط المتوقعة فقط.

قواعد صارمة:
- رجّع JSON فقط بدون أي نص خارجه.
- الشكل المطلوب بالظبط:
{"score": رقم من 0 إلى 10, "missing_points": ["النقاط الناقصة"], "feedback": "تعليق قصير بالعربي"}
- لو الإجابة فاضية، الدرجة = 0."""


async def evaluate_answer(question: str, expected_points: list, user_answer: str) -> dict:
    user_prompt = f"""السؤال: {question}
النقاط المتوقعة: {expected_points}
إجابة المرشح: {user_answer}
قيّم الإجابة الآن."""

    raw_response = await generate(EVAL_SYSTEM_PROMPT, user_prompt)
    return clean_json(raw_response)



REPORT_SYSTEM_PROMPT = """أنت مسؤول توظيف تقني خبير.
بناءً على نتائج مقابلة كاملة، اكتب تقرير تقييم شامل.

قواعد صارمة:
- رجّع JSON فقط بدون أي نص خارجه.
- الشكل المطلوب بالظبط:
{"overall_score": رقم من 0 إلى 10, "strengths": ["نقاط قوة"], "weaknesses": ["نقاط ضعف"], "recommendation": "hire او maybe او no_hire", "summary": "ملخص قصير بالعربي"}"""


async def generate_report(answered_questions: list) -> dict:
    summary_text = "\n\n".join(
        f"سؤال: {q['question']}\nدرجة: {q['score']}/10\nنقاط ناقصة: {q['missing_points']}"
        for q in answered_questions
    )

    raw_response = await generate(REPORT_SYSTEM_PROMPT, summary_text)
    return clean_json(raw_response)