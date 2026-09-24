# One container for the whole app: FastAPI serves the API, the photos and the
# built React frontend. Works on Railway, Hugging Face Spaces (Docker) and any Docker host.
#
#   docker build -t lostfound .
#   docker run -p 7860:7860 lostfound        -> http://localhost:7860

# ---- 1. Build the frontend -------------------------------------------------
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- 2. Backend ------------------------------------------------------------
FROM python:3.12-slim
RUN useradd -m -u 1000 user
ENV PYTHONUNBUFFERED=1 HF_HOME=/home/user/.cache/huggingface HF_HUB_DISABLE_SYMLINKS_WARNING=1
WORKDIR /app

# CPU-only torch: the default wheel bundles CUDA and is several GB larger.
COPY backend/requirements.txt backend/
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r backend/requirements.txt

COPY --chown=user backend/ backend/
COPY --from=web --chown=user /web/dist frontend/dist
RUN chown user /app
USER user

# Download both models at build time, so the app starts in seconds.
RUN python -c "from sentence_transformers import SentenceTransformer as S; S('all-MiniLM-L6-v2'); S('clip-ViT-B-32')"

# Hosts mount persistent volumes as root (Railway: set DATA_DIR to the mount path).
USER root

WORKDIR /app/backend
EXPOSE 7860
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-7860}"]
