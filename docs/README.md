# Documentazione Intecha Chat

Runtime corrente: [Open WebUI Intecha](OPENWEBUI.md), [ADR 006](adr/006-openwebui-intecha.md) e [migrazione](plans/05-openwebui-migrazione.md).

Le procedure e le ADR precedenti descrivono il legacy conservato per migrazione e ripristino.

Rilevazione del legacy: 30 ottobre 2026. Base ispezionata: `09467b47dca23ad9f0e6e384df6d502880cb74d5`.
L'ispezione riguarda sorgenti, schema e configurazioni versionate; non è un collaudo
live di Coolify, Supabase, Qdrant, Ollama o della qualità delle risposte.

## Documenti principali

| Documento | Contenuto |
| --- | --- |
| [PRODUCT.md](PRODUCT.md) | Perché esiste, utenti, pagine, obiettivi e limiti |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Servizi, dati, flussi, API, deploy e punti aperti |
| [DESIGN.md](DESIGN.md) | Stile realmente presente e regole per estenderlo |
| [ADR](adr/README.md) | Decisioni architetturali ricostruite dal codice |
| [Piani per fase](plans/README.md) | Baseline, misurazione e interventi proposti |
| [AGENTS.md](../AGENTS.md) | Stack, comandi e convenzioni operative |

## Procedure e approfondimenti esistenti

- [Supabase](SUPABASE.md): bootstrap e import legacy. Le sezioni iniziali descrivono
  anche fasi storiche; per stato corrente, quattro migrazioni e Qdrant server usare
  [ARCHITECTURE.md](ARCHITECTURE.md) e [AGENTS.md](../AGENTS.md).
- [Amministrazione e lettore](ADMIN_READER.md): la sezione finale IAM aggiorna i vecchi
  ruoli `manager/user` a `member/viewer`.
- [PDF strutturati](STRUCTURED_PDF.md), [worker](IMPORT_WORKER.md),
  [ricerca ibrida](HYBRID_SEARCH.md), [recupero gerarchico](HIERARCHICAL_RETRIEVAL.md).
- [Listini](STRUCTURED_PRICES.md), [privacy](PRIVACY_PIPELINE.md),
  [ricerca agentica](AGENTIC_RAG.md), [servizio Anonymizer](../services/anonymizer/README.md).
- [Bug import PDF](../bug/BUG-001-docling-timeout-pdf-digitali.md) e
  [misure worker/GPU](../bug/TODO-gpu-worker-docling.md): evidenze storiche del 19 ottobre;
  non descrivono necessariamente lo stato attuale del server.

## Come leggere gli stati

**Implementato** significa presente nel codice. **Da verificare live** richiede
controlli sull'installazione. **Proposto** significa lavoro non ancora realizzato.
Le checkbox dei piani attestano soltanto attività svolte nella relativa fase.
