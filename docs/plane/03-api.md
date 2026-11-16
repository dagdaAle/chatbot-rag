Stato: bozza generata da agente · Aggiornato: 2026-11-16 · Fonte: chatbot-rag@09467b4 (main) + codex/docling-integration@c5e9379

# API e tool MCP

## Tool MCP

Nessuno. Il chatbot non è esposto nel gateway MCP intecha e non ha integrazione Hermes. Nessuna sync con Obsidian.

## Privacy Gateway (runtime Open WebUI)

Interno, porta 8081, nessuna porta host. Auth: `Authorization: Bearer <GATEWAY_API_KEY>` (chiave interna, distinta da quella DeepSeek).

| Metodo | Path | Cosa fa |
|---|---|---|
| GET | `/health` | Liveness. Non prova che DeepSeek o i riconoscitori siano disponibili |
| GET | `/v1/models` | Solo i modelli in `GATEWAY_MODELS` |
| POST | `/v1/chat/completions` | Protegge → DeepSeek → ripristina. `stream=true` supportato come SSE bufferizzato |

Rifiuta: parametri sconosciuti, endpoint Responses, embedding remoti, audio, immagini, URL multimodali, header `user`, redirect. Limiti: 180.000 caratteri originali, 200.000 protetti, payload 1,5 MB. Contratto completo: `services/privacy-gateway/README.md`.

## Anonymizer

Interno, `http://anonymizer:8000`. Auth: header `X-Anonymizer-Token`.

| Metodo | Path | Uso |
|---|---|---|
| GET | `/health` | Liveness |
| GET | `/entities` | Entità riconosciute |
| POST | `/v1/protect` | `{mapping_id, texts[]}` → testi protetti, `tokens`, `recognizers_complete=true` |
| POST | `/v1/protect/extend` | Nuovi testi nella stessa mappa (non prolunga il TTL) |
| POST | `/v1/restore` | `{mapping_id, text, allowed_tokens}` → testo ripristinato |
| DELETE | `/mappings/{id}` | Cancella la mappa |
| POST | `/anonymize`, `/anonymize/batch`, `/deanonymize` | API legacy, mappe persistenti |

## Open WebUI

API upstream della release 0.12.5, non modificate. Riferimento: documentazione Open WebUI v0.12.5.

## Backend legacy (main)

OpenAPI su `/docs` dell'istanza FastAPI. Auth: JWT Supabase ES256 verificato con JWKS; profilo e permessi letti a ogni richiesta. Tutto tranne `/health` richiede utente autenticato.

| Prefisso | Endpoint principali | Permesso |
|---|---|---|
| `/health` | `GET /health` pubblico, `GET /health/qdrant` | utente |
| `/api/knowledge` | `GET/POST /`, `GET/PUT/DELETE /{id}`, `GET/PUT /{id}/access` | creator / owner |
| `/api/knowledge/{id}/documents` | `POST /upload`, `GET /`, `GET /{doc}/file`, `DELETE /{doc}` | editor per scrivere |
| `/api/knowledge/{id}/imports/{job}/retry` | Riprova un import fallito | editor |
| `/api/directory` | Directory utenti per condividere KB | utente |
| `/api/chat` | `POST` domanda → risposta, fonti, metadati ricerca | accesso KB + modello + quota |
| `/api/conversations` | Lista, crea, dettaglio, elimina, `POST /{id}/messages` | proprietario |
| `/api/settings/models` | `GET /config`, `/chat`, `/embedding`; `PUT /chat`, `/embedding` | admin per scrivere |
| `/api/settings/prompt` | `GET`, `PUT`, `POST /reset`, `GET /default` | admin per scrivere |
| `/api/account` | Profilo, password, consumi personali | utente |
| `/api/admin` | Utenti (crea, modifica, email, password, revoca sessioni), KB, modelli, audit, usage | admin |

La cronologia della chat è caricata dal server: quella inviata dal browser è ignorata.
