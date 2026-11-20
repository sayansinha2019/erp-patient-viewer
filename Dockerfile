FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

# Production clinical search (KLARIFY_EMBEDDINGS=local): bake the multilingual ONNX
# embedding model into the image so the app never downloads anything at runtime.
# (~120 MB on disk; unused and not loaded in the vertex demo mode.)
ARG LOCAL_EMBED_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
ARG LOCAL_EMBED_FILE=onnx/model_quint8_avx2.onnx
ENV KLARIFY_LOCAL_EMBED_MODEL=${LOCAL_EMBED_MODEL} \
    KLARIFY_LOCAL_EMBED_FILE=${LOCAL_EMBED_FILE} \
    KLARIFY_LOCAL_MODEL_DIR=/app/models/local-embed
RUN python -c "import os; from huggingface_hub import hf_hub_download as get; \
[get(os.environ['KLARIFY_LOCAL_EMBED_MODEL'], f, local_dir=os.environ['KLARIFY_LOCAL_MODEL_DIR']) \
 for f in (os.environ['KLARIFY_LOCAL_EMBED_FILE'], 'tokenizer.json')]" \
    && rm -rf /app/models/local-embed/.cache
ENV KLARIFY_MODEL_DOWNLOAD=0 \
    HF_HUB_OFFLINE=1

COPY backend/ ./backend/
COPY static/ ./static/
COPY data/ ./data/

# Bundle gematik FHIR sample prescriptions for demo mode
RUN git clone --depth 1 https://github.com/gematik/api-erp.git /tmp/api-erp \
    && mkdir -p /app/data/samples \
    && cp /tmp/api-erp/samples/qes/*.xml /app/data/samples/ \
    && rm -rf /tmp/api-erp

ENV ERP_SAMPLES_DIR=/app/data/samples
ENV KLARIFY_DATA_DIR=/app/.data
ENV KLARIFY_CACHE_DIR=/app/.cache
ENV HOME=/app/.cache/home
ENV PORT=8000

# Writable dirs for non-root runtimes (Hugging Face Spaces runs as uid 1000)
RUN mkdir -p /app/.data /app/.cache/home /app/logs     && chmod -R 777 /app/.data /app/.cache /app/logs
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/health')" || exit 1

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips=*"]
