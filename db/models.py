from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from db.database import Base


class Question(Base):
    __tablename__ = "questions"
    id = Column(String, primary_key=True)
    topic = Column(String, nullable=False, index=True)
    subtopic = Column(String)
    difficulty = Column(String, nullable=False, index=True)
    question_type = Column(String)
    question = Column(Text, nullable=False)
    expected_points = Column(JSON, nullable=False)
    sample_answer = Column(Text, nullable=True)
    tags = Column(JSON)
    source = Column(String)


class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    required_topics = Column(JSON, nullable=False)
    difficulty = Column(String, nullable=False)
    is_active = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)


class InterviewSession(Base):
    __tablename__ = "interview_sessions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=True)
    topic = Column(String, nullable=False)
    difficulty = Column(String, nullable=False)
    status = Column(String, default="in_progress")
    created_at = Column(DateTime, default=datetime.utcnow)
    final_report = Column(JSON, nullable=True)
    candidate_profile = Column(JSON, nullable=True)
    # New tracking fields for adaptive stopping and auditing
    aggregated_score = Column(Float, default=0.0)
    consecutive_success_count = Column(Integer, default=0)
    consecutive_fail_count = Column(Integer, default=0)
    stopped_reason = Column(String, nullable=True)
    stopped_at = Column(DateTime, nullable=True)
    answers = relationship("Answer", back_populates="session", cascade="all, delete-orphan")


class Answer(Base):
    __tablename__ = "answers"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("interview_sessions.id"), nullable=False)
    question_id = Column(String, ForeignKey("questions.id"), nullable=True)
    question_text = Column(Text, nullable=False)
    expected_points = Column(JSON, nullable=False)
    user_answer = Column(Text, nullable=True)
    score = Column(Float, nullable=True)
    matched_points = Column(JSON, nullable=True)
    missing_points = Column(JSON, nullable=True)
    feedback = Column(Text, nullable=True)
    status = Column(String, default="pending")
    session = relationship("InterviewSession", back_populates="answers")
