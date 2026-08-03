# Evaluation

This document explains how retrieval and LLM output quality are evaluated in this project,
and how to reproduce the results yourself.

## Retrieval evaluation

**Script:** `scr/evaluate_retrieval.py`

**Method:** 100 questions are sampled from the question bank. For each one, a *realistic*
query is built (topic + difficulty + a few keywords/tags) — deliberately **not** the exact
text that was indexed for that question, so the evaluation reflects real usage rather than a
question trivially matching itself.

Two retrieval configurations are compared:
- `vector_only` — Chroma vector similarity search, filtered by topic.
- `rerank` — the same vector candidates, re-ordered by a cross-encoder reranker
  (`reranker.py`).

**Metrics:** Hit Rate@5 (did the "correct" question appear in the top 5 results?) and MRR
(Mean Reciprocal Rank — rewards the correct result appearing *higher*, not just present).

**Run it:**
```bash
python scr/evaluate_retrieval.py
```

The production retrieval path (`retrieval.py`) additionally combines **BM25 lexical search**
with vector search (hybrid search) before reranking — see the "How Retrieval Works" section in
the main README. `HYBRID_FUSION_ALPHA` controls the vector/BM25 balance and can be tuned.

## LLM (answer grading) evaluation

**Script:** `scr/evaluate_llm.py`

**Method:** a small hand-labeled "golden set" of (question, expected points, candidate answer,
expected score) pairs, covering clear cases (empty/wrong answers, partially correct answers,
fully correct answers). Two grading system-prompt variants are run against the same golden set:

- `PROMPT_V1` — the current production prompt.
- `PROMPT_V2` — a stricter variant that penalizes vague/generic answers more aggressively.

**Metric:** Mean Absolute Error (MAE) between the LLM's score and the expected score — lower is
better.

**Run it:**
```bash
python scr/evaluate_llm.py
```

Whichever prompt has the lower MAE should be used as `EVAL_SYSTEM_PROMPT` in `ai_service.py`.

## Extending these evaluations

- The retrieval golden set is currently generated automatically from the question bank itself.
  For a stronger evaluation, replace it with real historical queries (e.g. logged
  `candidate_profile` + topic combinations from `data/rerank_feedback.csv`).
- The LLM golden set (`GOLDEN_SET` in `scr/evaluate_llm.py`) is intentionally small (5 examples)
  to keep the script fast and free to run. Extending it with more edge cases (partially correct
  answers with unusual wording, answers in Arabic, etc.) will make the comparison more robust.