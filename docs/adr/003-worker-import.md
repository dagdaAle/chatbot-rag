# 003 — Importazioni persistenti e worker separato

Data di ricostruzione: 2026-10-30. Stato: adottata nel codice.

## Contesto

Docling/OCR ed embedding possono durare minuti. Un lavoro legato alla sola richiesta
HTTP non è sufficiente per sopravvivere a riavvii e rendere visibile l'avanzamento.

## Decisione

Salvare PDF pendente e lavoro Postgres; un processo worker acquisisce un lease con
claim atomico, rinnova il possesso e pubblica il documento solo dopo l'indicizzazione.
Usare cleanup/retry e ID stabili; filtrare la chat sugli ID pubblicati. API e worker
condividono revisione e DATA_DIR e usano Qdrant server.

## Alternative e conseguenze

Background task nell'API non offre lo stesso recupero dopo riavvio. Redis/Celery
aggiungerebbero infrastruttura oggi non necessaria alla coda implementata. Il worker
separato rende gli import recuperabili ma richiede volumi coerenti, configurazione,
monitoraggio e ripristino testato. Qdrant embedded è incompatibile con API e worker
che aprono la stessa directory. Un singolo worker è la configurazione operativa
prevista; non aumentare le repliche senza rivalutare SQLite e concorrenza.

## Evidenze e riesame

`backend/app/worker.py`, `core/import_jobs.py`, `202610130001_import_jobs.sql`.
Riesaminare dopo misure di backlog e tempi reali. [Procedura worker](../IMPORT_WORKER.md).
