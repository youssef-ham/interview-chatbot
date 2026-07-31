"""
Backend API - بيعرض كل حاجة عملناها (الوظائف، المقابلة، التقييم) كـ REST endpoints
عشان أي frontend (React, Vue, HTML عادي) يقدر يكلمها.

شغّله بـ: uvicorn main:app --reload
التوثيق التفاعلي هيبقى متاح على: http://localhost:8000/docs
"""

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ai_service import (
    evaluate_answer,
    generate_personalized_question,
    generate_question,
    generate_report,
)
from cv_analyzer import analyze_cv
from cv_parser import extract_text_from_bytes
from db.database import get_db, init_db
from db.models import Answer, InterviewSession, Job
from retrieval import index_candidate_profile

# انشئ الجداول وطبق تحديثات مخطط بسيطة عند بدء تشغيل الـ API.
# نستخدم نفس حل الترحيل الخفيف الموجود في db/database.py
init_db()

app = FastAPI(title="Interview Bot API")

# CORS: بيسمح لأي frontend شغال على domain مختلف (زي localhost:3000) يكلم الـ API ده
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # في الإنتاج، حط هنا دومين الـ frontend الفعلي بدل *
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic schemas - شكل البيانات اللي بتتبعت وترجع في كل endpoint
# ---------------------------------------------------------------------------
class JobOut(BaseModel):
    id: int
    title: str
    description: str
    required_topics: list[str]
    difficulty: str

    class Config:
        from_attributes = True


class JobCreate(BaseModel):
    title: str
    description: str
    required_topics: list[str]
    difficulty: str


class AnswerSubmit(BaseModel):
    answer_id: int
    answer_text: str


# ---------------------------------------------------------------------------
# الوظائف (Jobs)
# ---------------------------------------------------------------------------
@app.get("/api/jobs", response_model=list[JobOut])
def list_jobs(db: Session = Depends(get_db)):
    """قائمة الوظائف المتاحة - لشاشة قائمة الوظائف عند المرشح"""
    return db.query(Job).filter_by(is_active="active").order_by(Job.created_at.desc()).all()


