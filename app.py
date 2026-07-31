"""
الصفحة الرئيسية - المرشح بيختار وظيفة، يرفع CV (اختياري)، وتبدأ المقابلة.
"""
import asyncio
import os
import streamlit as st
from dotenv import load_dotenv
from datetime import datetime

from ai_service import generate_question, evaluate_answer, generate_report, generate_personalized_question
from db.database import SessionLocal
from db.models import Job, InterviewSession, Answer
from cv_parser import extract_text_from_file
from cv_analyzer import analyze_cv
from retrieval import index_candidate_profile

load_dotenv()

st.set_page_config(page_title="Interview Bot", page_icon="🎙️")

# Adaptive stopping defaults (can be moved to env/config or admin UI later)
PASS_THRESHOLD = float(os.getenv('PASS_THRESHOLD', '7'))
CONSECUTIVE_SUCCESS = int(os.getenv('CONSECUTIVE_SUCCESS', '2'))
FAIL_THRESHOLD = float(os.getenv('FAIL_THRESHOLD', '4'))
CONSECUTIVE_FAIL = int(os.getenv('CONSECUTIVE_FAIL', '2'))
MAX_QUESTIONS = int(os.getenv('MAX_QUESTIONS', '8'))


def run_async(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError as exc:
        if "asyncio.run() cannot be called from a running event loop" not in str(exc):
            raise

        import threading

        result: dict[str, object] = {}

        def _run():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result["value"] = loop.run_until_complete(coro)
            except Exception as error:
                result["error"] = error
            finally:
                loop.close()

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join()

        if "error" in result:
            raise result["error"]
        return result.get("value")


def format_rtl_text(text: str) -> str:
    """Wrap text in RTL Unicode markers so mixed Arabic/English renders correctly."""
    if not text:
        return text
    return f"\u202B{text}\u202C"


def get_active_jobs():
    db = SessionLocal()
    jobs = db.query(Job).filter_by(is_active="active").order_by(Job.created_at.desc()).all()
    db.close()
    return jobs


if "stage" not in st.session_state:
    st.session_state.stage = "setup"
    st.session_state.answered_questions = []
    st.session_state.current_question = None
    st.session_state.session_id = None
    st.session_state.current_answer_id = None
    st.session_state.asked_question_ids = []

st.title("🎙️ Interview Bot")

# ---------------------------------------------------------------------------
# مرحلة الإعداد: اختيار وظيفة + رفع CV
# ---------------------------------------------------------------------------
if st.session_state.stage == "setup":
    jobs = get_active_jobs()

    if not jobs:
        st.warning("لا توجد وظائف متاحة حاليًا. راجع صفحة إدارة الوظائف.")
        st.stop()

    job_titles = [job.title for job in jobs]
    selected_title = st.selectbox("اختر الوظيفة اللي عايز تقدّم عليها", job_titles)
    selected_job = next(job for job in jobs if job.title == selected_title)

    st.write(selected_job.description)
    st.caption(f"المواضيع: {', '.join(selected_job.required_topics)} | المستوى: {selected_job.difficulty}")

    cv_file = st.file_uploader("ارفع السيرة الذاتية (اختياري)", type=["pdf", "docx", "txt"])

    st.markdown("**العدد سيُحدّد تلقائيًا بناءً على تقييم الإجابات؛ لا تحتاج لاختيار عدد الأسئلة.**")

    if st.button("ابدأ المقابلة", type="primary"):
        candidate_profile = None
        if cv_file is not None:
            try:
                cv_text = extract_text_from_file(cv_file)
                with st.spinner("جاري تحليل السيرة الذاتية..."):
                    candidate_profile = run_async(analyze_cv(cv_text))
            except Exception as e:
                st.error(f"تعذر قراءة أو تحليل الملف: {e}")
                st.stop()

        db = SessionLocal()
        db_session = InterviewSession(
            topic=", ".join(selected_job.required_topics),
            difficulty=selected_job.difficulty,
            status="in_progress",
            aggregated_score=0.0,
            consecutive_success_count=0,
            consecutive_fail_count=0,
        )
        db.add(db_session)
        db.commit()
        db.refresh(db_session)
        st.session_state.session_id = db_session.id
        if candidate_profile:
            index_candidate_profile(db_session.id, candidate_profile)
        db.close()

        st.session_state.job_topics = selected_job.required_topics
        st.session_state.difficulty = selected_job.difficulty
        st.session_state.max_questions = MAX_QUESTIONS
        st.session_state.answered_questions = []
        st.session_state.asked_question_ids = []
        st.session_state.recent_scores = []
        st.session_state.questions_asked_count = 0
        st.session_state.candidate_profile = candidate_profile
        st.session_state.stage = "question"
        st.rerun()

# ---------------------------------------------------------------------------
# مرحلة السؤال
# ---------------------------------------------------------------------------
elif st.session_state.stage == "question":
    q_num = len(st.session_state.answered_questions) + 1
    total = st.session_state.max_questions

    if st.session_state.current_question is None:
        # نوزّع الأسئلة بالتناوب على مواضيع الوظيفة (لو أكتر من موضوع)
        topics = st.session_state.job_topics
        current_topic = topics[(q_num - 1) % len(topics)]

        with st.spinner("جاري تجهيز السؤال..."):
            profile = st.session_state.get("candidate_profile")
            if profile:
                question = run_async(
                    generate_personalized_question(
                        current_topic,
                        st.session_state.difficulty,
                        profile,
                        exclude_ids=st.session_state.asked_question_ids,
                        previous_answers=st.session_state.answered_questions,
                        session_id=st.session_state.session_id,
                    )
                )
            else:
                question = run_async(
                    generate_question(
                        current_topic,
                        st.session_state.difficulty,
                        exclude_ids=st.session_state.asked_question_ids,
                    )
                )
            st.session_state.current_question = question

            if question.get("id"):
                st.session_state.asked_question_ids.append(question["id"])

            db = SessionLocal()
            answer_row = Answer(
                session_id=st.session_state.session_id,
                question_id=question.get("id"),
                question_text=question["question"],
                expected_points=question["expected_points"],
                status="pending",
            )
            db.add(answer_row)
            db.commit()
            db.refresh(answer_row)
            st.session_state.current_answer_id = answer_row.id
            db.close()

    st.subheader(f"سؤال {q_num} من {total}")
    st.info(format_rtl_text(st.session_state.current_question["question"]))

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

        db = SessionLocal()
        answer_row = db.query(Answer).get(st.session_state.current_answer_id)
        answer_row.user_answer = answer
        answer_row.score = evaluation["score"]
        answer_row.missing_points = evaluation["missing_points"]
        answer_row.feedback = evaluation["feedback"]
        answer_row.status = "evaluated"
        db.commit()
        db.close()

        st.session_state.answered_questions.append({
            "question": st.session_state.current_question["question"],
            "score": evaluation["score"],
            "missing_points": evaluation["missing_points"],
        })
        st.session_state.last_evaluation = evaluation
        # update adaptive tracking
        score = float(evaluation.get("score", 0.0))
        st.session_state.recent_scores.append(score)
        st.session_state.questions_asked_count = st.session_state.questions_asked_count + 1

        # Persist aggregated stats to DB
        db = SessionLocal()
        sess = db.query(InterviewSession).get(st.session_state.session_id)
        if sess:
            # compute overall aggregated score as average of all evaluated answers so far
            all_scores = [a.get("score", 0.0) for a in st.session_state.answered_questions if a.get("score") is not None]
            agg = sum(all_scores) / len(all_scores) if all_scores else 0.0
            sess.aggregated_score = agg
            # compute consecutive success/fail counts based on last responses
            # consecutive success: how many of last answers (from most recent) are >= PASS_THRESHOLD
            consec_success = 0
            for s in reversed(st.session_state.recent_scores):
                if s >= PASS_THRESHOLD:
                    consec_success += 1
                else:
                    break
            sess.consecutive_success_count = consec_success

            consec_fail = 0
            for s in reversed(st.session_state.recent_scores):
                if s <= FAIL_THRESHOLD:
                    consec_fail += 1
                else:
                    break
            sess.consecutive_fail_count = consec_fail
            db.commit()
        db.close()

        # check adaptive stop conditions
        stop_reason = None
        # pass condition: last CONSECUTIVE_SUCCESS avg >= PASS_THRESHOLD
        if len(st.session_state.recent_scores) >= CONSECUTIVE_SUCCESS:
            last_n = st.session_state.recent_scores[-CONSECUTIVE_SUCCESS:]
            if (sum(last_n) / len(last_n)) >= PASS_THRESHOLD:
                stop_reason = "reached_pass_threshold"

        # fail condition
        if stop_reason is None and len(st.session_state.recent_scores) >= CONSECUTIVE_FAIL:
            last_m = st.session_state.recent_scores[-CONSECUTIVE_FAIL:]
            if (sum(last_m) / len(last_m)) <= FAIL_THRESHOLD:
                stop_reason = "reached_fail_pattern"

        # max questions
        if stop_reason is None and st.session_state.questions_asked_count >= st.session_state.max_questions:
            stop_reason = "reached_max_questions"

        if stop_reason:
            # finalize session in DB and show neutral message to candidate
            db = SessionLocal()
            sess = db.query(InterviewSession).get(st.session_state.session_id)
            if sess:
                sess.stopped_reason = stop_reason
                sess.stopped_at = datetime.utcnow()
                sess.status = "completed"
                db.commit()
            db.close()

            # neutral friendly message shown to candidate (as requested)
            if stop_reason == "reached_pass_threshold":
                st.session_state.stop_message = "شكرًا — إجاباتك جيدة ومناسبة لمتطلبات هذه الوظيفة. سنراجعها ونوافيك بالتحديثات."
            elif stop_reason == "reached_fail_pattern":
                st.session_state.stop_message = "شكراً على وقتك — سنراجع إجاباتك ونشارك الفريق المسؤول. سنوافيك بالتحديثات لاحقًا."
            else:
                st.session_state.stop_message = "انتهت المقابلة — سنراجع إجاباتك ونرجع لك بالتحديثات."

            st.session_state.current_question = None
            st.session_state.current_answer_id = None
            st.session_state.stage = "report"
            st.rerun()

        # otherwise continue
        st.session_state.current_question = None
        st.session_state.current_answer_id = None
        st.session_state.stage = "answered"
        st.rerun()

# ---------------------------------------------------------------------------
# مرحلة عرض النتيجة
# ---------------------------------------------------------------------------
elif st.session_state.stage == "answered":
    ev = st.session_state.last_evaluation
    st.metric("الدرجة", f"{ev['score']}/10")
    st.write("**نقاط ناقصة:**", ev["missing_points"])
    st.write("**تعليق:**", ev["feedback"])

    is_last = len(st.session_state.answered_questions) >= st.session_state.max_questions
    label = "شوف التقرير" if is_last else "السؤال التالي"

    if st.button(label, type="primary"):
        st.session_state.stage = "report" if is_last else "question"
        st.rerun()

# ---------------------------------------------------------------------------
# مرحلة التقرير
# ---------------------------------------------------------------------------
elif st.session_state.stage == "report":
    if "final_report" not in st.session_state:
        with st.spinner("جاري إعداد التقرير..."):
            report = run_async(generate_report(st.session_state.answered_questions))
            st.session_state.final_report = report

            db = SessionLocal()
            db_session = db.query(InterviewSession).get(st.session_state.session_id)
            db_session.final_report = report
            db_session.status = "completed"
            db.commit()
            db.close()

    report = st.session_state.final_report
    st.subheader("📋 التقرير النهائي")
    st.metric("الدرجة الإجمالية", f"{report['overall_score']}/10")
    st.write("**التوصية:**", report["recommendation"])
    st.write("**الملخص:**", report["summary"])

    if st.button("مقابلة جديدة"):
        for key in ["stage", "answered_questions", "current_question", "final_report",
                     "session_id", "current_answer_id", "asked_question_ids"]:
            st.session_state.pop(key, None)
        st.rerun()