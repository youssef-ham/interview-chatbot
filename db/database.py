import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./interview_bot.db")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False)

if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_interview_session_columns() -> None:
    """Ensure the interview_sessions table has the required adaptive flow columns."""
    inspector = inspect(engine)
    if not inspector.has_table("interview_sessions"):
        return

    stopped_at_type = "DATETIME" if engine.dialect.name == "sqlite" else "TIMESTAMP"
    required_columns = {
        "aggregated_score": "FLOAT DEFAULT 0.0",
        "consecutive_success_count": "INTEGER DEFAULT 0",
        "consecutive_fail_count": "INTEGER DEFAULT 0",
        "stopped_reason": "TEXT",
        "stopped_at": f"{stopped_at_type}",
    }
    existing_columns = {column["name"] for column in inspector.get_columns("interview_sessions")}

    with engine.begin() as conn:
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                conn.execute(text(f"ALTER TABLE interview_sessions ADD COLUMN {column_name} {column_type}"))


def init_db() -> None:
    """Create any missing tables and apply lightweight schema updates.

    This is a deliberately lightweight migration helper used during development
    and small deployments. It creates missing tables (via SQLAlchemy metadata)
    and adds any missing columns required by the adaptive interview flow.

    Note: For production deployments prefer a dedicated migration system
    (Alembic) to manage complex schema changes and rollbacks.
    """
    from db.models import Base as ModelsBase

    ModelsBase.metadata.create_all(bind=engine)
    ensure_interview_session_columns()
