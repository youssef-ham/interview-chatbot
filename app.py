"""
الصفحة الرئيسية - هنا تحصل المقابلة الفعلية.
"""

import asyncio
import streamlit as st
from dotenv import load_dotenv

from ai_service import generate_question, evaluate_answer, generate_report

from db.database import SessionLocal, engine, Base
import db.models
from db.models import Question
from db.seed import seed_database

load_dotenv()

st.set_page_config(
    page_title="Interview Bot",
    page_icon="🎙️"
)


# =========================
# Initialize Database
# =========================

@st.cache_resource
def init_database():
    Base.metadata.create_all(bind=engine)
    seed_database()


init_database()


# =========================
# Async Helper
# =========================

def run_async(coro):
    return asyncio.run(coro)


# =========================
# Database Helpers
# =========================

def get_available_topics():
    db = SessionLocal()
    try:
        topics = [
            row[0]
            for row in db.query(Question.topic).distinct().all()
        ]
        return topics
    finally:
        db.close()


def get_available_difficulties():
    db = SessionLocal()
    try:
        difficulties = [
            row[0]
            for row in db.query(Question.difficulty).distinct().all()
        ]
        return difficulties
    finally:
        db.close()


# =========================
# Session State
# =========================

if "stage" not in st.session_state:
    st.session_state.stage = "setup"
    st.session_state.answered_questions = []
    st.session_state.current_question = None


# =========================
# UI
# =========================

st.title("🎙️ Interview Bot")


# =========================
# Setup
# =========================

if st.session_state.stage == "setup":

    topic = st.selectbox(
        "الموضوع",
        get_available_topics()
    )

    difficulty = st.selectbox(
        "المستوى",
        get_available_difficulties()
    )

    num_questions = st.slider(
        "عدد الأسئلة",
        1,
        5,
        3
    )

    if st.button("ابدأ المقابلة", type="primary"):

        st.session_state.topic = topic
        st.session_state.difficulty = difficulty
        st.session_state.num_questions = num_questions
        st.session_state.answered_questions = []
        st.session_state.current_question = None
        st.session_state.stage = "question"

        st.rerun()


# =========================
# Question
# =========================

elif st.session_state.stage == "question":

    q_num = len(st.session_state.answered_questions) + 1
    total = st.session_state.num_questions

    if st.session_state.current_question is None:

        with st.spinner("جاري توليد السؤال..."):

            st.session_state.current_question = run_async(
                generate_question(
                    st.session_state.topic,
                    st.session_state.difficulty,
                )
            )

    st.subheader(f"سؤال {q_num} من {total}")

    st.info(
        st.session_state.current_question["question"]
    )

    answer = st.text_area("إجابتك:")

    if st.button("ابعت الإجابة", type="primary") and answer.strip():

        with st.spinner("جاري التقييم..."):

            evaluation = run_async(
                evaluate_answer(
                    st.session_state.current_question["question"],
                    st.session_state.current_question["expected_points"],
                    answer,
                )
            )

        st.session_state.answered_questions.append(
            {
                "question": st.session_state.current_question["question"],
                "score": evaluation["score"],
                "missing_points": evaluation["missing_points"],
            }
        )

        st.session_state.last_evaluation = evaluation
        st.session_state.current_question = None
        st.session_state.stage = "answered"

        st.rerun()


# =========================
# Answered
# =========================

elif st.session_state.stage == "answered":

    ev = st.session_state.last_evaluation

    st.metric(
        "الدرجة",
        f"{ev['score']}/10"
    )

    st.write(
        "**نقاط ناقصة:**",
        ev["missing_points"]
    )

    st.write(
        "**تعليق:**",
        ev["feedback"]
    )

    is_last = (
        len(st.session_state.answered_questions)
        >= st.session_state.num_questions
    )

    label = (
        "شوف التقرير"
        if is_last
        else "السؤال التالي"
    )

    if st.button(label, type="primary"):

        if is_last:
            st.session_state.stage = "report"
        else:
            st.session_state.stage = "question"

        st.rerun()


# =========================
# Report
# =========================

elif st.session_state.stage == "report":

    if "final_report" not in st.session_state:

        with st.spinner("جاري إعداد التقرير..."):

            st.session_state.final_report = run_async(
                generate_report(
                    st.session_state.answered_questions
                )
            )

    report = st.session_state.final_report

    st.subheader("📋 التقرير النهائي")

    st.metric(
        "الدرجة الإجمالية",
        f"{report['overall_score']}/10"
    )

    st.write(
        "**التوصية:**",
        report["recommendation"]
    )

    st.write(
        "**الملخص:**",
        report["summary"]
    )

    if st.button("مقابلة جديدة"):

        for key in [
            "stage",
            "answered_questions",
            "current_question",
            "final_report",
            "last_evaluation",
        ]:
            st.session_state.pop(key, None)

        st.rerun()