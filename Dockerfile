FROM python:3.12-slim

WORKDIR /workspace

# Keep image minimal and deterministic for CLI usage.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY pyproject.toml ./
COPY src ./src
COPY tests ./tests
COPY docs ./docs
COPY README.md ./README.md
COPY README.en.md ./README.en.md

ENTRYPOINT ["python", "-m", "src.brag_cli"]
