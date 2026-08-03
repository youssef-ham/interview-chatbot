# Setup Guide

This document covers everything needed to run `interview-chatbot` locally, in Docker, or on
Streamlit Cloud. If you just want the short version, see the "Quick Start" section in the
main [README](../README.md).

## 1. Requirements

- Python 3.12+
- A [Groq](https://console.groq.com/) API key (free tier available) — used for all LLM calls
  (CV analysis, question personalization, answer evaluation, and report generation).
- Optional: Docker + Docker Compose, if you prefer a containerized setup.

## 2. Getting the code and dependencies

The project's dependencies are declared in `pyproject.toml` and pinned exactly in `uv.lock`.
**`uv.lock`/`pyproject.toml` is the source of truth** — `requirements.txt` is kept empty on
purpose so that platforms which only understand `requirements.txt` don't silently install a
stale or incomplete dependency set.

Using [uv](https://docs.astral.sh/uv/) (recommended, matches `uv.lock` exactly):

```bash
pip install uv
uv sync
```

Or with plain `pip`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

> **Tip:** `sentence-transformers` pulls in `torch` as a dependency. By default `pip` may
> install the much larger GPU/CUDA build even though this project only runs on CPU. To save
> several GB of download and disk space, install the CPU-only build first:
> ```bash
> pip install torch --index-url https://download.pytorch.org/whl/cpu
> ```

## 3. Configuration (environment variables)

Create a `.env` file in the project root:

```env
# Required
GROQ_API_KEY=your_groq_api_key_here

# Database (SQLite by default; use Postgres for a persistent local setup, see docker-compose.yml)
DATABASE_URL=sqlite:///./interview_bot.db

# Retrieval / vector store
CHROMA_PERSIST_DIR=./chroma_store
CHROMA_COLLECTION_NAME=interview_documents
EMBEDDING_MODEL_NAME=all-MiniLM-L6-v2
RERANKER_MODEL_NAME=cross-encoder/ms-marco-MiniLM-L-6-v2
RERANKER_TOP_N=20
RERANK_FUSION_ALPHA=0.7
HYBRID_FUSION_ALPHA=0.5
RERANK_FEEDBACK_FILE=./data/rerank_feedback.csv

# Adaptive interview stopping rules
PASS_THRESHOLD=7
CONSECUTIVE_SUCCESS=2
FAIL_THRESHOLD=4
CONSECUTIVE_FAIL=2
MAX_QUESTIONS=8
```

| Variable | Purpose | Default |
|---|---|---|
| `GROQ_API_KEY` | Auth for all LLM calls (CV analysis, question rewriting, grading, reports) | — (required) |
| `DATABASE_URL` | SQLAlchemy connection string (SQLite or Postgres) | `sqlite:///./interview_bot.db` |
| `CHROMA_PERSIST_DIR` | Where the local vector store is persisted on disk | `./chroma_store` |
| `CHROMA_COLLECTION_NAME` | Chroma collection name | `interview_documents` |
| `EMBEDDING_MODEL_NAME` | SentenceTransformers model used for vector embeddings | `all-MiniLM-L6-v2` |
| `RERANKER_MODEL_NAME` | Cross-encoder model used to re-rank retrieved candidates | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| `RERANKER_TOP_N` | How many vector-search candidates get passed to the reranker | `20` |
| `RERANK_FUSION_ALPHA` | Weight given to the reranker score vs. the retrieval score (0–1) | `0.7` |
| `HYBRID_FUSION_ALPHA` | Weight given to vector similarity vs. BM25 lexical score (0–1) | `0.5` |
| `RERANK_FEEDBACK_FILE` | CSV log of retrieval/reranking decisions, for debugging | `./data/rerank_feedback.csv` |
| `PASS_THRESHOLD` / `CONSECUTIVE_SUCCESS` | Interview stops early if the last N scores average ≥ this | `7` / `2` |
| `FAIL_THRESHOLD` / `CONSECUTIVE_FAIL` | Interview stops early if the last N scores average ≤ this | `4` / `2` |
| `MAX_QUESTIONS` | Hard cap on questions per interview regardless of scores | `8` |

## 4. Database and question bank

The database schema is created and lightly migrated automatically the first time the app
starts (`init_db()` in `db/database.py`). **Alembic is not used** — the project intentionally
uses a single, simple `init_db()` function instead of a full migration framework, since the
team is small and the schema is still evolving.

If the `questions` table is empty (e.g. first run, or a fresh SQLite file on Streamlit Cloud),
`init_db()` automatically seeds the 500-question bank from `data/questions.json` and indexes it
into Chroma. You normally don't need to run anything manually.

To do it manually instead (e.g. to re-index after changing `data/questions.json`):

```bash
python scr/seed_questions.py     # loads data/questions.json into the questions table
python scr/index_documents.py    # (re)builds the Chroma vector index
```

## 5. Running the app

**Streamlit UI (the main app):**
```bash
streamlit run app.py
```

**FastAPI backend** (optional — exposes the same interview flow as a JSON API, see
`main.py` for the endpoint list):
```bash
uvicorn main:app --reload
```

**Manage Jobs page:** available automatically in the Streamlit sidebar
(`pages/1_manage_jobs.py`) once the app is running.

**Monitoring dashboard:** available automatically in the Streamlit sidebar
(`pages/2_dashboard.py`).

## 6. Running with Docker

```bash
docker compose up --build
```

This starts two containers:
- `db` — Postgres 16, with a persisted volume.
- `app` — the Streamlit app, built from the project `Dockerfile`, connected to `db`.

Set `GROQ_API_KEY` in your shell (or a `.env` file next to `docker-compose.yml`) before running,
since it's passed through to the `app` container.

## 7. Deploying to Streamlit Cloud

Streamlit Cloud installs dependencies from `pyproject.toml`/`uv.lock` directly — it does **not**
use `Dockerfile` or `docker-compose.yml`, which only apply to self-hosted/Docker setups.

In your app's "Secrets" settings, paste:

```toml
GROQ_API_KEY = "your_groq_api_key_here"
DATABASE_URL = "sqlite:///./interview_bot.db"
CHROMA_PERSIST_DIR = "./chroma_store"
CHROMA_COLLECTION_NAME = "interview_documents"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
PASS_THRESHOLD = 7
CONSECUTIVE_SUCCESS = 2
FAIL_THRESHOLD = 4
CONSECUTIVE_FAIL = 2
MAX_QUESTIONS = 8
```

> Streamlit Cloud's free tier has limited RAM (~1GB). `sentence-transformers` + `torch` +
> `chromadb` are relatively heavy for that tier — if you see slow cold starts or crashes,
> that's the most likely cause.

The SQLite file on Streamlit Cloud is **ephemeral** — it resets on every reboot/redeploy.
`init_db()`'s auto-seed step (see section 4) re-populates it automatically each time, so this
is expected behavior, not a bug.

## 8. Development

```bash
black .                                       # format
ruff check .                                  # lint
pytest                                        # tests
python scr/evaluate_retrieval.py              # retrieval evaluation (see docs/EVALUATION.md)
python scr/evaluate_llm.py                    # LLM grading evaluation (see docs/EVALUATION.md)
```

## Troubleshooting

- **Import/package errors:** confirm your virtual environment is activated and `uv sync` (or
  `pip install -e .`) completed without errors.
- **Questions aren't personalized to the CV:** check the `questions` table isn't empty (see
  section 4) and check the app logs for `Failed to get Chroma collection` — that message means
  the retrieval layer silently fell back to non-personalized questions.
- **`HF_TOKEN` warning in logs:** harmless. Set `HF_TOKEN` (a free Hugging Face token) as an
  env var for higher download rate limits, but it isn't required.
- **Docker build context is huge / very slow:** make sure `.dockerignore` exists at the project
  root (it excludes `.venv/`, caches, and local DB files from the build context).