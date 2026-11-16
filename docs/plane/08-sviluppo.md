Stato: bozza generata da agente · Aggiornato: 2026-11-16 · Fonte: chatbot-rag@09467b4 (main) + codex/docling-integration@c5e9379

# Sviluppo locale

## Runtime Open WebUI (branch `codex/docling-integration`)

```sh
cp deploy/openwebui/.env.example .env   # riempire i segreti, mai in Git
docker compose config --quiet           # mai stampare la config senza --quiet: contiene segreti
docker compose up -d --build            # webui su 127.0.0.1:3080
docker compose ps
```

Richiede la rete esterna `coolify` (o `INTECHA_NETWORK`) con `anonymizer` e `ollama` raggiungibili.

Test del gateway:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r services/privacy-gateway/requirements.txt pytest
PYTHONPATH=services/privacy-gateway .venv/bin/python -m pytest services/privacy-gateway/tests -q
```

37 test al 30/10, con Anonymizer e provider simulati. Test Docling: `tests/unit/`, `tests/integration/docling/` (molti richiedono servizi reali e vengono saltati). Benchmark RAG: `tests/evaluation/rag_benchmark.py`.

## Legacy (main)

```sh
cp .env.example .env
docker compose up -d           # anonymizer, qdrant, backend, import-worker, frontend
docker compose up -d --build   # dopo modifiche
docker compose logs -f
```

| Servizio | URL locale |
|---|---|
| Frontend Vite | http://localhost:5173 |
| API | http://localhost:8000, OpenAPI su `/docs` |
| Qdrant | http://localhost:6333/dashboard |

Supabase e Ollama sono esterni al compose. Worker GPU: `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d import-worker`.

Test:

```sh
PYTHONPATH=backend python -m pytest backend/tests          # backend, in venv
cd supabase/tests && npm ci && npm test                    # RLS/IAM/admin su PGlite, senza Supabase
```

Anonymizer:

```sh
cd services/anonymizer
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m spacy download it_core_news_sm
.venv/bin/python -m pytest tests
```

## Convenzioni del repo

- Risposte e documentazione in italiano. Prima l'analisi, poi l'implementazione.
- Branch per feature (`feat/`, `fix/`, `codex/`) + PR, mai commit su `main`. Commit stile conventional (`feat(pdf): ...`, `fix(iam): ...`).
- Python solo in venv, mai `pip` globale.
- Ogni chiamata cloud passa dal gateway/Anonymizer: nessun fallback in chiaro. Mai loggare prompt, risposte, mappe o segreti.
- `backend/`, `frontend/`, `supabase/` sono legacy: non modificarli come se fossero il runtime nuovo.
- Le migrazioni `supabase/migrations` non vanno applicate all'archivio Open WebUI.
- Vecchi dati e volumi si conservano fino a verifica e backup; mai cancellarli durante un deploy.
- Non dichiarare test live o deploy non eseguiti.
