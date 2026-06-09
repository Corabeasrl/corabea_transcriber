FROM ghcr.io/astral-sh/uv:0.5.18 AS uv

FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WHISPER_DOWNLOAD_ROOT=/models \
    OMP_NUM_THREADS=4 \
    UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_CACHE=1

WORKDIR /app

COPY requirements.txt .
RUN uv pip install --system -r requirements.txt

COPY app ./app

VOLUME ["/models"]

CMD ["celery", "-A", "app.celery_app", "worker", "--loglevel", "info"]
