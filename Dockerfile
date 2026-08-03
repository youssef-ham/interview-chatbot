FROM python:3.12-slim

WORKDIR /app

# System deps needed by some packages (e.g. sentence-transformers/torch build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv \
    # نصّب نسخة CPU من torch بس (بدل نسخة CUDA اللي حجمها أضعاف كذا)
    && pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && uv pip install --system --no-cache -r pyproject.toml

COPY . .

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]