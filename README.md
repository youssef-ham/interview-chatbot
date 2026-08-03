# interview-chatbot 🎙️

An AI-powered technical interview assistant. A candidate uploads their CV, is matched to a
job's required topics, and answers questions that are **personalized to their actual skills and
projects** (not generic trivia) — pulled from a curated question bank via retrieval and graded
automatically against clear expected points, with an adaptive stop rule and a structured final
report for the hiring team.

Built for an Arabic-speaking candidate base, but the interface and question bank currently run
in English (see [Future Improvements](#future-improvements)).

> 📹 **Demo video:** _add a short screen recording here (see "Recording a demo video" below)._

## Table of contents

- [Problem](#problem)
- [How it works](#how-it-works)
- [Data](#data)
- [Screenshots](#screenshots)
- [Quick start](#quick-start)
- [Walkthrough example](#walkthrough-example)
- [Monitoring](#monitoring)
- [Evaluation](#evaluation)
- [Repository structure](#repository-structure)
- [Tech stack](#tech-stack)
- [How this project maps to the evaluation criteria](#how-this-project-maps-to-the-evaluation-criteria)
- [Future improvements](#future-improvements)

## Problem

Technical recruiters and hiring teams spend a large amount of time conducting first-round
technical interviews to screen candidates before they even reach a human interviewer. This is
repetitive, time-consuming, and inconsistent — different interviewers ask different questions
and grade answers by different standards.

`interview-chatbot` automates this first round: a candidate uploads their CV, is matched to a
specific job's required topics and difficulty, and receives interview questions personalized to
their actual skills and projects. Answers are graded automatically against clear expected
points, the interview adaptively stops early once a clear pass/fail pattern emerges, and the
hiring team receives a structured final report (strengths, weaknesses, recommendation) — cutting
down manual screening time significantly.

## How it works

```
 Candidate                                    Recruiter / hiring team
     │                                                  │
     ▼                                                  │
 1. Picks a job + uploads CV (PDF/DOCX/TXT, optional)    │
     │                                                  │
     ▼                                                  │
 2. CV is parsed → analyzed by an LLM into a structured  │
    profile (skills, projects, experience level)         │
     │                                                  │
     ▼                                                  │
 3. For each question:                                  │
    a. Hybrid retrieval (vector search + BM25) pulls     │
       candidate questions from the question bank,       │
       filtered by job topic/difficulty                  │
    b. A cross-encoder reranks the candidates             │
    c. The top question is rewritten by an LLM to         │
       reference the candidate's real skills/projects     │
     │                                                  │
     ▼                                                  │
 4. Candidate answers → LLM grades the answer against     │
    the question's expected points (0–10, with feedback)  │
     │                                                  │
     ▼                                                  │
 5. Adaptive stopping: interview ends early once scores   │
    show a clear pass pattern or fail pattern, or after    │
    a max number of questions                             │
     │                                                  │
     ▼                                                  ▼
 6. Candidate sees a summary  ──────────────▶  Structured final report:
                                                overall score, recommendation,
                                                strengths, weaknesses
```

Retrieval details (topic/difficulty filtering, hybrid search, reranking) are in
`retrieval.py`; grading and report generation are in `ai_service.py`.

## Data

- **Question bank** (`data/questions.json`): 500 curated technical questions across 11 topics
  (`Python`, `Machine Learning`, `Deep Learning`, `NLP`, `LLM`, `MLOps`, `Data Engineering`,
  `Statistics`, `System Design`, `Computer Vision`, `Behavioral`) and 3 difficulty levels
  (`junior`, `mid`, `senior`). Each question has an id, topic/subtopic, difficulty, the question
  text, and a set of weighted **expected points** used for grading, e.g.:
  ```json
  {
    "id": "python_001",
    "topic": "Python",
    "difficulty": "junior",
    "question": "What is the difference between a list and a tuple?",
    "expected_points": [
      {"point": "Correct understanding of the concept", "weight": 0.4},
      {"point": "Technical accuracy", "weight": 0.4},
      {"point": "Relevant example or use case", "weight": 0.2}
    ]
  }
  ```
- **Jobs**: created/managed through the app's "Manage Jobs" page — each job defines a title,
  description, required topics (mapped to the question bank's topics), and difficulty level.
- **Candidate CVs**: uploaded per-interview (PDF/DOCX/TXT), not stored as raw files — only the
  LLM-derived structured profile (skills, projects, experience) is kept.

## Screenshots

> _Add screenshots here once you have a running instance — this section is a placeholder._
> Recommended shots: the job-selection screen, a personalized question in progress, the final
> report, and the monitoring dashboard.

| Interview flow | Final report | Monitoring dashboard |
|---|---|---|
| `docs/screenshots/interview.png` | `docs/screenshots/report.png` | `docs/screenshots/dashboard.png` |

### Recording a demo video

In the running Streamlit app, open the **⋮ menu (top-right) → Record a screencast**
([Streamlit docs](https://docs.streamlit.io/develop/concepts/architecture/app-chrome)), record a
short walkthrough (job selection → CV upload → a question or two → final report), then drag and
drop the downloaded video file into this README using the
[GitHub web editor](https://stackoverflow.com/a/4279746) — GitHub will host it and insert an
embeddable link automatically.

## Quick start

```bash
pip install uv
uv sync
cp .env.example .env   # then add your GROQ_API_KEY
streamlit run app.py
```

Full setup (Docker, Streamlit Cloud, all environment variables, troubleshooting) is in
**[docs/SETUP.md](docs/SETUP.md)**.

## Walkthrough example

1. Candidate selects **"Backend Engineer"** and uploads a CV mentioning a Django + PostgreSQL
   project and 2 years of Python experience.
2. First question (topic: Python, difficulty: junior→mid based on the job) comes back
   personalized, e.g.: *"You mentioned building a Django + PostgreSQL API — how would you avoid
   the N+1 query problem when serializing related objects?"* instead of a generic textbook
   question.
3. Candidate answers; the LLM grades it against the question's expected points and returns a
   score (0–10) plus specific missing points.
4. After a few questions, if the candidate consistently scores ≥7, the interview ends early with
   a "meets requirements" message — the recruiter doesn't need 8 full questions to see a clear
   pass.
5. The recruiter opens the final report: overall score, recommendation (e.g. "Recommend for next
   round"), and a bullet list of concrete strengths/weaknesses tied to what was actually asked.

## Monitoring

The **Monitoring Dashboard** page (`pages/2_dashboard.py`, in the app sidebar) shows:
total/completed interviews, score distribution, interviews over time, why interviews ended
(pass/fail/max-questions), average score per job, and 👍/👎 user feedback collected at the end of
each report (see `save_feedback` in `app.py`).

## Evaluation

Retrieval quality (hybrid search + reranking vs. vector-only) and LLM grading quality (prompt
comparison against a hand-labeled golden set) are both evaluated with reproducible scripts.
See **[docs/EVALUATION.md](docs/EVALUATION.md)** for methodology, metrics, and how to run them.

## Repository structure

```
app.py                     Streamlit UI — the main candidate-facing app
main.py                    FastAPI backend (same interview flow as a JSON API)
ai_service.py               Question generation, answer grading, report generation (LLM calls)
retrieval.py                Hybrid retrieval (vector + BM25), reranking, Chroma indexing
reranker.py                 Cross-encoder reranking model wrapper
cv_parser.py / cv_analyzer.py   CV text extraction and LLM-based profile analysis
question_rewriter.py        Rewrites a bank question to reference the candidate's real profile
providers.py                 LLM provider abstraction (Groq)
db/                          SQLAlchemy models, session management, schema bootstrap
pages/                       Streamlit extra pages: Manage Jobs, Monitoring Dashboard
scr/                          Seeding, indexing, and evaluation scripts
data/questions.json           The 500-question bank
docs/                         Extended documentation (setup, evaluation)
Dockerfile / docker-compose.yml   Containerized app + Postgres
```

## Tech stack

- **UI:** Streamlit
- **API:** FastAPI
- **LLM:** Groq (Llama models)
- **Retrieval:** ChromaDB (vector store) + SentenceTransformers (embeddings) + rank-bm25
  (lexical search) + a cross-encoder reranker
- **Database:** SQLAlchemy, SQLite (default/dev) or PostgreSQL (Docker/production)
- **Deployment:** Streamlit Cloud, or Docker Compose for self-hosting

## How this project maps to the evaluation criteria

| Criterion | Where to look |
|---|---|
| Problem description | [Problem](#problem) above |
| Retrieval flow (knowledge base + LLM) | `retrieval.py` (Chroma + BM25 + reranker) feeding into `ai_service.py` (LLM) |
| Retrieval evaluation | `scr/evaluate_retrieval.py`, methodology in [docs/EVALUATION.md](docs/EVALUATION.md) |
| LLM evaluation | `scr/evaluate_llm.py`, methodology in [docs/EVALUATION.md](docs/EVALUATION.md) |
| Interface | Streamlit UI (`app.py`) + FastAPI (`main.py`) |
| Ingestion pipeline | `scr/seed_questions.py` + `scr/index_documents.py`, also auto-run by `init_db()` on first startup (`db/database.py`) |
| Monitoring | [Monitoring](#monitoring) above — feedback collection + `pages/2_dashboard.py` |
| Containerization | `Dockerfile` + `docker-compose.yml` (app + Postgres) |
| Reproducibility | [docs/SETUP.md](docs/SETUP.md) — exact steps, pinned dependencies (`uv.lock`), sample data included |
| Hybrid search (best practice) | `retrieval.py` — BM25 + vector fusion before reranking |
| Document re-ranking (best practice) | `reranker.py`, fused in `retrieval.py` |
| Cloud deployment (bonus) | Deployed on Streamlit Cloud |

## Future improvements

- Expand the question bank with more realistic, up-to-date interview content.
- Add structured admin tooling for job/question management beyond the basic Manage Jobs page.
- Full Arabic UI support (question bank and interface are currently English-only).
- Automate the ingestion pipeline with a proper orchestration tool (e.g. Prefect/Airflow) instead
  of manually-triggered scripts, for the full ingestion-pipeline evaluation score.
- Move the CV-personalized question rewriting into true retrieval **query** rewriting (currently
  it rewrites the retrieved question's phrasing, not the search query itself).