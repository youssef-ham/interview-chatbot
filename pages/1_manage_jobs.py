"""
صفحة إدارة الوظائف - صاحب الشركة بيضيف وظايف جديدة من هنا.
"""

import json
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from db.database import Base, SessionLocal, engine
from db.models import Job, Question
from retrieval import index_single_job, index_single_question

load_dotenv()

st.set_page_config(page_title="إدارة الوظائف", page_icon="🗂️")

Base.metadata.create_all(bind=engine)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
QUESTIONS_JSON = DATA_DIR / "questions.json"


DEFAULT_TOPICS = [
    "Python",
    "Data Structures",
    "Algorithms",
    "System Design",
    "DevOps",
    "SQL",
    "Security",
    "Frontend",
    "Backend",
    "Testing",
]
DEFAULT_DIFFICULTIES = ["junior", "mid", "senior", "lead", "intern"]


def get_available_topics():
    db = SessionLocal()
    topics = [row[0] for row in db.query(Question.topic).distinct().all() if row[0]]
    db.close()
    return topics


def get_available_difficulties():
    db = SessionLocal()
    difficulties = [row[0] for row in db.query(Question.difficulty).distinct().all() if row[0]]
    db.close()
    return difficulties


def count_questions() -> int:
    db = SessionLocal()
    count = db.query(Question).count()
    db.close()
    return count


def seed_questions_from_data() -> tuple[int, int]:
    if not QUESTIONS_JSON.exists():
        return 0, 0

    with QUESTIONS_JSON.open("r", encoding="utf-8") as f:
        questions = json.load(f)

    db = SessionLocal()
    added = 0
    skipped = 0
    newly_added_questions = []

    for q in questions:
        exists = db.query(Question).filter_by(id=q["id"]).first()
        if exists:
            skipped += 1
            continue

        question = Question(
            id=q["id"],
            topic=q["topic"],
            subtopic=q.get("subtopic"),
            difficulty=q["difficulty"],
            question_type=q.get("question_type"),
            question=q["question"],
            expected_points=q["expected_points"],
            sample_answer=q.get("sample_answer"),
            tags=q.get("tags"),
            source=q.get("source"),
        )
        db.add(question)
        newly_added_questions.append(question)
        added += 1

    if added:
        db.commit()
    db.close()

    for question in newly_added_questions:
        try:
            index_single_question(question)
        except Exception:
            pass

    return added, skipped


st.title("🗂️ إدارة الوظائف")

question_count = count_questions()
if question_count == 0:
    st.warning(
        "قاعدة الأسئلة حالياً فاضية. اضغط الزر تحت لملء بنك الأسئلة الآلي من data/questions.json."
    )
    if st.button("أضف الأسئلة من بنك البيانات"):
        added, skipped = seed_questions_from_data()
        if added:
            st.success(f"تمت إضافة {added} سؤالاً جديداً إلى قاعدة البيانات.")
        else:
            st.info("مافيش أسئلة جديدة لإضافتها أو الملف غير موجود.")
        st.experimental_rerun()

st.subheader("إضافة وظيفة جديدة")

with st.form("add_job_form", clear_on_submit=True):
    title = st.text_input("مسمى الوظيفة", placeholder="مثال: Backend Developer")
    description = st.text_area(
        "وصف الوظيفة", height=150, placeholder="اكتب متطلبات ومسؤوليات الوظيفة..."
    )

    available_topics = get_available_topics()
    available_difficulties = get_available_difficulties()

    if not available_topics or not available_difficulties:
        st.info(
            "مافيش بيانات أسئلة في قاعدة البيانات حالياً، فالقائمة دي اقتراحات فقط. "
            "لو عايز تظهر لك المواضيع الحقيقية من بنك الأسئلة، أضف أسئلة أولاً."
        )

    required_topics = st.multiselect(
        "المواضيع المطلوبة في المقابلة",
        available_topics or DEFAULT_TOPICS,
        help=(
            "اختر أهم المواضيع اللي يتوقع أنها تظهر في المقابلة. "
            "مثلاً Python، Data Structures، أو System Design."
        ),
    )
    difficulty = st.selectbox(
        "المستوى المطلوب",
        available_difficulties or DEFAULT_DIFFICULTIES,
        help=(
            "اختر مستوى الوظيفة. junior للمبتدئين، mid للمتوسطين، senior للخبرة العالية. "
            "استخدم intern للمتدرّبين و lead للمسؤوليات القيادية."
        ),
    )

    submitted = st.form_submit_button("أضف الوظيفة", type="primary")

    if submitted:
        if not title or not description or not required_topics:
            st.error("لازم تملأ كل الحقول")
        else:
            db = SessionLocal()
            job = Job(
                title=title,
                description=description,
                required_topics=required_topics,
                difficulty=difficulty,
                is_active="active",
            )
            db.add(job)
            db.commit()
            db.refresh(job)  # نجيب الـ id والقيم المُحدّثة قبل ما نستخدمها في الفهرسة

            # نفهرس الوظيفة فورًا في Chroma - قبل ما نقفل الـ session
            # (لازم يحصل قبل db.close() عشان القيم expired من غير session نشط)
            try:
                index_single_job(job)
            except Exception as e:
                st.warning(f"الوظيفة اتضافت، لكن فشلت فهرستها للبحث الذكي: {e}")

            db.close()
            st.success(f"تمت إضافة وظيفة '{title}' بنجاح")
            st.rerun()

st.divider()
st.subheader("الوظائف الحالية")

db = SessionLocal()
jobs = db.query(Job).order_by(Job.created_at.desc()).all()
db.close()

if not jobs:
    st.info("لسه مفيش وظايف مضافة")
else:
    for job in jobs:
        with st.expander(f"{job.title} — {job.difficulty}"):
            st.write(job.description)
            st.caption(f"المواضيع: {', '.join(job.required_topics)}")
