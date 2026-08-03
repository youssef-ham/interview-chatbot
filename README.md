# interview-chatbot

## Problem

Technical recruiters and hiring teams spend a large amount of time conducting first-round
technical interviews to screen candidates before they even reach a human interviewer.
This is repetitive, time-consuming, and inconsistent — different interviewers ask different
questions and grade answers with different standards.

`interview-chatbot` solves this by acting as an automated first-round technical interviewer:
a candidate uploads their CV, is matched to a specific job's required topics and difficulty,
and receives interview questions personalized to their actual skills and projects (pulled
from a curated question bank via retrieval, not invented from scratch). Answers are graded
automatically against clear expected points, the interview adaptively stops early once a
clear pass/fail pattern emerges, and the hiring team receives a structured final report
(strengths, weaknesses, recommendation) — cutting down manual screening time significantly.

## Overview

`interview-chatbot` is an intelligent interview assistant built with Streamlit for the candidate-facing UI and FastAPI for backend services. The project combines:

- Interactive Streamlit interview experience.
- FastAPI backend for question generation and scoring.
- SQL database support with SQLAlchemy and Alembic.
- Local RAG-like retrieval using Chroma and SentenceTransformers.
- Candidate profile handling via resume upload and question personalization.

## Key Features

- RAG-style question selection from a real question bank.
- Job and resume context used to generate intelligent interview prompts.
- Local retrieval with Chroma including topic and difficulty filtering.
- Lightweight reranking fallback when heavy models are unavailable.
- Database bootstrap logic with SQLite fallback for quick Streamlit Cloud deployment.

## Repository Structure

- `app.py` - Streamlit app for the interview UI.
- `main.py` - FastAPI backend entrypoint.
- `retrieval.py` - RAG retrieval, question indexing, and similarity logic.
- `ai_service.py` - Smart question generation and report logic.
- `db/` - SQLAlchemy setup, session management, and models.
- `alembic/` - Database migration configuration.
- `scr/` - helper scripts for seeding and indexing data.

## Requirements

- Python 3.12 or newer.
- Dependencies are listed in `requirements.txt` and `pyproject.toml`.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

> Note: Resume upload supports `TXT`, `PDF`, and `DOCX` resumes. The required parser libraries are included in `requirements.txt` so Streamlit Cloud installs them automatically on deploy.

For development dependencies:

```bash
python -m pip install -e .[dev]
```

## Configuration

Create a `.env` file in the project root with the required settings:

```env
DATABASE_URL=sqlite:///./interview_bot.db
CHROMA_PERSIST_DIR=./chroma_store
EMBEDDING_MODEL_NAME=all-MiniLM-L6-v2
CHROMA_COLLECTION_NAME=interview_documents
```

If the question bank is empty, open the Streamlit Manage Jobs page and use the provided button to seed the database from `data/questions.json`.

To initialize the database schema:

```bash
alembic upgrade head
```

To seed and index data:

```bash
python scr/seed_questions.py
python scr/index_documents.py
```

## Running the App

### Streamlit UI

```bash
streamlit run app.py
```

### Backend API

```bash
uvicorn main:app --reload
```

### Manage Jobs

Open the Streamlit app and navigate to the `Manage Jobs` page if available.

## How RAG Works

1. The system reads job postings, question bank entries, and candidate context.
2. It builds a query containing:
   - topic
   - job context
   - candidate keywords
   - candidate profile
3. It queries Chroma and filters by `topic` and `difficulty`.
4. If strict filtering returns no results, it falls back to broader topic matching.
5. It reranks results and combines retrieval and reranking scores.

## Development

- Format code:

```bash
black .
```

- Lint code:

```bash
ruff check .
```

- Run tests:

```bash
pytest
```

- Create a new migration:

```bash
alembic revision --autogenerate -m "Add description"
```

## Streamlit Cloud Deployment

For fast Streamlit Cloud deployment with local SQLite, add these secrets:

```toml
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

If you are using PostgreSQL locally for development, keep `DATABASE_URL` in your local `.env` file. The app supports PostgreSQL for development and SQLite as a fallback for Cloud deployment.

The file `streamlit_cloud.env.example` contains the same configuration in an example format.

## Notes

- `db/database.py` includes `init_db()` logic that creates missing tables and adapts the schema on startup.
- `CHROMA_PERSIST_DIR` controls where the local Chroma store is persisted.
- Use SQLite locally for quick setup and PostgreSQL for production-grade deployments.
- If you encounter import or package errors, confirm your virtual environment is activated and dependencies are installed.

## Future Improvements

- Expand the question bank with more realistic interview content.
- Add structured admin tooling for job/question management.
- Improve multi-language UI support.
- Add optional PDF resume support once dependency constraints are resolved.
