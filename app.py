"""
الصفحة الرئيسية لتطبيق المقابلات.
المسؤوليات الرئيسية في هذا الملف:
- واجهة Streamlit لبدء المقابلة، عرض الأسئلة، استلام الإجابات، وعرض التقرير النهائي.
- مناداة الخدمات الخلفية (ai_service, retrieval, db) عند الحاجة.

تغييرات تنظيفية: توحيد أسلوب الوصول إلى الجلسة عبر db.get()، واستخدام init_db() عند البدء
للتطبيق لتطبيق أي تحديث مخطط بسيط مُضمن في db/database.py.
"""

import asyncio
from datetime import datetime

import streamlit as st

from ai_service import (
    evaluate_answer,
    generate_personalized_question,
    generate_question,
    generate_report,
)
from config import get_setting
from cv_analyzer import analyze_cv
from cv_parser import extract_text_from_bytes, extract_text_from_file
from db.database import SessionLocal, init_db
from db.models import Answer, Feedback, InterviewSession, Job
from retrieval import index_candidate_profile

st.set_page_config(page_title="Interview Bot", page_icon="🎙️")
# Apply lightweight DB migrations / create tables if missing.
# We keep migrations simple and inline (preferred per your choice). For production
# consider using a proper migration tool (Alembic).
init_db()

# Adaptive stopping defaults (can be moved to env/config or admin UI later)
PASS_THRESHOLD = float(get_setting("PASS_THRESHOLD", "7"))
CONSECUTIVE_SUCCESS = int(get_setting("CONSECUTIVE_SUCCESS", "2"))
FAIL_THRESHOLD = float(get_setting("FAIL_THRESHOLD", "4"))
CONSECUTIVE_FAIL = int(get_setting("CONSECUTIVE_FAIL", "2"))
MAX_QUESTIONS = int(get_setting("MAX_QUESTIONS", "8"))


def run_async(coro):
    """Run an async coroutine from sync Streamlit code.

    Streamlit runs inside an event loop; calling asyncio.run() directly will
    raise if an event loop is already running. The helper attempts asyncio.run()
    and falls back to running the coroutine on a fresh thread/event loop.
    """
    try:
        return asyncio.run(coro)
    except RuntimeError as exc:
        if "asyncio.run() cannot be called from a running event loop" not in str(exc):
            raise

        # Fallback: run coroutine in a dedicated thread with its own loop.
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
    return f"\u202b{text}\u202c"


