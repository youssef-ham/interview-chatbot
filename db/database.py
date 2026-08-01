import logging

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base, sessionmaker

from config import get_setting

DATABASE_URL = get_setting("DATABASE_URL", "sqlite:///./interview_bot.db")
FALLBACK_DATABASE_URL = "sqlite:///./interview_bot.db"


def _is_sqlite_url(url: str) -> bool:
    return url.startswith("sqlite")


def _create_engine(url: str):
    connect_args = {"check_same_thread": False} if _is_sqlite_url(url) else {}
    return create_engine(url, connect_args=connect_args, echo=False)


def _enable_sqlite_fk(engine):
    @event.listens_for(engine, "connect")
    def _listener(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def _build_engine() -> object:
    try:
        engine = _create_engine(DATABASE_URL)
    except SQLAlchemyError as exc:
        logging.warning(
            "Unable to create engine for DATABASE_URL=%s; falling back to local SQLite (%s). Error: %s",
            DATABASE_URL,
            FALLBACK_DATABASE_URL,
            exc,
        )
        engine = _create_engine(FALLBACK_DATABASE_URL)
        _enable_sqlite_fk(engine)
        return engine

    if _is_sqlite_url(DATABASE_URL):
        _enable_sqlite_fk(engine)
        return engine

    try:
        with engine.connect():
            pass
    except SQLAlchemyError as exc:
        logging.warning(
            "Unable to connect to DATABASE_URL=%s; falling back to local SQLite (%s). Error: %s",
            DATABASE_URL,
            FALLBACK_DATABASE_URL,
            exc,
        )
        engine = _create_engine(FALLBACK_DATABASE_URL)
        _enable_sqlite_fk(engine)

    return engine


engine = _build_engine()
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
                conn.execute(
                    text(f"ALTER TABLE interview_sessions ADD COLUMN {column_name} {column_type}")
                )


def init_db() -> None:
    """Create any missing tables and apply lightweight schema updates.

    هذا هو نظام إدارة الـ schema الوحيد المعتمد في المشروع (تم اتخاذ قرار
    بعدم استخدام Alembic حاليًا لأن المشروع لسه في التطوير وفريق صغير).

    لو الحاجة لإدارة schema أكثر تعقيدًا ظهرت مستقبلًا (بيانات إنتاج حقيقية،
    أكتر من مطور بيغيّر الـ schema بالتوازي، حاجة لـ rollback منظم)،
    يستاهل وقتها نراجع القرار ده ونضيف Alembic من جديد.
    """
    from db.models import Base as ModelsBase

    ModelsBase.metadata.create_all(bind=engine)
    ensure_interview_session_columns()
