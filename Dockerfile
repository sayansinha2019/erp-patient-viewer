FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

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
ENV PORT=8000
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/health')" || exit 1

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips=*"]
