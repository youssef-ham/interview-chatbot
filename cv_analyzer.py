"""
تحليل الـ CV بالموديل واستخراج بيانات منظمة عن المرشح.
مختلف عن cv_parser.py (اللي بيستخرج نص خام بس) - هنا بنفهم محتوى النص.
"""

from ai_service import clean_json
from providers import generate

CV_ANALYSIS_SYSTEM_PROMPT = """أنت محلل سير ذاتية خبير في المجال التقني.
مهمتك: تحليل نص السيرة الذاتية واستخراج بيانات منظمة عن المرشح.

قواعد صارمة:
- رجّع JSON فقط بدون أي نص خارجه.
- الشكل المطلوب بالظبط:
{
  "skills": ["مهارة 1", "مهارة 2"],
  "technologies": ["تقنية 1", "تقنية 2"],
  "programming_languages": ["Python", "..."],
  "frameworks": ["Django", "..."],
  "projects": [{"name": "اسم المشروع", "description": "وصف قصير", "technologies_used": ["..."]}],
  "work_experience_years": رقم تقريبي,
  "education": "آخر مؤهل دراسي",
  "certifications": ["..."],
  "strengths": ["نقاط قوة واضحة من السيرة الذاتية"],
  "possible_weak_areas": ["مجالات محتمل المرشح أضعف فيها، بناءً على غياب ذكرها"]
}
- لو معلومة مش موجودة في السيرة الذاتية، سيب القائمة فاضية [] أو null، متخترعش."""


async def analyze_cv(cv_text: str) -> dict:
    """
    بتاخد نص خام من CV (من cv_parser.extract_text_from_file) وترجع بيانات منظمة.
    """
    user_prompt = f'السيرة الذاتية:\n"""{cv_text[:4000]}"""\n\nحلل السيرة الذاتية الآن.'
    raw_response = await generate(CV_ANALYSIS_SYSTEM_PROMPT, user_prompt, temperature=0.2)
    return clean_json(raw_response)
