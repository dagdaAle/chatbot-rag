# Chatbot RAG - Qdrant + FastAPI + React

Chatbot RAG generico con supporto per documenti PDF.

## Stack

- **Qdrant**: vector database (ricerca semantica)
- **FastAPI**: backend Python
- **React + Vite + TypeScript**: frontend

## Avvio rapido

```bash
docker compose up -d
```

Servizi:
- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API docs**: http://localhost:8000/docs
- **Qdrant dashboard**: http://localhost:6333/dashboard

## Comandi

```bash
# Avvia
docker compose up -d

# Build + avvio (dopo modifiche)
docker compose up -d --build

# Log
docker compose logs -f

# Stop
docker compose down
```

## Struttura

```
├── backend/          # FastAPI
├── frontend/         # React + Vite + TS
├── docker-compose.yml
└── .env.example
```
