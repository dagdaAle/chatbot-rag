# 001 — Persistenza specializzata

Data di ricostruzione: 2026-10-30. Stato: adottata nel codice.

## Contesto

Identità, conversazioni e condivisione richiedono relazioni e autorizzazioni;
la ricerca necessita di vettori; i PDF originali devono restare consultabili.
Le tabelle prezzo devono supportare calcoli verificabili.

## Decisione

Supabase Postgres per metadati/chat/IAM/coda/consumi; Qdrant per vettori e payload
chunk; volume persistente per PDF/JSON/configurazione; SQLite WAL come indice
listini derivato. Le note Markdown documentano il progetto, non sono il database
applicativo. La struttura estratta completa è salvata in JSON, non modellata oggi
come gerarchia relazionale in Postgres.

## Alternative e conseguenze

Un unico Postgres con ricerca vettoriale ridurrebbe il numero di archivi ma richiede
una migrazione; non è l'implementazione attuale. Usare soli JSON/Markdown non copre
bene isolamento utenti e interrogazioni numeriche. La scelta corrente riusa i
componenti esistenti, ma richiede backup coordinati e gestione dei fallimenti fra
archivi: non c'è atomicità distribuita. SQLite prezzi è ricostruibile, PDF e dati
applicativi richiedono conservazione.

## Evidenze e riesame

`core/price_lists.py`, `core/documents.py`, `core/qdrant_client.py`, migrazioni SQL.
Riesaminare SQLite e volumi condivisi prima di introdurre più worker o repliche API.
Vedi [architettura](../ARCHITECTURE.md).
