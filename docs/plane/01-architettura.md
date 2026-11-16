Stato: bozza generata da agente · Aggiornato: 2026-11-16 · Fonte: chatbot-rag@09467b4 (main) + codex/docling-integration@c5e9379

# Architettura

Due runtime nello stesso repo. Il più recente (Open WebUI) è quello in uso dal 30/10 al 10/11/2026. Il legacy resta in `main` per ripristino e per le funzioni non migrate (listini, quote, audit).

## C4 L1 — Contesto

```
 [Dipendente/Admin] --HTTPS--> [Intecha Chat]
                                  |   \
                    embedding     |    \ testo protetto (pseudonimi)
                    locali        v     v
                              [Ollama]  [DeepSeek API]   (cloud, extra SEE)
                                  ^
         dati personali restano sul server; verso il cloud solo testo
         passato dall'Anonymizer
```

## C4 L2 — Container, runtime Open WebUI

```
Browser
   |
   v
Traefik/Coolify proxy (chatbot.intecha.dev, priority 1000)
   |
   v
+----------------------+     rete "private" (internal)     +--------------------+
| webui                |---------------------------------->| privacy-gateway    |
| Open WebUI 0.12.5    |  OpenAI API /v1 (chiave interna)  | FastAPI :8081      |
| :8080 (+127.0.0.1:   |                                   | read-only, no porte|
|  3080 per diagnosi)  |                                   +---------+----------+
+---+--------------+---+                                             |
    |              |                                     /v1/protect | /v1/restore
    | volume       | embedding                                       v
    v              v (rete coolify)                       +--------------------+
 intecha-openwebui-data   Ollama :11434                    | anonymizer :8000   |
 (DB app + Chroma)        nomic-embed-text                 | Presidio + GLiNER  |
                                                           | GPU, vault Fernet  |
                                                           +--------------------+
                          privacy-gateway --solo testo protetto--> api.deepseek.com
```

## C4 L2 — Container, legacy (main)

```
Browser React ---JWT---> FastAPI backend :8000 ----JWT utente----> Supabase PostgREST/Postgres (RLS)
     |                     |  |  |  \
     +--login--> Supabase  |  |  |   +--> Anonymizer --> (testi protetti) --> DeepSeek/OpenAI
                 Auth      |  |  +--> Ollama (embedding, chat locale opzionale)
                           |  +-----> Qdrant server (vettori dense + sparse)
                           +--------> DATA_DIR (PDF, JSON Docling, runtime_config, SQLite listini)

import-worker (stessa immagine, python -m app.worker)
     claim/lease su import_jobs (Postgres) -> Docling/OCR -> embedding Ollama -> Qdrant + DATA_DIR -> pubblica documento
```

## Componenti

| Componente | Runtime | Responsabilità | Sorgente |
|---|---|---|---|
| Open WebUI + overlay | Open WebUI | UI, utenti, permessi, KB, retrieval ibrido BM25+vettori, tool | `Dockerfile`, `deploy/openwebui/brand.py` |
| Privacy Gateway | Open WebUI | Unica uscita verso DeepSeek; protegge e ripristina ogni chiamata (chat, task, tool) | `services/privacy-gateway/gateway/main.py` |
| Anonymizer | entrambi | Pseudonimizzazione reversibile, mappe cifrate con TTL | `services/anonymizer/` |
| Docling preview | pilot | Estrattore isolato `docling-serve` 1.38.2, non promosso (gate E3 fallito) | `deploy/docling/`, `docs/DOCLING-PILOT.md` |
| Backend FastAPI | legacy | Auth, KB, chat, upload, admin, agente | `backend/app/` |
| Import worker | legacy | Coda persistente, Docling, embedding, indicizzazione | `backend/app/worker.py`, `core/import_jobs.py` |
| Frontend React | legacy | Chat, fonti, lettore PDF, KB, admin | `frontend/src/` |

### Anonymizer (componente condiviso)

- FastAPI + Microsoft Presidio + regole italiane (CF, P.IVA, IBAN, targhe, telefoni, email) + GLiNER `urchade/gliner_multi_pii-v1` su GPU (~2,4 GB VRAM al 06/10).
- Sul server: container `anonymizer`, rete `coolify`, nessuna porta né Traefik. Raggiungibile solo come `http://anonymizer:8000`.
- Contratto: `POST /v1/protect` crea una mappa per richiesta, `/v1/protect/extend` aggiunge testi alla stessa mappa, `/v1/restore` ripristina solo i token emessi, `DELETE /mappings/{id}` cancella. Segnaposto `<PII_<uuid>_PERSONA_1>`.
- Limiti: 64 campi, 200.000 caratteri, una inferenza alla volta, 4 richieste in coda, poi 503. Un solo worker Uvicorn.
- Se GLiNER è disattivato `/v1/protect` risponde 503: nessun fallback in chiaro.
- Il repo separato `~/Progetti/server-apps/anonymizer` è la versione iniziale (solo API `/anonymize`, `/deanonymize`). La versione con `/v1/*` usata dal chatbot è in `services/anonymizer/`. Quale delle due giri oggi sul server: DA VERIFICARE.

## Flussi principali

### Domanda (Open WebUI)

1. Open WebUI fa retrieval locale (embedding Ollama, ibrido BM25+vettori, top 12 → 8).
2. Manda la chiamata chat al gateway con la chiave interna.
3. Il gateway crea una mappa, protegge messaggi, cronologia, argomenti tool e schemi (`/v1/protect`, poi `extend` oltre 64 campi).
4. Valida protocollo e segnaposto, chiama DeepSeek senza streaming.
5. Ripristina risposta, reasoning e argomenti tool, cancella la mappa. Restituisce SSE bufferizzato.
6. Ogni chiamata successiva dell'agente ripete la protezione con una mappa nuova.

### Importazione PDF (legacy)

1. API controlla permesso editor/owner e limite 20 MB, salva il PDF pendente, crea `import_jobs`.
2. Il worker prende il lavoro con claim atomico (`SKIP LOCKED`) e rinnova il lease.
3. Docling estrae struttura e tabelle. OCR solo se il PDF non ha testo nativo (commit `98e0e31`).
4. Chunk con provenienza → embedding Ollama + vettori lessicali → Qdrant. JSON e indice listini in `DATA_DIR`.
5. Il documento diventa visibile in chat solo dopo la pubblicazione finale.

### Domanda (legacy), tre percorsi

1. Listino riconosciuto → query su SQLite tipizzato, calcoli `Decimal`, nessun LLM.
2. DeepSeek agentico → ricerca iniziale, poi tool `read_section`, versioni, listini. Max 3 passi, 6 tool call, 120 s.
3. Standard → retrieval ibrido (RRF) → MMR → espansione a sezione/articolo (18.000 car/sezione, 48.000 totali) → LLM.
