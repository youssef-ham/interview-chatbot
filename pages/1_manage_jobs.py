"""
صفحة إدارة الوظائف - صاحب الشركة بيضيف وظايف جديدة من هنا.
"""

import streamlit as st
from dotenv import load_dotenv

from db.database import Base, SessionLocal, engine
from db.models import Job, Question
from retrieval import index_single_job

load_dotenv()

st.set_page_config(page_title="إدارة الوظائف", page_icon="🗂️")

Base.metadata.create_all(bind=engine)


def get_available_topics():
    db = SessionLocal()
    topics = [row[0] for row in db.query(Question.topic).distinct().all()]
    db.close()
    return topics


def get_available_difficulties():
    db = SessionLocal()
    difficulties = [row[0] for row in db.query(Question.difficulty).distinct().all()]
    db.close()
    return difficulties


st.title("🗂️ إدارة الوظائف")

st.subheader("إضافة وظيفة جديدة")

with st.form("add_job_form", clear_on_submit=True):
    title = st.text_input("مسمى الوظيفة", placeholder="مثال: Backend Developer")
    description = st.text_area(
        "وصف الوظيفة", height=150, placeholder="اكتب متطلبات ومسؤوليات الوظيفة..."
    )
    required_topics = st.multiselect("المواضيع المطلوبة في المقابلة", get_available_topics())
    difficulty = st.selectbox("المستوى المطلوب", get_available_difficulties())

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