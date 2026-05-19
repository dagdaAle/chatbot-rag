FROM python:3.12-slim

WORKDIR /app

# Dipendenze sistema (layer separato per cache)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Dipendenze Python (layer separato - viene ricreato solo se requirements.txt cambia)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Codice applicazione (copiato per ultimo - cambia più spesso)
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
