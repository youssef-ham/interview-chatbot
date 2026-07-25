from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, JSON, ForeignKey, DateTime,Text
from sqlalchemy.orm import relationship 
from .database import Base

class Question(Base):
    __tablename__ = "questions"
    
    id = Column(String, primary_key=True)
    topic = Column(String, nullable=False, index=True)
    difficulty = Column(String, nullable=False, index=True)
    question_type = Column(String)
    question = Column(Text, nullable=False)
    expected_points = Column(JSON, nullable=False)
    subtopic = Column(String)
    sample_answer = Column(Text, nullable=True)
    tags = Column(JSON)
    source = Column(String)
    
    
class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    topic = Column(String, nullable=False)
    difficulty = Column(String, nullable=False)
    status = Column(String, default="in_progress")
    created_at = Column(DateTime, default=datetime.utcnow)
    final_report = Column(JSON, nullable=True)
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
    
class Job(Base):
    """وظيفة معلنة، بيضيفها صاحب الشركة من واجهة الإدارة"""
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    required_topics = Column(JSON, nullable=False)  # ["Python", "LLM"] - بتربطها ببنك الأسئلة
    difficulty = Column(String, nullable=False)  # junior / mid / senior
    is_active = Column(String, default="active")  # active / closed
    created_at = Column(DateTime, default=datetime.utcnow)