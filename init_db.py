from db.database import engine, Base
import db.models

from db.seed import seed_database

# إنشاء الجداول
Base.metadata.create_all(bind=engine)

# إدخال البيانات
seed_database()

print("Database initialized successfully!")