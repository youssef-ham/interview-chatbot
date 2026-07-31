"""
فهرسة بنك الأسئلة محليًا في Chroma لاستخدام RAG.
شغّله بعد تهيئة قاعدة البيانات والأسئلة:
python scr/index_documents.py
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from db.database import Base, engine
from retrieval import index_job_descriptions, index_question_bank

load_dotenv()


def main():
    Base.metadata.create_all(bind=engine)
    index_question_bank()
    index_job_descriptions()
    print("تم فهرسة بنك الأسئلة ووصف الوظائف في Chroma.")


if __name__ == "__main__":
    main()
