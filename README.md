# interview-chatbot

## نظرة عامة

`interview-chatbot` هو مشروع بوت مقابلات ذكي مصمَّم لدعم تجربة تقييم المرشحين التقنية.
المشروع يجمع بين:
- واجهة مستخدم Streamlit تفاعلية.
- API خلفي بواسطة FastAPI.
- قاعدة بيانات SQL محليّة مع دعم ترحيلات Alembic.
- محرك RAG محلي باستخدام Chroma و SentenceTransformers.
- توليد أسئلة ذكي يعتمد على بنك الأسئلة والسياق الوظيفي وملف المرشح.

## الميزات الرئيسية

- استرجاع الأسئلة باستخدام RAG محلي بدلًا من الاعتماد الكلي على الموديل.
- دعم فهرسة بنك الأسئلة، وصف الوظيفة، وملف المرشح في Chroma.
- بناء استعلام متقدم يشمل:
  - موضوع السؤال.
  - كلمات المرشح المفتاحية.
  - سياق الوظيفة.
  - بيانات المرشح الشخصية والتقنية.
- فلترة Chroma صحيحة باستخدام `$and` في الاستعلامات متعددة الحقول.
- إعادة ترتيب النتائج مع مزج تقييمات التشابه الأولية وإعادة الترتيب الأخباري.
- دعم تحديثات قاعدة البيانات المحلية مع إدارة أعمدة مرنة في `db/database.py`.

## البنية

- `app.py` - واجهة Streamlit للمقابلة.
- `main.py` - واجهة FastAPI ونقاط النهاية للخدمة.
- `retrieval.py` - منطق RAG، فهرسة Chroma، واسترجاع الأسئلة.
- `ai_service.py` - نقطة الدخول لتوليد الأسئلة الذكية، ربط بنك الأسئلة، والتوليد الاحتياطي.
- `db/` - إعداد SQLAlchemy، الجلسات، ونموذج البيانات.
- `alembic/` - بنية ترحيل قاعدة البيانات.
- `providers.py` - طبقة الاتصال بخدمات الموديل والبيانات الخارجية.

## المتطلبات

- Python 3.12 أو أحدث.
- مكتبات المشروع مذكورة في `requirements.txt` و `pyproject.toml`.

## التثبيت

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

لأدوات التطوير:

```bash
python -m pip install -e .[dev]
```

## الإعداد

1. إنشاء ملف `.env` في جذر المشروع إذا لم يكن موجودًا.
2. تكوين المتغيرات الأساسية:

```env
DATABASE_URL=sqlite:///./interview_bot.db
CHROMA_PERSIST_DIR=./chroma_store
EMBEDDING_MODEL_NAME=all-MiniLM-L6-v2
CHROMA_COLLECTION_NAME=interview_documents
```

3. إنشاء قاعدة البيانات وتحديثها:

```bash
alembic upgrade head
```

4. تهيئة البيانات والفهرسة:

```bash
python scr/seed_questions.py
python scr/index_documents.py
```

> ملاحظة: إذا كان لديك بيانات أسئلة أو وظائف جديدة، يمكنك استخدام `retrieval.index_single_question(...)` أو `retrieval.index_single_job(...)` لإضافة العناصر فورًا إلى فهرس Chroma.

## التشغيل

### واجهة المستخدم Streamlit

```bash
streamlit run app.py
```

### تشغيل API الخلفي

```bash
uvicorn main:app --reload
```

### إدارة الوظائف

إذا كنت تستخدم صفحة Streamlit الإدارية، افتح:

```bash
streamlit run app.py
```

وثم انتقل إلى الصفحة `Manage Jobs` إن كانت متاحة في قائمة Streamlit.

## كيفية عمل الـ RAG

1. يقرأ النظام بنك الأسئلة والوظائف وملفات المرشحين.
2. يبني نص استعلام يحتوي على:
   - الموضوع.
   - سياق الوظيفة (إن وجد).
   - كلمات المرشح المفتاحية.
   - ملف المرشح الشخصي.
3. يستعلم Chroma باستخدام هذا النص ويطبِّق فلترًا للمطابقة على `topic` و `difficulty`.
4. إذا لم يجد نتائج مطابقة صارمة، يتراجع إلى فلتر أوسع بالموضوع فقط.
5. يعيد الترتيب باستخدام دالة `rerank_documents` ويجمع درجات التشابه الأولى مع درجات إعادة الترتيب.

## تطوير

- تنسيق الكود:

```bash
black .
```

- فحص الشيفرة:

```bash
ruff check .
```

- تشغيل الاختبارات:

```bash
pytest
```

- إنشاء ترحيل جديد:

```bash
alembic revision --autogenerate -m "وصف التغيير"
```

## الاستضافة على Streamlit Cloud

للتشغيل على Streamlit Cloud بسرعة باستخدام SQLite المحلي، أضف القيم التالية في Secrets:

```toml
GROQ_API_KEY = "your_groq_api_key"
DATABASE_URL = "sqlite:///./interview_bot.db"
CHROMA_PERSIST_DIR = "./chroma_store"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
CHROMA_COLLECTION_NAME = "interview_documents"
PASS_THRESHOLD = 7
CONSECUTIVE_SUCCESS = 2
FAIL_THRESHOLD = 4
CONSECUTIVE_FAIL = 2
MAX_QUESTIONS = 8
```

إذا كنت تستخدم PostgreSQL محليًا للتطوير، احتفظ بإعداد `DATABASE_URL` في ملف `.env` المحلي أو في بيئتك المحلية كما هو. الكود الآن يدعم التشغيل المحلي بـ PostgreSQL وفي Cloud بـ SQLite كخيار سريع.

الملف `streamlit_cloud.env.example` يوضح نفس الإعدادات بصيغة جاهزة للنسخ.

## ملاحظات مهمة

- `db/database.py` يحتوي على منطق `init_db()` الذي ينشئ الجداول ويضيف الأعمدة المفقودة تلقائيًا عند التشغيل.
- `CHROMA_PERSIST_DIR` يمكن تغييره لتخزين الفهرس في مسار مختلف.
- يفضَّل استخدام `DATABASE_URL` بـ SQLite محليًا و PostgreSQL في بيئات الإنتاج.
- إذا واجهت خطأ في الاستيراد أو الحزم، تأكد من أن البيئة الافتراضية مفعلة وأن الحزم مثبتة.

## نقاط التحسين القادمة

- زيادة قوة الأسئلة باستخدام مجموعات بيانات أكبر لبنك الأسئلة.
- إضافة دعم Markdown أو واجهات متعددة اللغات.
- تعزيز تكامل الـ RAG مع تحليل السيرة الذاتية الذكي وملفات `.pdf`.
- بناء واجهة إدارة بيانات أسئلة / وظائف أكثر شمولا.
