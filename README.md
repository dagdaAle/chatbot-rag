# Chatbot RAG - Qdrant + FastAPI + React

Chatbot RAG avanzato con supporto per documenti PDF, chunking semantico e diversi provider LLM.

## Stack

- **Qdrant**: vector database (ricerca semantica con MMR)
- **FastAPI**: backend Python
- **React + Vite + TypeScript**: frontend

## Caratteristiche

- **Chunking intelligente**: 2000 caratteri con overlap 250, divisione semantica su paragrafi e frasi
- **Ricerca avanzata**: MMR (Maximum Marginal Relevance) per diversità nei risultati
- **Provider multipli**: supporto per OpenAI e Ollama
- **Filtro per score**: filtraggio automatico di chunk poco rilevanti
- **Citazioni precise**: risposte con citazioni verbatim dai documenti

## Provider supportati

### Chat
- **OpenAI**: GPT-4o, GPT-4o-mini, GPT-4-turbo, GPT-3.5-turbo
- **Ollama**: modelli locali compatibili

### Embeddings
- **OpenAI**: text-embedding-3-small, text-embedding-3-large, text-embedding-ada-002
- **Ollama**: nomic-embed-text, mxbai-embed-large, all-minilm

*Nota: chat e embeddings possono usare provider diversi (es. Ollama + OpenAI embeddings)*

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

## Configurazione

Copia `.env.example` in `.env` e configura le chiavi API necessarie:

```bash
cp .env.example .env
```

### Variabili principali

```env
# Provider per chat
LLM_PROVIDER=openai  # openai, ollama

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small


# Ollama (locale)
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

## Struttura

```
├── backend/          # FastAPI
├── frontend/         # React + Vite + TS
├── docker-compose.yml
└── .env.example
```

## Affidabilità e limiti operativi

- Eseguire una sola istanza/worker quando si usano Qdrant embedded e metadati JSON.
- `DATA_DIR` contiene conversazioni, PDF, prompt, metadati e configurazione runtime;
  il volume persistente deve essere montato su quel percorso. Salvare anche Qdrant
  (percorso `QDRANT_LOCAL_PATH` o volume del server) nei backup.
- Il cambio del modello embedding è rifiutato quando esistono vettori: richiede
  una migrazione esplicita. Non vengono più ricreate automaticamente le collezioni.
- Upload PDF: massimo 20 MB per file. L'indicizzazione resta nella richiesta HTTP,
  senza una coda persistente; PDF scansionati richiedono OCR esterno.
- Il retrieval mantiene la soglia di rilevanza e include le ultime due domande;
  non è una riscrittura della query tramite LLM. Cronologia: massimo 12 messaggi
  e 16000 caratteri. Le fonti recuperate non costituiscono una validazione delle
  singole affermazioni generate.

Test backend (virtualenv, dipendenze in `backend/requirements.txt` + pytest/httpx):

```bash
PYTHONPATH=backend python -m pytest backend/tests
```
