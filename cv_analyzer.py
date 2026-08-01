"""
Analyze resume text with the model and extract structured candidate profile data.
Different from cv_parser.py (which extracts raw text only) — this file interprets the content.
"""

from ai_service import clean_json
from providers import generate

CV_ANALYSIS_SYSTEM_PROMPT = """You are an expert technical resume analyst.
Your task: analyze the resume text and extract structured candidate profile information.

Strict rules:
- Return JSON only, with no extra text outside the JSON.
- Answer in English only, even if the resume itself is written in another language
  (e.g. Arabic). Translate skill names, project descriptions, and all extracted
  text into English before returning them.
- The exact required format is:
{
  "skills": ["skill 1", "skill 2"],
  "technologies": ["technology 1", "technology 2"],
  "programming_languages": ["Python", "..."],
  "frameworks": ["Django", "..."],
  "projects": [{"name": "project name", "description": "short description", "technologies_used": ["..."]}],
  "work_experience_years": approximate number,
  "education": "latest degree",
  "certifications": ["..."],
  "strengths": ["clear strengths from the resume"],
  "possible_weak_areas": ["possible weaker areas based on missing skills"]
}
- If information is not present in the resume, leave lists empty [] or use null. Do not invent details."""

async def analyze_cv(cv_text: str) -> dict:
    """Take raw resume text and return structured candidate profile data."""
    user_prompt = f'Resume text:\n"""{cv_text[:4000]}"""\n\nAnalyze the resume now.'
    raw_response = await generate(CV_ANALYSIS_SYSTEM_PROMPT, user_prompt, temperature=0.2)
    return clean_json(raw_response)