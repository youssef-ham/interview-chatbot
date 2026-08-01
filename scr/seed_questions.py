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
from retrieval import index_single_question


def seed():
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    questions_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "questions.json"
    )

    with open(questions_path, encoding="utf-8") as f:
        questions = json.load(f)

    added, skipped = 0, 0
    newly_added_questions = []

    for q in questions:
        exists = db.query(Question).filter_by(id=q["id"]).first()
        if exists:
            skipped += 1
            continue

        new_question = Question(
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
        db.add(new_question)
        newly_added_questions.append(new_question)
        added += 1

    db.commit()

    # نفهرس بس الأسئلة الجديدة اللي دخلت فعلاً - مش هنعيد فهرسة كل البنك من الصفر
    indexed, failed = 0, 0
    for question in newly_added_questions:
        try:
            index_single_question(question)
            indexed += 1
        except Exception as e:
            failed += 1
            print(f"تحذير: فشلت فهرسة السؤال {question.id}: {e}")

    db.close()
    print(f"تمت إضافة {added} سؤال جديد، وتخطي {skipped} سؤال كان موجود بالفعل.")
    if added:
        print(f"تم فهرسة {indexed} سؤال في Chroma" + (f"، وفشل فهرسة {failed}." if failed else "."))


if __name__ == "__main__":
    seed()