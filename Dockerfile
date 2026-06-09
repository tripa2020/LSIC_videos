# LSIC Event→Briefing pipeline — CPU-only container (no GPU; all "AI" is the Gemini API).
# Packages the validated pipeline AS-IS — the entrypoint is the same `python -m src.main`
# CLI used locally, so a cloud run produces the same Report bundle as a local run.
FROM python:3.11-slim

# System deps:
#   ffmpeg      — audio extract + ffprobe (one package provides both)
#   libreoffice — PPTX → PDF render (src/pptx_handler.py); the big layer (~700 MB)
#   libgl1 + libglib2.0-0 — OpenCV runtime (scenedetect / cv2 frame grab)
#   curl        — Zoom recording fetch (src/ingest.py curl path)
#   fonts-dejavu-core — legible LibreOffice slide renders
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libreoffice \
        libgl1 \
        libglib2.0-0 \
        curl \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps first so this layer caches unless requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pipeline source + acquisition front-end (selected_manifest, group_manifest, run_corpus.sh).
# .claude/ is intentionally absent — _load_role_pool degrades to [] (roles come from the prompt).
COPY src/ src/
COPY download_lsic/ download_lsic/

# GEMINI_API_KEY is injected at run time (-e GEMINI_API_KEY / service env) — NEVER baked in.
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "-m", "src.main"]
CMD ["--help"]
