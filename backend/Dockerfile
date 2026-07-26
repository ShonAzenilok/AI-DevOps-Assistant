# Build from repo root:
#   docker build -f backend/Dockerfile .
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml backend/README.md ./backend/
COPY backend/app ./backend/app
COPY hello-world ./hello-world

WORKDIR /app/backend
RUN pip install --no-cache-dir .

ENV HOST=0.0.0.0
ENV PORT=8000
ENV DEBUG_CODE_ROOT=/app/hello-world

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
