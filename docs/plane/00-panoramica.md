Stato: bozza generata da agente · Aggiornato: 2026-11-16 · Fonte: chatbot-rag@09467b4 (main) + codex/docling-integration@c5e9379

# Chatbot RAG (Intecha Chat) — Panoramica

## Scopo

Chat che risponde su documenti PDF citando le fonti. Casi d'uso reali: atti dei Comuni (delibere, regolamenti, allegati, versioni) e listini prodotto (codici, prezzi, confronti fra versioni). Requisito trasversale: i dati personali non escono in chiaro verso il modello cloud (DeepSeek). Gli embedding restano locali (Ollama).

## Per chi

Dipendenti di un Comune, anche su pratiche interne con dati personali (scenario scelto il 13/10/2026). Oggi in uso solo da 2 account amministratori. Il servizio **non è pronto per essere proposto come conforme GDPR/PA**: mancano contratti, DPIA, isolamento per ente, retention. Vedi vault `server/Chatbot RAG - GDPR e servizio ai Comuni.md`.

## Stato: archiviata (novembre 2026)

| Data | Evento |
|---|---|
| 06/10/2026 | Anonymizer (Presidio + GLiNER su GPU) attivo sul server |
| 13/10–19/10 | Legacy custom (FastAPI + React + Supabase + Qdrant) con worker Docling, ricerca ibrida, listini, agente DeepSeek |
| 30/10/2026 | Sostituito da **Open WebUI v0.12.5** + Privacy Gateway (ADR-006). Dominio `chatbot.intecha.dev` attivo |
| 10/11/2026 | intecha-chat (Open WebUI + gateway) **archiviato**: backup in `~/backups/intecha-chat-20261110/` sul server, volume `intecha-openwebui-data` ancora presente |
| 12/11/2026 | Legacy `chatbot-rag` e `rag-import-worker` eliminati da Coolify (backup `~/backups/chatbot-rag-20261112/`), route `chatbot.` tolta dal tunnel |

Restano in piedi sul server: Supabase, Qdrant, Anonymizer, `intecha-docling-preview` (fuori da Coolify). Motivo dell'archiviazione: DA VERIFICARE (non scritto nelle fonti).

## Riferimenti

| Cosa | Dove |
|---|---|
| URL | `https://chatbot.intecha.dev` (non più instradato) |
| Repo | `github.com/dagdaAle/chatbot-rag` · locale `~/Progetti/server-apps/chatbot-rag` |
| Branch runtime Open WebUI | `codex/openwebui-intecha` (su GitHub, fino a `2921808`) · `codex/docling-integration` (solo locale, +2 commit pilot Docling) |
| Branch legacy | `main` (`09467b4`) |
| Anonymizer | `services/anonymizer/` nel repo (versione usata). `~/Progetti/server-apps/anonymizer` è la prima versione (1 commit), superata |
| Doc nel repo | `docs/` (su branch Open WebUI: `ARCHITECTURE.md`, `OPENWEBUI.md`, `adr/`, `plans/`) |

## Stack

| Runtime | Componenti |
|---|---|
| Open WebUI (30/10–10/11) | Open WebUI 0.12.5 (immagine fissata per digest + overlay marchio), Privacy Gateway FastAPI + httpx, Anonymizer, Ollama `nomic-embed-text`, Chroma, DeepSeek `deepseek-flash` |
| Legacy (fino al 30/10) | FastAPI Python 3.12, React + Vite + TS + shadcn/ui, Supabase (Auth + Postgres/PostgREST + RLS), Qdrant server, Docling + Tesseract, SQLite listini, worker import |

## Pagine

01 · Architettura · 02 · Modello dati · 03 · API e tool MCP · 04 · Configurazione · 05 · Deploy e operations · 06 · Runbook · 07 · Decisioni (ADR) · 08 · Sviluppo locale
