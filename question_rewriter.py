"""
إعادة صياغة سؤال من البنك ليصبح مخصص لخبرة المرشح الفعلية (مشاريعه، تقنياته).
مهم: الـ expected_points تظل كما هي من غير تغيير - عشان معيار التقييم.
"""

from ai_service import clean_json
from providers import generate

REWRITE_SYSTEM_PROMPT = """أنت interviewer تقني محترف بتحضّر لمقابلة مرشح معين.
مهمتك: أعد صياغة السؤال المُعطى ليبدو موجّه لخبرة المرشح الفعلية، من غير ما تغيّر
الفكرة التقنية الأساسية للسؤال.

قواعد صارمة:
- رجّع JSON فقط بدون أي نص خارجه.
- أجب بالعربية فقط، ولا تخلط بالعربية والإنجليزية في نفس السؤال.
- الشكل: {"question": "السؤال المُعاد صياغته"}
- لو تقدر تربط السؤال بمشروع حقيقي مذكور في خبرة المرشح، اعمل كده (مثال: "لاحظت إنك استخدمت X في مشروع Y، ...")
- لو مفيش مشروع مرتبط واضح، أعد الصياغة بأسلوب أكتر شخصية بس من غير اختراع تفاصيل غير موجودة
- ممنوع تغيّر الفكرة التقنية للسؤال الأصلي"""

REWRITE_PROMPT = (
    "السؤال الأصلي: {original_question}\n\n"
    "معلومات المرشح:\n{candidate_profile}\n\n"
    "أقرب أسئلة من بنك الأسئلة:\n{reference_text}\n\n"
    "إجابات المرشح السابقة في هذه الجلسة:\n{previous_answers}\n\n"
    "أعد صياغة السؤال الآن بالعربية فقط بحيث يكون موجّهًا لهذا المرشح، ولكن لا تغير الفكرة التقنية أو النقاط الأساسية."
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
            f"- {p.get('name', 'مشروع غير مسمى')}: {p.get('description', '').strip()} (تقنيات: {', '.join(p.get('technologies_used', []))})"
            for p in relevant_projects
        )
        or "لا توجد مشاريع مذكورة"
    )

    reference_text = (
        "\n\n".join(
            f"- سؤال: {ref['question']} (topic: {ref.get('topic')}, difficulty: {ref.get('difficulty')})"
            for ref in (reference_questions or [])
        )
        or "لا توجد مراجع إضافية من بنك الأسئلة."
    )

    candidate_profile_text = (
        f"المهارات: {', '.join(candidate_profile.get('skills', []))}\n"
        f"التقنيات: {', '.join(candidate_profile.get('technologies', []))}\n"
        f"اللغات البرمجية: {', '.join(candidate_profile.get('programming_languages', []))}\n"
        f"المشاريع:\n{projects_text}"
    )

    previous_answers_text = (
        "\n\n".join(
            f"- سؤال: {answer['question']} | درجة: {answer.get('score', 'غير متاح')} | نقاط ناقصة: {answer.get('missing_points', [])}"
            for answer in (previous_answers or [])
        )
        or "لا توجد إجابات سابقة حتى الآن."
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
