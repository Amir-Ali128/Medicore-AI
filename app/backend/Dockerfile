# Medicore backend. Build once with internet; run without it.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# OpenCV (OCR) runtime libraries.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/backend
COPY requirements.txt requirements-voice.txt ./
RUN pip install -r requirements.txt

COPY . .
# Download and hash-verify the pinned Turkish speech model at BUILD time, so the
# running container never needs the internet for voice dictation.
RUN python -m app.infrastructure.voice_model_provisioning

EXPOSE 8000
# Create/upgrade tables, load reference data, then serve.
CMD ["sh", "-c", "python init_db.py && python seed_reference_data.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