def inject_custom_css() -> None:
    """يحقن CSS مخصص فوق شكل Streamlit الافتراضي: خط Tajawal (يدعم عربي/إنجليزي)،
    بطاقة للسؤال الحالي، أزرار بألوان الهوية، وشارات (badges) ملونة للدرجات."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap');

        html, body, [class*="css"] {
            font-family: 'Tajawal', sans-serif;
        }

        /* بطاقة السؤال الحالي */
        div[data-testid="stAlert"] {
            border-radius: 14px;
            border: 1px solid #E0E3F0;
            box-shadow: 0 2px 10px rgba(45, 53, 97, 0.06);
        }

        /* الأزرار الأساسية (type="primary") */
        button[kind="primary"] {
            background-color: #2D3561;
            border-radius: 10px;
            border: none;
            font-weight: 600;
        }
        button[kind="primary"]:hover {
            background-color: #232a4d;
        }

        /* شارات الدرجات */
        .score-badge {
            display: inline-block;
            padding: 4px 14px;
            border-radius: 999px;
            font-weight: 700;
            font-size: 0.95rem;
        }
        .score-badge.score-high { background-color: #DFF3EA; color: #1E7A54; }
        .score-badge.score-mid  { background-color: #FDEED2; color: #A9700F; }
        .score-badge.score-low  { background-color: #FBE2E2; color: #B23A3A; }

        /* Stepper أعلى الصفحة */
        .stepper { display: flex; gap: 8px; margin-bottom: 1.5rem; }
        .stepper .step {
            flex: 1; text-align: center; padding: 8px 4px;
            border-radius: 8px; font-size: 0.85rem; font-weight: 600;
            background-color: #EDEFF7; color: #8A8FA8;
        }
        .stepper .step.active { background-color: #2D3561; color: white; }
        .stepper .step.done { background-color: #DFF3EA; color: #1E7A54; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_stepper(current: str) -> None:
    """يعرض شريط خطوات (Setup → Interview → Report) في أعلى كل صفحة، عشان المستخدم
    يعرف هو فين بالظبط في الرحلة - بدل ما يفاجئه سؤال وراء سؤال من غير سياق."""
    stages = [("setup", "1. Setup"), ("interview", "2. Interview"), ("report", "3. Report")]
    order = {"setup": 0, "question": 1, "answered": 1, "report": 2}
    current_index = order.get(current, 0)

    html = '<div class="stepper">'
    for index, (_, label) in enumerate(stages):
        css_class = "step"
        if index < current_index:
            css_class += " done"
        elif index == current_index:
            css_class += " active"
        html += f'<div class="{css_class}">{label}</div>'
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def score_badge(score: float) -> str:
    """يرجّع HTML لشارة ملونة حسب الدرجة: أخضر (ممتاز) / كهرماني (متوسط) / أحمر (ضعيف).
    بدل ما المستخدم يفسّر الأرقام بنفسه، اللون بيدي إحساس فوري بالنتيجة."""
    if score >= 7:
        css_class = "score-high"
    elif score >= 4:
        css_class = "score-mid"
    else:
        css_class = "score-low"
    return f'<span class="score-badge {css_class}">{score:.1f}/10</span>'


def get_progress_context() -> dict:
    answered = st.session_state.get("answered_questions", [])
    total = st.session_state.get("max_questions", MAX_QUESTIONS)
    answered_count = len(answered)
    current = min(answered_count + 1, total)
    percentage = int((current / total) * 100) if total else 100
    scores = [item.get("score") for item in answered if item.get("score") is not None]
    avg_score = sum(scores) / len(scores) if scores else None
    last_score = scores[-1] if scores else None
    return {
        "current": current,
        "total": total,
        "percentage": percentage,
        "answered_count": answered_count,
        "avg_score": avg_score,
        "last_score": last_score,
    }


def render_progress_bar() -> None:
    """يعرض شريط التقدم + 3 مؤشرات (التقدّم/متوسط الدرجة/آخر درجة).
    مستخرجة لدالة مستقلة لأن نفس الواجهة كانت مكررة حرفيًا في مرحلتي
    'question' و 'answered' - أي تعديل مستقبلي هيبقى مكانه واحد بس.
    """
    context = get_progress_context()
    st.progress(context["percentage"] / 100)

    progress_col, avg_score_col, last_score_col = st.columns(3)
    progress_col.metric("Progress", f"{context['current']}/{context['total']}")
    avg_score_col.metric(
        "Average Score",
        f"{context['avg_score']:.1f}/10" if context["avg_score"] is not None else "—",
    )
    last_score_col.metric(
        "Last Score",
        f"{context['last_score']:.1f}/10" if context["last_score"] is not None else "—",
    )


def save_current_answer(
    status: str,
    user_answer: str | None = None,
    score: float | None = None,
    missing_points: list | None = None,
    feedback: str | None = None,
):
    answer_id = st.session_state.get("current_answer_id")
    if not answer_id:
        return None

    db = SessionLocal()
    answer_row = db.get(Answer, answer_id)
    if answer_row is None:
        db.close()
        return None

    if user_answer is not None:
        answer_row.user_answer = user_answer
    if score is not None:
        answer_row.score = score
    if missing_points is not None:
        answer_row.missing_points = missing_points
    if feedback is not None:
        answer_row.feedback = feedback
    answer_row.status = status
    db.commit()
    db.close()
    return answer_row


def finish_session(stop_reason: str | None, message: str) -> None:
    session_id = st.session_state.get("session_id")
    if session_id:
        db = SessionLocal()
        interview_session = db.get(InterviewSession, session_id)
        if interview_session:
            interview_session.stopped_reason = stop_reason
            interview_session.stopped_at = datetime.utcnow()
            interview_session.status = "completed"
            db.commit()
        db.close()

    st.session_state.stop_message = message
    st.session_state.current_question = None
    st.session_state.current_answer_id = None
    st.session_state.stage = "report"
    st.rerun()


def skip_current_question() -> None:
    if st.session_state.get("current_question"):
        st.session_state.answered_questions.append(
            {
                "question": st.session_state.current_question["question"],
                "score": None,
                "missing_points": [],
                "skipped": True,
            }
        )
        st.session_state.questions_asked_count = (
            st.session_state.get("questions_asked_count", 0) + 1
        )
        save_current_answer("skipped")

    st.session_state.current_question = None
    st.session_state.current_answer_id = None
    st.session_state.stage = "question"
    st.rerun()


def save_feedback(rating: int, comment: str | None = None) -> None:
    session_id = st.session_state.get("session_id")
    if not session_id:
        return
    db = SessionLocal()
    db.add(Feedback(session_id=session_id, rating=rating, comment=comment))
    db.commit()
    db.close()
    st.session_state.feedback_submitted = True
    st.rerun()


def parse_and_analyze_cv(cv_bytes: bytes | None, cv_filename: str, cv_file=None) -> dict | None:
    """يقرأ نص الـ CV (من bytes محفوظة في الجلسة، أو من ملف مرفوع مباشرة) ويحلله بالـ LLM.

    كانت نفس خطوات الـ try/except دي مكررة 3 مرات في app.py (زرار "Retry parsing"،
    وزرار "Start Interview" في حالتين مختلفتين)؛ دمجناها هنا في مكان واحد عشان أي
    تعديل مستقبلي (رسالة خطأ، إضافة نوع ملف جديد...) يتعمل مرة واحدة بس.

    بيحدّث st.session_state مباشرة (candidate_profile / cv_parse_failed / cv_parse_error)
    ويرجع الـ candidate_profile (أو None لو فشل التحليل).
    """
    try:
        if cv_bytes:
            cv_text = extract_text_from_bytes(cv_filename, cv_bytes)
        elif cv_file is not None:
            cv_text = extract_text_from_file(cv_file)
        else:
            return None

        with st.spinner("Analyzing resume..."):
            candidate_profile = run_async(analyze_cv(cv_text))

        st.session_state["candidate_profile"] = candidate_profile
        st.session_state.pop("cv_parse_failed", None)
        st.session_state.pop("cv_parse_error", None)
        return candidate_profile

    except Exception as error:
        st.session_state["cv_parse_failed"] = True
        st.session_state["cv_parse_error"] = str(error)
        return None


def get_active_jobs():
    db = SessionLocal()
    jobs = db.query(Job).filter_by(is_active="active").order_by(Job.created_at.desc()).all()
    db.close()
    return jobs


def main():
    inject_custom_css()

    if "stage" not in st.session_state:
        st.session_state.stage = "setup"
        st.session_state.answered_questions = []
        st.session_state.current_question = None
        st.session_state.session_id = None
        st.session_state.current_answer_id = None
        st.session_state.asked_question_ids = []

    st.title("🎙️ Interview Bot")
    render_stepper(st.session_state.stage)

    # ---------------------------------------------------------------------------
    # Setup stage: select job + upload CV
    # ---------------------------------------------------------------------------
    if st.session_state.stage == "setup":
        jobs = get_active_jobs()

        if not jobs:
            st.warning("No active jobs right now. Check the Manage Jobs page.")
            st.stop()

        job_titles = [job.title for job in jobs]
        selected_title = st.selectbox("Select the job you want to apply for", job_titles)
        selected_job = next((job for job in jobs if job.title == selected_title), None)
        if selected_job is None:
            selected_job = jobs[0]

        st.write(selected_job.description)
        st.caption(
            f"Topics: {', '.join(selected_job.required_topics)} | Level: {selected_job.difficulty}"
        )

        cv_file = st.file_uploader("Upload resume (optional)", type=["pdf", "docx", "txt"])

        # Persist uploaded file bytes in session_state so user can retry parsing.
        if cv_file is not None:
            try:
                buf = cv_file.read()
                st.session_state["cv_bytes"] = buf
                st.session_state["cv_filename"] = cv_file.name
                st.session_state.pop("cv_parse_failed", None)
                st.session_state.pop("cv_parse_error", None)
                st.session_state.pop("candidate_profile", None)
            except Exception:
                pass

        # Show controls and guidance when a file is present
        if st.session_state.get("cv_bytes"):
            col_a, col_b = st.columns([3, 1])
            with col_a:
                if st.session_state.get("cv_parse_failed"):
                    st.error(f"Previous resume parsing failed: {st.session_state.get('cv_parse_error')}")
                else:
                    st.info("Resume uploaded. You can start the interview or retry parsing if the file was not read correctly.")

            with col_b:
                if st.button("Retry parsing resume"):
                    parsed = parse_and_analyze_cv(
                        st.session_state.get("cv_bytes"),
                        st.session_state.get("cv_filename", "resume.txt"),
                    )
                    if parsed:
                        st.success("Resume parsed successfully. Will be used for personalized questions.")
                    else:
                        st.error(f"Retry failed: {st.session_state.get('cv_parse_error')}")

                if st.button("Clear uploaded CV"):
                    for k in [
                        "cv_bytes",
                        "cv_filename",
                        "cv_parse_failed",
                        "cv_parse_error",
                        "candidate_profile",
                    ]:
                        st.session_state.pop(k, None)
                    st.success("Uploaded resume cleared.")
                    st.rerun()

        st.markdown(
            "**The number of questions will be determined automatically based on answer evaluation; you do not need to choose it.**"
        )

        if st.button("Start Interview", type="primary"):
            candidate_profile = st.session_state.get("candidate_profile")

            # Prefer an already-parsed profile; otherwise try to parse now from
            # whichever CV source is available (saved bytes, then raw uploaded file).
            if not candidate_profile and (st.session_state.get("cv_bytes") or cv_file is not None):
                candidate_profile = parse_and_analyze_cv(
                    st.session_state.get("cv_bytes"),
                    st.session_state.get("cv_filename", "resume.txt"),
                    cv_file=cv_file,
                )
                if candidate_profile is None and st.session_state.get("cv_parse_failed"):
                    st.warning(
                        "Unable to read or analyze the resume. Continuing without CV analysis. "
                        f"Please upload a valid TXT, PDF, or DOCX resume.\nReason: {st.session_state.get('cv_parse_error')}"
                    )

            db = SessionLocal()
            interview_session = InterviewSession(
                job_id=selected_job.id,  # كان ناقص - بدونه معندناش رابط بين الجلسة والوظيفة
                topic=", ".join(selected_job.required_topics),
                difficulty=selected_job.difficulty,
                status="in_progress",
                aggregated_score=0.0,
                consecutive_success_count=0,
                consecutive_fail_count=0,
            )
            db.add(interview_session)
            db.commit()
            db.refresh(interview_session)
            st.session_state.session_id = interview_session.id
            if candidate_profile:
                index_candidate_profile(interview_session.id, candidate_profile)
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

        if st.session_state.current_question is None:
            # نوزّع الأسئلة بالتناوب على مواضيع الوظيفة (لو أكتر من موضوع)
            topics = st.session_state.job_topics
            current_topic = topics[(q_num - 1) % len(topics)]

            with st.spinner("Preparing question..."):
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

        render_progress_bar()

        st.subheader("💬 Current Question")
        st.info(st.session_state.current_question["question"])

        answer = st.text_area("Your answer:", height=180, placeholder="Type your answer here...")

        submitted = False
        action_col1, action_col2, action_col3 = st.columns([1.2, 1, 1])
        with action_col1:
            submitted = st.button("Submit Answer", type="primary", use_container_width=True)
        with action_col2:
            if st.button("⏭️ Skip Question", use_container_width=True):
                skip_current_question()
        with action_col3:
            if st.session_state.get("confirm_end_interview"):
                if st.button("⚠️ Confirm End", use_container_width=True):
                    finish_session(
                        "user_ended",
                        "The interview has ended — we will review your answers and get back to you.",
                    )
            else:
                if st.button("🛑 End Interview", use_container_width=True):
                    st.session_state.confirm_end_interview = True
                    st.rerun()

        if st.session_state.get("confirm_end_interview"):
            st.warning("Are you sure? This cannot be undone. Click \"⚠️ Confirm End\" to finish now.")

        if submitted and answer.strip():
            with st.spinner("Evaluating..."):
                evaluation = run_async(
                    evaluate_answer(
                        st.session_state.current_question["question"],
                        st.session_state.current_question["expected_points"],
                        answer,
                    )
                )

            save_current_answer(
                "evaluated",
                user_answer=answer,
                score=float(evaluation.get("score", 0.0)),
                missing_points=evaluation.get("missing_points", []),
                feedback=evaluation.get("feedback", ""),
            )

            st.session_state.answered_questions.append(
                {
                    "question": st.session_state.current_question["question"],
                    "score": evaluation["score"],
                    "missing_points": evaluation["missing_points"],
                }
            )
            st.session_state.last_evaluation = evaluation
            score = float(evaluation.get("score", 0.0))
            st.session_state.recent_scores.append(score)
            st.session_state.questions_asked_count = (
                st.session_state.get("questions_asked_count", 0) + 1
            )

            db = SessionLocal()
            interview_session = db.get(InterviewSession, st.session_state.session_id)
            if interview_session:
                all_scores = [
                    a.get("score", 0.0)
                    for a in st.session_state.answered_questions
                    if a.get("score") is not None
                ]
                agg = sum(all_scores) / len(all_scores) if all_scores else 0.0
                interview_session.aggregated_score = agg

                consec_success = 0
                for s in reversed(st.session_state.recent_scores):
                    if s >= PASS_THRESHOLD:
                        consec_success += 1
                    else:
                        break
                interview_session.consecutive_success_count = consec_success

                consec_fail = 0
                for s in reversed(st.session_state.recent_scores):
                    if s <= FAIL_THRESHOLD:
                        consec_fail += 1
                    else:
                        break
                interview_session.consecutive_fail_count = consec_fail
                db.commit()
            db.close()

            stop_reason = None
            if len(st.session_state.recent_scores) >= CONSECUTIVE_SUCCESS:
                last_n = st.session_state.recent_scores[-CONSECUTIVE_SUCCESS:]
                if (sum(last_n) / len(last_n)) >= PASS_THRESHOLD:
                    stop_reason = "reached_pass_threshold"

            if stop_reason is None and len(st.session_state.recent_scores) >= CONSECUTIVE_FAIL:
                last_m = st.session_state.recent_scores[-CONSECUTIVE_FAIL:]
                if (sum(last_m) / len(last_m)) <= FAIL_THRESHOLD:
                    stop_reason = "reached_fail_pattern"

            if (
                stop_reason is None
                and st.session_state.questions_asked_count >= st.session_state.max_questions
            ):
                stop_reason = "reached_max_questions"

            if stop_reason:
                if stop_reason == "reached_pass_threshold":
                    message = "Thank you — your answers meet the requirements for this role. We will review them and get back to you."
                elif stop_reason == "reached_fail_pattern":
                    message = "Thank you for your time — we will review your answers and share them with the hiring team. We will get back to you with updates."
                else:
                    message = "The interview has ended — we will review your answers and get back to you." 
                finish_session(stop_reason, message)

            st.session_state.current_question = None
            st.session_state.current_answer_id = None
            st.session_state.confirm_end_interview = False
            st.session_state.stage = "answered"
            st.rerun()

    # ---------------------------------------------------------------------------
    # مرحلة عرض النتيجة
    # ---------------------------------------------------------------------------
    elif st.session_state.stage == "answered":
        render_progress_bar()

        ev = st.session_state.last_evaluation
        st.success("Question evaluated successfully")
        st.markdown(f"**Score:** {score_badge(ev['score'])}", unsafe_allow_html=True)
        st.write("**Missing points:**", ev["missing_points"])
        st.markdown(f"**Feedback:** {format_rtl_text(ev['feedback'])}", unsafe_allow_html=True)

        is_last = len(st.session_state.answered_questions) >= st.session_state.max_questions
        label = "View Report" if is_last else "Next Question"

        if st.button(label, type="primary", use_container_width=True):
            st.session_state.stage = "report" if is_last else "question"
            st.rerun()

    # ---------------------------------------------------------------------------
    # مرحلة التقرير
    # ---------------------------------------------------------------------------
    elif st.session_state.stage == "report":
        if st.session_state.get("stop_message"):
            st.info(st.session_state.get("stop_message"))

        if "final_report" not in st.session_state:
            with st.spinner("Preparing report..."):
                report = run_async(generate_report(st.session_state.answered_questions))
                st.session_state.final_report = report

                db = SessionLocal()
                interview_session = db.get(InterviewSession, st.session_state.session_id)
                if interview_session:
                    interview_session.final_report = report
                    interview_session.status = "completed"
                    db.commit()
                db.close()

        report = st.session_state.final_report
        st.subheader("📋 Final Report")
        st.markdown("---")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**Overall Score**")
            st.markdown(score_badge(report["overall_score"]), unsafe_allow_html=True)
        col2.metric("Recommendation", report["recommendation"])
        col3.metric("Status", "Completed")

        st.markdown("### Summary")
        st.markdown(format_rtl_text(report["summary"]), unsafe_allow_html=True)

        strengths = report.get("strengths", []) or []
        weaknesses = report.get("weaknesses", []) or []

        left_col, right_col = st.columns(2)
        with left_col:
            st.markdown("### Strengths")
            if strengths:
                for item in strengths:
                    st.success(f"• {item}")
            else:
                st.caption("No strengths listed")

        with right_col:
            st.markdown("### Weaknesses")
            if weaknesses:
                for item in weaknesses:
                    st.error(f"• {item}")
            else:
                st.caption("No weaknesses listed")

        st.markdown("---")
        st.markdown("### Was this report helpful?")
        if st.session_state.get("feedback_submitted"):
            st.success("Thanks for your feedback!")
        else:
            fb_col1, fb_col2 = st.columns(2)
            with fb_col1:
                if st.button("👍 Helpful", use_container_width=True):
                    save_feedback(1)
            with fb_col2:
                if st.button("👎 Not helpful", use_container_width=True):
                    save_feedback(-1)

        st.markdown("---")
        if st.button("New Interview", type="primary", use_container_width=True):
            for key in [
                "stage",
                "answered_questions",
                "current_question",
                "final_report",
                "session_id",
                "current_answer_id",
                "asked_question_ids",
                "stop_message",
                "recent_scores",
                "questions_asked_count",
                "feedback_submitted",
                "confirm_end_interview",
            ]:
                st.session_state.pop(key, None)
            st.rerun()


if __name__ == "__main__":
    main()