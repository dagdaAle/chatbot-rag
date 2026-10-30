# 005 — Ricerca ibrida e percorsi distinti per testo e calcoli

Data di ricostruzione: 2026-10-30. Stato: adottata nel codice.

## Contesto

Somiglianza semantica, codici esatti, lettura delle condizioni e aggregazioni numeriche
richiedono operazioni differenti. Un LLM non è una fonte affidabile di conteggi e prezzi.

## Decisione

Fondere retrieval denso e lessicale locale con RRF; diversificare con MMR e ampliare
le sezioni nel percorso standard. Per listini riconosciuti interrogare un indice
tipizzato e calcolare con Decimal. Con DeepSeek usare un agente con strumenti
ammessi e limiti di passi/chiamate/tempo; leggere le sezioni su richiesta del modello.
Altri provider mantengono il percorso standard.

## Alternative e conseguenze

Solo vettori perde segnale sugli identificativi; tutto al LLM rende poco verificabili
le aggregazioni. Un agente con strumenti arbitrari eccederebbe il perimetro attuale.
I percorsi distinti permettono provenienza e controlli, ma il riconoscimento dell'intento
non copre ogni domanda. Le vecchie collezioni richiedono migrazione ibrida. MMR non è
reranking; scale RRF/coseno e scelta di espandere le sezioni restano da valutare.
Nessun benchmark attuale prova la superiorità rispetto a Open WebUI.

## Evidenze e riesame

`core/chat.py`, `core/lexical.py`, `core/hierarchical.py`, `core/price_lists.py`,
`core/agentic.py`. Riesaminare ranking e strumenti dopo la
[baseline di qualità](../plans/01-valutazione-rag.md).
