"""
لوحة مراقبة (Monitoring Dashboard) - إحصائيات عن المقابلات، النتائج، وتقييم المستخدمين.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from db.database import SessionLocal
from db.models import Answer, Feedback, InterviewSession, Job

st.set_page_config(page_title="Monitoring Dashboard", page_icon="📊")
st.title("📊 Monitoring Dashboard")


@st.cache_data(ttl=30)
def load_data():
    db = SessionLocal()
    sessions = pd.read_sql(db.query(InterviewSession).statement, db.bind)
    answers = pd.read_sql(db.query(Answer).statement, db.bind)
    feedback = pd.read_sql(db.query(Feedback).statement, db.bind)
    jobs = pd.read_sql(db.query(Job).statement, db.bind)
    db.close()
    return sessions, answers, feedback, jobs


sessions, answers, feedback, jobs = load_data()

if sessions.empty:
    st.info("No interview sessions yet. Run an interview first to see data here.")
    st.stop()

# ---------------------------------------------------------------------------
# Top-level metrics
# ---------------------------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Interviews", len(sessions))
col2.metric("Completed", int((sessions["status"] == "completed").sum()))
avg_score = sessions["aggregated_score"].mean()
col3.metric("Avg Score", f"{avg_score:.1f}/10" if pd.notna(avg_score) else "—")
if not feedback.empty:
    positive_pct = (feedback["rating"] > 0).mean() * 100
    col4.metric("Positive Feedback", f"{positive_pct:.0f}%")
else:
    col4.metric("Positive Feedback", "—")

st.markdown("---")

# 1) Distribution of aggregated scores
st.subheader("1. Score Distribution")
st.bar_chart(sessions["aggregated_score"].dropna())

# 2) Interviews over time
st.subheader("2. Interviews Over Time")
sessions["created_at"] = pd.to_datetime(sessions["created_at"])
by_day = sessions.groupby(sessions["created_at"].dt.date).size()
st.line_chart(by_day)

# 3) Stop reason breakdown
st.subheader("3. Why Interviews Ended (stop_reason)")
if "stopped_reason" in sessions.columns and sessions["stopped_reason"].notna().any():
    st.bar_chart(sessions["stopped_reason"].value_counts())
else:
    st.caption("No stop reason data yet.")

# 4) Average score per job
st.subheader("4. Average Score per Job")
if not jobs.empty:
    merged = sessions.merge(jobs, left_on="job_id", right_on="id", suffixes=("", "_job"))
    if not merged.empty:
        st.bar_chart(merged.groupby("title")["aggregated_score"].mean())
    else:
        st.caption("No job-linked sessions yet.")

# 5) Feedback breakdown (thumbs up vs down)
st.subheader("5. User Feedback")
if not feedback.empty:
    counts = feedback["rating"].map({1: "👍 Helpful", -1: "👎 Not helpful"}).value_counts()
    st.bar_chart(counts)
else:
    st.caption("No feedback submitted yet.")

# 6) Answer score distribution (bonus chart)
st.subheader("6. Individual Answer Scores")
if not answers.empty and answers["score"].notna().any():
    st.bar_chart(answers["score"].dropna())
else:
    st.caption("No scored answers yet.")

st.markdown("---")
if feedback.empty is False and feedback["comment"].notna().any():
    st.subheader("Recent Feedback Comments")
    st.dataframe(
        feedback[feedback["comment"].notna()][["created_at", "rating", "comment"]]
        .sort_values("created_at", ascending=False)
        .head(20)
    )
