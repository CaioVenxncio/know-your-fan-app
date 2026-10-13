# Reproducible local runtime with Tesseract OCR. Not a deployment configuration.
# Build: docker build -t know-your-fan .
# Run:   docker run --rm -p 8501:8501 know-your-fan

FROM ghcr.io/astral-sh/uv:0.13.0 AS uv

FROM python:3.13-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-por tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app

# Dependencies first, for layer caching.
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY main.py ./
COPY .streamlit ./.streamlit
RUN uv sync --locked --no-dev

RUN useradd --create-home --uid 10001 kyf \
    && mkdir -p /app/.data \
    && chown kyf /app/.data

USER kyf
# OMP_THREAD_LIMIT=1: each Tesseract process uses one CPU thread, so total OCR
# CPU use stays proportional to KYF_OCR_MAX_CONCURRENCY instead of
# concurrency x cores.
ENV PATH="/opt/venv/bin:${PATH}" \
    KYF_DB_PATH=/app/.data/kyf_demo.db \
    OMP_THREAD_LIMIT=1

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=3)"

CMD ["streamlit", "run", "main.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