@app.get("/api/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    """تفاصيل وظيفة واحدة - لشاشة تفاصيل الوظيفة"""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="الوظيفة غير موجودة")
    return job


@app.post("/api/jobs", response_model=JobOut)
def create_job(job_data: JobCreate, db: Session = Depends(get_db)):
    """إضافة وظيفة جديدة - لشاشة إدارة الوظائف"""
    job = Job(
        title=job_data.title,
        description=job_data.description,
        required_topics=job_data.required_topics,
        difficulty=job_data.difficulty,
        is_active="active",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


# ---------------------------------------------------------------------------
# بدء المقابلة (رفع CV + اختيار وظيفة)
# ---------------------------------------------------------------------------
@app.post("/api/interviews/start")
async def start_interview(
    job_id: int = Form(...),
    num_questions: int = Form(3),
    cv_file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    """
    لشاشة رفع الـ CV/بدء المقابلة. لو cv_file اتبعت، بيتحلل فورًا.
    بترجع session_id عشان الـ frontend يستخدمه في باقي الـ endpoints.
    """
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="الوظيفة غير موجودة")

    candidate_profile = None
    if cv_file is not None:
        try:
            raw_bytes = await cv_file.read()
            cv_text = extract_text_from_bytes(cv_file.filename, raw_bytes)
            candidate_profile = await analyze_cv(cv_text)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"تعذر قراءة أو تحليل الملف: {e}")

    session = InterviewSession(
        job_id=job.id,
        topic=", ".join(job.required_topics),
        difficulty=job.difficulty,
        status="in_progress",
        candidate_profile=candidate_profile,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    if candidate_profile:
        index_candidate_profile(session.id, candidate_profile)

    return {
        "session_id": session.id,
        "num_questions": num_questions,
        "topics": job.required_topics,
        "difficulty": job.difficulty,
        "has_cv_profile": candidate_profile is not None,
    }


# ---------------------------------------------------------------------------
# السؤال التالي
# ---------------------------------------------------------------------------
@app.get("/api/interviews/{session_id}/next-question")
async def next_question(session_id: int, topic_index: int, db: Session = Depends(get_db)):
    """
    لشاشة المقابلة. topic_index بيحدد أنهي موضوع من مواضيع الوظيفة نستخدمه
    (الـ frontend بيحسبها زي: رقم السؤال - 1، بيتاخد modulo عدد المواضيع).
    """
    session = db.get(InterviewSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="الجلسة غير موجودة")

    topics = [t.strip() for t in session.topic.split(",")]
    current_topic = topics[topic_index % len(topics)]

    # نجيب الأسئلة اللي اتسألت قبل كده في نفس الجلسة، عشان نستبعدها
    answers = db.query(Answer).filter_by(session_id=session_id).all()
    already_asked = [a.question_id for a in answers if a.question_id is not None]
    previous_answers = [
        {
            "question": a.question_text,
            "score": a.score,
            "missing_points": a.missing_points,
        }
        for a in answers
        if a.status == "evaluated"
    ]

    if session.candidate_profile:
        question = await generate_personalized_question(
            current_topic,
            session.difficulty,
            session.candidate_profile,
            exclude_ids=already_asked,
            previous_answers=previous_answers,
            session_id=session.id,
        )
    else:
        question = await generate_question(
            current_topic, session.difficulty, exclude_ids=already_asked
        )

    answer_row = Answer(
        session_id=session_id,
        question_id=question.get("id"),
        question_text=question["question"],
        expected_points=question["expected_points"],
        status="pending",
    )
    db.add(answer_row)
    db.commit()
    db.refresh(answer_row)

    return {"answer_id": answer_row.id, "question": question["question"]}


# ---------------------------------------------------------------------------
# إرسال إجابة
# ---------------------------------------------------------------------------
@app.post("/api/interviews/{session_id}/answer")
async def submit_answer(session_id: int, payload: AnswerSubmit, db: Session = Depends(get_db)):
    """لشاشة المقابلة - بعد ما المرشح يكتب إجابته ويدوس إرسال"""
    answer_row = db.get(Answer, payload.answer_id)
    if answer_row is None or answer_row.session_id != session_id:
        raise HTTPException(status_code=404, detail="السؤال غير موجود في الجلسة دي")

    evaluation = await evaluate_answer(
        answer_row.question_text, answer_row.expected_points, payload.answer_text
    )

    answer_row.user_answer = payload.answer_text
    answer_row.score = evaluation["score"]
    answer_row.missing_points = evaluation["missing_points"]
    answer_row.feedback = evaluation["feedback"]
    answer_row.status = "evaluated"
    db.commit()

    return {
        "score": evaluation["score"],
        "missing_points": evaluation["missing_points"],
        "feedback": evaluation["feedback"],
    }


# ---------------------------------------------------------------------------
# إنهاء المقابلة والتقرير النهائي
# ---------------------------------------------------------------------------
@app.post("/api/interviews/{session_id}/complete")
async def complete_interview(session_id: int, db: Session = Depends(get_db)):
    """لشاشة التقرير النهائي - بتتنادى بعد آخر سؤال"""
    session = db.get(InterviewSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="الجلسة غير موجودة")

    answered = db.query(Answer).filter_by(session_id=session_id, status="evaluated").all()
    answered_data = [
        {"question": a.question_text, "score": a.score, "missing_points": a.missing_points}
        for a in answered
    ]

    report = await generate_report(answered_data)

    session.final_report = report
    session.status = "completed"
    db.commit()

    return report


# ---------------------------------------------------------------------------
# تفاصيل جلسة (للتشخيص أو للإدارة)
# ---------------------------------------------------------------------------
@app.get("/api/interviews/{session_id}")
def get_interview(session_id: int, db: Session = Depends(get_db)):
    session = db.get(InterviewSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="الجلسة غير موجودة")

    return {
        "id": session.id,
        "status": session.status,
        "topic": session.topic,
        "difficulty": session.difficulty,
        "final_report": session.final_report,
        "answers": [
            {"question": a.question_text, "score": a.score, "feedback": a.feedback}
            for a in session.answers
        ],
    }
