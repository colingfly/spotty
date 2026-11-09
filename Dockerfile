# Dockerfile (repo root) - trill backend
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# tesseract for the poster scanner, libgl/glib for OpenCV, libsndfile for waveforms
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-eng \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 libsndfile1 \
    build-essential curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

# Generated audio lives here; mount a volume in production so it survives deploys.
RUN mkdir -p /app/audio_output
ENV AUDIO_OUTPUT_DIR=/app/audio_output \
    APP_ENV=production \
    PORT=8080

EXPOSE 8080

# One worker so the in-memory rate limiter and completion worker have a single
# source of truth. Threads handle concurrent polling; raise --threads before --workers.
CMD ["bash", "-lc", "gunicorn app:app --bind 0.0.0.0:${PORT} --workers 1 --threads 8 --timeout 120"]
