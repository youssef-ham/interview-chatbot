"""
سكريبت لملء الـ database بالأسئلة من data/questions.json.
شغّله بـ: python scripts/seed_questions.py
"""

import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import Base, SessionLocal, engine
from db.models import Question


def seed():
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    questions_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "questions.json"
    )

    with open(questions_path, encoding="utf-8") as f:
        questions = json.load(f)

    added, skipped = 0, 0
    for q in questions:
        exists = db.query(Question).filter_by(id=q["id"]).first()
        if exists:
            skipped += 1
            continue

        db.add(
            Question(
                id=q["id"],
                topic=q["topic"],
                subtopic=q.get("subtopic"),
                difficulty=q["difficulty"],
                question_type=q.get("question_type"),
                question=q["question"],
                expected_points=q["expected_points"],
                sample_answer=q.get("sample_answer"),
                tags=q.get("tags"),
                source=q.get("source"),
            )
        )
        added += 1

    db.commit()
    db.close()
    print(f"تمت إضافة {added} سؤال جديد، وتخطي {skipped} سؤال كان موجود بالفعل.")


if __name__ == "__main__":
    seed()
