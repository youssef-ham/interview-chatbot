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

st.set_page_config(page_title="Manage Jobs", page_icon="🗂️")

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


st.title("🗂️ Manage Jobs")

question_count = count_questions()
if question_count == 0:
    st.warning(
        "The question bank is currently empty. Click the button below to populate the questions from data/questions.json."
    )
    if st.button("Add questions from data bank"):
        added, skipped = seed_questions_from_data()
        if added:
            st.success(f"Added {added} new questions to the database.")
        else:
            st.info("No new questions to add or the file is missing.")
        st.experimental_rerun()

st.subheader("Add New Job")

with st.form("add_job_form", clear_on_submit=True):
    title = st.text_input("Job Title", placeholder="e.g., Backend Developer")
    description = st.text_area(
        "Job description", height=150, placeholder="Write job requirements and responsibilities..."
    )

    available_topics = get_available_topics()
    available_difficulties = get_available_difficulties()

    if not available_topics or not available_difficulties:
        st.info(
            "No question data in the database currently — this list shows default suggestions. "
            "To populate real topics from the question bank, add questions first."
        )

    required_topics = st.multiselect(
        "Required interview topics",
        available_topics or DEFAULT_TOPICS,
        help=(
            "Select the main topics you expect in the interview, e.g. Python, Data Structures, System Design."
        ),
    )
    difficulty = st.selectbox(
        "Required level",
        available_difficulties or DEFAULT_DIFFICULTIES,
        help=(
            "Choose the role level: 'junior' for entry, 'mid' for intermediate, 'senior' for experienced. "
            "Use 'intern' for trainees and 'lead' for leadership roles."
        ),
    )

    submitted = st.form_submit_button("Add Job", type="primary")

    if submitted:
        if not title or not description or not required_topics:
            st.error("Please fill in all required fields")
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
            db.refresh(job)  # refresh to get id and updated fields before indexing

            # Index the job in Chroma immediately (before closing session)
            try:
                index_single_job(job)
            except Exception as e:
                st.warning(f"Job added, but failed to index for semantic search: {e}")

            db.close()
            st.success(f"Job '{title}' added successfully")
            st.rerun()

st.divider()
st.subheader("Current Jobs")

db = SessionLocal()
jobs = db.query(Job).order_by(Job.created_at.desc()).all()
db.close()

if not jobs:
    st.info("No jobs have been added yet")
else:
    for job in jobs:
        with st.expander(f"{job.title} — {job.difficulty}"):
            st.write(job.description)
            st.caption(f"Topics: {', '.join(job.required_topics)}")
