Stato: bozza generata da agente · Aggiornato: 2026-11-16 · Fonte: chatbot-rag@09467b4 (main) + codex/docling-integration@c5e9379

# Configurazione

Solo nomi e scopo. I valori stanno nel `.env` sul server (permessi 0600) e nei backup. Segreti: Vaultwarden → DA VERIFICARE la voce (non trovata nelle fonti).

## Runtime Open WebUI

Template: `deploy/openwebui/.env.example`. La configurazione è tutta da ambiente (`ENABLE_PERSISTENT_CONFIG=false`): le modifiche fatte dalla UI non persistono, si cambia il Compose.

| Variabile | Servizio | A cosa serve |
|---|---|---|
| `INTECHA_REBRANDING_CONFIRMED` | build webui | Conferma licenza rebranding (≤50 utenti/30 giorni). Senza, la build fallisce |
| `WEBUI_URL` | webui | URL pubblico |
| `WEBUI_SECRET_KEY` | webui | Segreto sessioni. Va mantenuto per riusare il volume |
| `INTECHA_NETWORK` | compose | Rete Docker esterna (default `coolify`) |
| `INTECHA_PREVIEW_PORT` | webui | Porta su 127.0.0.1 per diagnosi (default 3080) |
| `GATEWAY_API_KEY` | webui + gateway | Chiave interna webui → gateway |
| `DEEPSEEK_API_KEY` | solo gateway | Chiave provider. Mai in webui |
| `DEEPSEEK_CHAT_MODEL` | webui + gateway | Modello (default `deepseek-flash`) |
| `ANONYMIZER_URL`, `ANONYMIZER_TOKEN` | gateway | Endpoint e token Anonymizer |
| `OLLAMA_BASE_URL` | webui | Ollama per gli embedding (default `http://ollama:11434`) |
| `OPENWEBUI_IMAGE` | build | Immagine upstream fissata per digest |
| `INTECHA_HARDEN_DOCLING` | build | `1` = overlay loader Docling (solo candidato preview). Default `0` |

Valori fissati nel `docker-compose.yml`: signup chiuso, ruolo default `pending`, Ollama chat e connessioni dirette disattivate, web search/immagini/community/export admin disattivati, embedding `nomic-embed-text` con prefissi `search_query:` / `search_document:`, ricerca ibrida, `RAG_TOP_K=12`, `RAG_TOP_K_RERANKER=8`, chunk 1200/150, `VECTOR_DB=chroma`, telemetria disattivata.

## Anonymizer

| Variabile | A cosa serve |
|---|---|
| `ANONYMIZER_KEY` | Chiave Fernet del vault. Solo qui. Se si perde, i pseudonimi persistenti non si invertono più |
| `ANONYMIZER_TOKEN` | Token condiviso con gateway/backend |
| `GLINER_MODEL`, `GLINER_THRESHOLD` | Modello NER e soglia (default 0,5) |
| `SPACY_MODEL` | Modello spaCy (default `it_core_news_sm`) |
| `DEVICE` | `auto` / `cuda` / `cpu` |
| `DISABLE_GLINER` | `1` disattiva GLiNER (allora `/v1/protect` dà 503) |
| `MAPPING_TTL_SECONDS` | TTL mappe temporanee (300–3600, default 900) |
| `DATA_DIR` | Directory del vault (default `/data`) |

## Legacy (main)

Template: `.env.example`. Se esiste `DATA_DIR/runtime_config.json`, prevale sulle variabili per provider e modelli.

| Gruppo | Variabili | Note |
|---|---|---|
| Qdrant | `QDRANT_HOST`, `QDRANT_PORT`, `QDRANT_LOCAL_PATH` | `QDRANT_LOCAL_PATH` (embedded) è incompatibile con il worker |
| Dati | `DATA_DIR` | Volume persistente: PDF, JSON, config, SQLite listini |
| PDF | `PDF_EXTRACTOR` (`docling`/`pypdf`), `PDF_MAX_PAGES`, `PDF_CONVERSION_TIMEOUT`, `PDF_DEVICE` (`cpu`/`cuda`), `PDF_CPU_THREADS`, `DOCLING_ARTIFACTS_PATH` | Solo worker |
| Worker | `IMPORT_WORKER_POLL_SECONDS`, `IMPORT_WORKER_LEASE_SECONDS` | |
| Retrieval | `RETRIEVAL_SECTION_MAX_CHARS`, `RETRIEVAL_TOTAL_MAX_CHARS`, `RETRIEVAL_NEIGHBOR_CHUNKS` | Budget in caratteri, non token |
| LLM | `LLM_PROVIDER` (`deepseek`/`openai`/`ollama`), `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_CHAT_MODEL`, `OPENAI_API_KEY`, `OPENAI_EMBEDDING_API_KEY` | |
| Agente | `AGENTIC_RAG_ENABLED`, `AGENTIC_MAX_STEPS`, `AGENTIC_MAX_TOOL_CALLS`, `AGENTIC_TIMEOUT_SECONDS`, `AGENTIC_MAX_OUTPUT_TOKENS`, `AGENTIC_MAX_INPUT_BYTES`, `AGENTIC_REASONING_EFFORT` | |
| Embedding | `EMBEDDING_PROVIDER`, `OLLAMA_BASE_URL`, `OLLAMA_CHAT_MODEL`, `OLLAMA_EMBEDDING_MODEL` | Cambio embedding bloccato se ci sono vettori |
| Supabase | `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_JWT_ISSUER`, `SUPABASE_ADMIN_KEY` | `SUPABASE_ADMIN_KEY` solo server (admin API e worker) |
| Anonymizer | `ANONYMIZER_URL`, `ANONYMIZER_TOKEN`, `ANONYMIZER_CONNECT_TIMEOUT`, `ANONYMIZER_READ_TIMEOUT`, `ANONYMIZER_MAX_CHARS` | Obbligatori per la chat esterna |
| Frontend | `CORS_ORIGINS`, `VITE_API_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY` | Solo valori pubblici |

## Servizi esterni e dipendenze

| Servizio | Uso | Dove |
|---|---|---|
| DeepSeek API | Chat (`deepseek-flash`) | Cloud, solo tramite gateway/Anonymizer |
| Ollama | Embedding `nomic-embed-text` (e chat locale nel legacy) | Container `ollama` sul server; in origine Mac mini in LAN |
| Supabase self-hosted | Auth + Postgres legacy | `supabase.intecha.dev` |
| Qdrant | Vettori legacy | Server |
| Open WebUI | Base applicativa | `ghcr.io/open-webui/open-webui:v0.12.5` fissata per digest |
| Docling / docling-serve | Estrazione PDF | Libreria nel worker legacy; servizio 1.38.2 nella preview |
