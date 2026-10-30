# 004 — Embedding locali e protezione delle chat esterne

Data di ricostruzione: 2026-10-30. Stato: adottata nel codice.

## Contesto

Domande, cronologia, fonti e nomi possono contenere dati personali. Un agente invia
contenuti nuovi anche nei passaggi successivi alla prima chiamata.

## Decisione

Embedding obbligatoriamente locali via Ollama. Per chat esterne proteggere messaggi
con Anonymizer prima dell'SDK; estendere la stessa mappa temporanea nei passaggi
agentici; ripristinare la sola risposta autorizzata e cancellare la mappa. La chiave
Fernet rimane nel servizio Anonymizer. In caso di errore bloccare la chiamata esterna.
Chat locale e risposte deterministiche dei listini mantengono percorsi dedicati.

## Alternative e conseguenze

Invio in chiaro o ripiego automatico senza protezione violerebbero il contratto attuale.
Solo modelli locali ridurrebbero l'uscita dei dati ma limiterebbero le opzioni chat.
La scelta richiede servizio/versione/chiavi coordinati, aggiunge latenza e dipende
anche dalla qualità del riconoscimento. È pseudonimizzazione con possibili falsi
negativi, non una prova di anonimizzazione totale o conformità normativa.

## Evidenze e riesame

`core/privacy.py`, `core/agentic.py`, `services/anonymizer/`.
Calibrare sui documenti italiani e verificare che codici prodotto e riferimenti utili
non vengano alterati inutilmente. [Contratto privacy](../PRIVACY_PIPELINE.md).
