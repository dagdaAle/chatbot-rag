# Fase 00 — Fotografare il sistema

Stato: documentazione iniziale completata il 30 ottobre 2026; verifica live aperta.
Base: commit `09467b4`. Dipendenze: nessuna modifica applicativa.

## Obiettivo e perimetro

Dare ad agenti e sviluppatori un punto di ingresso unico. Conservare i runbook esistenti,
segnalando le parti storiche; non riscrivere l'applicazione né attestare lo stato live.

## Attività

- [x] Ispezionare stack, router, UI, migrazioni, dati, worker e percorsi RAG.
- [x] Documentare prodotto, architettura e stile realmente presenti.
- [x] Aggiungere AGENTS.md e CLAUDE.md con rimando unico.
- [x] Ricostruire ADR delle scelte implementate, con alternative e conseguenze.
- [x] Separare i piani futuri dalla baseline corrente.
- [ ] Confrontare questo inventario con immagini, schema e configurazione server.

## Evidenze e verifica

[Architettura](../ARCHITECTURE.md), [design](../DESIGN.md), [ADR](../adr/README.md).
Il frontend passa top_k=5, pur avendo l'API default 12; l'agente limita l'iniziale a 6.
Questo è un esempio di parametro da leggere lungo tutto il percorso prima di misurare.
Verifica documentale: link locali, percorsi, ordine SQL e coerenza con i sorgenti.
Nessuna nuova esecuzione delle suite applicative è necessaria per soli file Markdown.

## Completamento e rischi

La parte documentale è completa quando i file sono salvati e i rimandi risolvono.
L'allineamento produzione rimane aperto fino all'inventario della fase 04.
Rischio principale: documentazione che invecchia; aggiornare i documenti insieme al codice.
