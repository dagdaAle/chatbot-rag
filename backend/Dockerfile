FROM python:3.12-slim

WORKDIR /app

# Dipendenze sistema (layer separato per cache)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libglib2.0-0 \
    tesseract-ocr tesseract-ocr-eng tesseract-ocr-ita \
    && rm -rf /var/lib/apt/lists/*

# Dipendenze Python (layer separato - viene ricreato solo se requirements.txt cambia)
COPY requirements.txt .
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt
ENV DOCLING_ARTIFACTS_PATH=/opt/docling-models HF_HUB_DISABLE_TELEMETRY=1
COPY scripts/download_pdf_models.py /tmp/download_pdf_models.py
RUN python /tmp/download_pdf_models.py
ENV HF_HUB_OFFLINE=1

# Codice applicazione (copiato per ultimo - cambia più spesso)
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
