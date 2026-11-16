Stato: bozza generata da agente · Aggiornato: 2026-11-16 · Fonte: chatbot-rag@09467b4 (main) + codex/docling-integration@c5e9379

# Decisioni (ADR)

Sintesi delle ADR in `docs/adr/` (branch `codex/docling-integration`). Le 001–005 sono state ricostruite dal codice il 30/10/2026: motivazioni tecniche, non verbali di approvazione. ADR-008 è aggiunta qui dalle note server.

| ADR | Decisione | Stato |
|---|---|---|
| 001 | Persistenza specializzata | Adottata (legacy), superata da 006 |
| 002 | Supabase Auth + permessi in SQL | Adottata (legacy), superata da 006 |
| 003 | Import persistente con worker separato | Adottata (legacy) |
| 004 | Embedding locali + protezione obbligatoria delle chat esterne | Adottata, principio ancora valido |
| 005 | Retrieval ibrido, listini deterministici, agente limitato | Adottata (legacy) |
| 006 | Open WebUI + Privacy Gateway | Adottata il 30/10/2026 |
| 007 | Docling isolato, promozione dopo collaudo | Pilot in preview, promozione bloccata (gate E3) |
| 008 | Archiviazione del chatbot | Eseguita 10–12/11/2026 |

## ADR-001 — Persistenza specializzata

- Contesto: identità e permessi chiedono relazioni; la ricerca chiede vettori; i PDF vanno conservati; i prezzi chiedono calcoli verificabili.
- Decisione: Supabase Postgres (metadati, chat, IAM, coda, consumi), Qdrant (vettori), volume (PDF, JSON, config), SQLite WAL (indice listini derivato).
- Alternative scartate: un solo Postgres con pgvector (richiede migrazione); solo JSON/Markdown (non regge isolamento utenti e query numeriche).
- Conseguenze: backup coordinati, nessuna atomicità fra archivi. SQLite listini ricostruibile.

## ADR-002 — Identità Supabase e permessi in SQL

- Contesto: visibilità coerente fra browser, API e PostgREST; un ruolo nel token può essere revocato dopo l'emissione.
- Decisione: JWT ES256 via JWKS, profilo letto a ogni richiesta, ruoli `admin/member/viewer`, permesso calcolato in SQL + RLS, JWT utente per le operazioni normali.
- Alternative scartate: solo forward-auth Authentik (non dà regole applicative); permessi nel frontend (divergenze).
- Conseguenze: test SQL e migrazioni in ordine. Admin globale: non è un confine fra Comuni diversi.

## ADR-003 — Worker di import separato

- Contesto: Docling/OCR + embedding durano minuti; devono sopravvivere ai riavvii.
- Decisione: lavoro in Postgres, claim atomico con lease, pubblicazione solo a indicizzazione completata, un solo worker.
- Alternative scartate: background task nell'API (si perde al riavvio); Redis/Celery (infrastruttura in più non necessaria).
- Conseguenze: API e worker devono avere stessa revisione, stesso `DATA_DIR` e Qdrant server.

## ADR-004 — Embedding locali e protezione obbligatoria

- Contesto: domande, cronologia e fonti possono contenere dati personali; un agente manda contenuti nuovi a ogni passo.
- Decisione: embedding solo Ollama. Ogni chat esterna passa dall'Anonymizer; errore = chiamata bloccata. Chiave Fernet solo nell'Anonymizer.
- Alternative scartate: invio in chiaro o fallback senza protezione; solo modelli locali (limita le opzioni chat).
- Conseguenze: latenza in più, dipendenza dalla qualità NER. È pseudonimizzazione, non anonimizzazione né conformità.

## ADR-005 — Percorsi distinti per testo e calcoli

- Contesto: somiglianza, codici esatti, sezioni complete e aggregazioni numeriche sono operazioni diverse; un LLM non è affidabile su conteggi e prezzi.
- Decisione: dense + lessicale con RRF, MMR, espansione a sezione; listini su indice tipizzato con `Decimal`; agente DeepSeek con tool ammessi e budget.
- Alternative scartate: solo vettori (perde gli identificativi); tutto al LLM (aggregazioni non verificabili); agente con tool arbitrari.
- Conseguenze: l'encoder lessicale non è BM25 completo, MMR non è un reranker, nessun benchmark di qualità.

## ADR-006 — Open WebUI come base, gateway come confine di uscita

- Contesto: il chatbot custom recuperava pochi frammenti e gestiva male le ricerche senza prove. Rifare tutta la piattaforma costa troppo da mantenere.
- Decisione: Open WebUI 0.12.5 fissato per digest + overlay marchio minimo. Gateway OpenAI-compatible tra WebUI e DeepSeek che protegge ogni chiamata (anche task e tool) e ripristina le risposte. Rebranding con eccezione di licenza ≤50 utenti per 30 giorni, confermata dal proprietario.
- Alternative scartate: riscrivere il RAG custom; fork profondo di Open WebUI; solo filtro PII iniziale (non copre ogni chiamata e il ripristino).
- Conseguenze: DB e indice nuovi, import esplicito, permessi da riconciliare. SSE bufferizzato, solo testo. Listini, quote e audit non migrati. Oltre 50 utenti va rivista la licenza.

## ADR-007 — Docling isolato

- Contesto: sul catalogo si perdeva l'associazione fra modello, intestazione e valore. Il loader Docling nativo non ha timeout HTTP esplicito.
- Decisione proposta: `docling-serve` come servizio locale separato, overlay minimo del loader (timeout, validazione, errori sanitizzati), promozione solo dopo i gate E0–E6.
- Alternative scartate: Docling dentro il container WebUI; connettore nativo senza hardening; adapter + archivio strutturato subito.
- Esito 30/10: preview funzionante, 120/120 associazioni con `pypdfium2`, ma **E3 fallito**: il connettore Markdown non tiene modello e consumo nello stesso chunk. Produzione invariata.

## ADR-008 — Archiviazione

- Contesto: DA VERIFICARE (motivo non scritto nelle fonti). Il 10/11 c'è stata una pulizia generale del server (disco dal 59% al 43%).
- Decisione: 10/11 intecha-chat archiviato con backup; 12/11 legacy e worker eliminati da Coolify, route `chatbot.` tolta dal tunnel.
- Conseguenze: Supabase, Qdrant (senza backup) e Anonymizer restano accesi. Il volume Open WebUI è conservato. Il pilot Docling resta fuori da Coolify. Il codice Open WebUI era solo sul server: copia sul Mac in `~/Progetti/archivio/intecha-chat-20261110/`; il branch `codex/docling-integration` è solo locale.
