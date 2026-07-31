# interview-chatbot

A Python interview chatbot with a FastAPI backend, Streamlit UI, and AI-powered question generation.

## What changed
- Local RAG retrieval for personalized question generation via Chroma and SentenceTransformers.
- Lightweight schema initialization support in `db/database.py` for local/dev environments.
- Alembic-based migrations for database schema changes.
- Formatting/linting setup via Black and Ruff.

## Setup
1. Create a virtual environment and activate it.
2. Install dependencies:
   ```bash
   python -m pip install -r requirements.txt
   ```
   For development tools (Black, Ruff, Alembic, pytest), use:
   ```bash
   python -m pip install -e .[dev]
   ```
3. Set required environment variables in `.env`.
4. Create/update the database schema and apply migrations:
   ```bash
   alembic upgrade head
   ```
5. Seed the database and index the question bank:
   ```bash
   python scr/seed_questions.py
   python scr/index_documents.py
   ```
6. Run the UI:
   ```bash
   streamlit run app.py
   ```
   Run the API:
   ```bash
   uvicorn main:app --reload
   ```

## Development tools
- Format code: `black .`
- Lint code: `ruff check .`
- Create a new migration: `alembic revision --autogenerate -m "your message"`
