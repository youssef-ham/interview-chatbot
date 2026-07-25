import json
from pathlib import Path

from db.database import SessionLocal
from db.models import Question


def seed_database():
    db = SessionLocal()

    # لو البيانات موجودة بالفعل، متكررهاش
    if db.query(Question).first():
        print("Database already seeded")
        db.close()
        return

    # مسار ملف الأسئلة
    BASE_DIR = Path(__file__).resolve().parent.parent
    QUESTIONS_FILE = BASE_DIR / "data" / "questions.json"

    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        questions = json.load(f)

    for q in questions:
        question = Question(
            id=q["id"],
            topic=q["topic"],
            subtopic=q.get("subtopic"),
            difficulty=q["difficulty"],
            question_type=q["question_type"],
            question=q["question"],
            expected_points=q["expected_points"],
            sample_answer=q.get("sample_answer"),
            tags=q.get("tags"),
            source=q.get("source"),
        )

        db.add(question)

    db.commit()
    db.close()

    print(f"Seeded {len(questions)} questions successfully!")