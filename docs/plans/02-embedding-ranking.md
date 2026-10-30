# Fase 02 — Embedding e ranking

Stato: proposta. Dipendenza: baseline della fase 01. Nessuna modifica attuata qui.

## Situazione

Encoder comune per query/documenti, senza prefissi applicativi. Modello configurabile,
predefinito Nomic. Dense+sparse IDF e RRF già presenti; MMR combina score di fusione
con penalità coseno. Reranker dedicato assente. Le collezioni legacy restano dense.

## Attività

- [ ] Verificare modello/tag/variante e istruzioni del produttore; controllare se
  Ollama aggiunge prefissi. Valutare query/documento distinti e qualità sull'italiano.
- [ ] Verificare collezioni e provenienza degli indici; migrare solo dove necessario,
  con backup, conteggi e ripristino verificati.
- [ ] Confrontare RRF senza MMR con l'attuale; se si mantiene MMR, rendere coerenti
  le scale del punteggio di pertinenza e della penalità di ridondanza.
- [ ] Confrontare concatenazione cronologia con query autonome riscritte,
  conservando identificativi e costo/latency delle chiamate aggiuntive.
- [ ] Provare un reranker multilingue con pochi assetti controllati di candidati,
  soglia e risultati finali; modello e quantità da scegliere sui dati della fase 01.
- [ ] Rendere osservabili versione indice/encoder, metodo retrieval e configurazione
  attiva, senza esporre prompt o dati personali nei log.

## Verifica e completamento

Ablation: cambiare una componente per volta, sullo stesso dataset. Confrontare
recupero dei passaggi, risposte, citazioni, latenza e memoria. Adottare solo variazioni
con beneficio verificato e regressioni comprese. Registrare la scelta in una nuova ADR.

## Migrazione e ripristino

Cambiare modello o prefissi documento richiede nuovi embedding; non mescolare spazi
vettoriali solo perché hanno dimensione uguale. Usare un indice candidato separato,
validarlo e conservare quello precedente fino al collaudo. L'intervento su MMR/query
può essere confrontato con configurazione precedente senza reimportare i PDF.
