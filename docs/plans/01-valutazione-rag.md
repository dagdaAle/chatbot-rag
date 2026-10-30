# Fase 01 — Baseline di qualità e confronto Open WebUI

Stato: da avviare. Dipendenza: fase 00. Nessuna prova comparativa svolta finora.

## Obiettivo

Capire dove si perde informazione: estrazione, ricerca, ranking, contesto o generazione.
Confrontare implementazioni e configurazioni sui medesimi documenti e domande.

## Attività

- [ ] Preparare 20–30 domande reali: concetti, codici, requisiti/eccezioni, follow-up,
  tabelle, confronto fra versioni, elenco completo e domanda senza risposta.
- [ ] Annotare PDF/versione/hash, pagine/passaggi attesi, risposta e criteri di valutazione.
- [ ] Registrare modello embedding esatto, prefissi, provider/modello chat, prompt,
  top_k effettivo, soglia, RAG agentico, budget, indici e versione dell'estrattore.
- [ ] Eseguire baseline chatbot e Open WebUI, distinguendo RAG, documento completo e
  strumenti agentici. Registrare reranker/ibrido effettivamente attivi su Open WebUI.
- [ ] Confrontare separatamente qualità complessiva e componenti: i diversi prompt,
  la protezione Anonymizer e i contesti possono influenzare il risultato.
- [ ] Classificare gli errori e scegliere gli interventi della fase 02.

## Misure e verifica

Passaggio atteso presente nei candidati e nel contesto finale; correttezza della
risposta e supporto delle citazioni; copertura degli elenchi; correttezza numerica;
nessuna risposta inventata senza prove. Misurare latenza per fase, chiamate/token/costo
e ripetere le prove generative. Non usare uno score vettoriale come misura di qualità.
Conservare artefatti di prova con accesso adeguato, senza PII nei log o fixture pubbliche.

## Completamento

Dataset annotato, configurazioni riproducibili, risultati per domanda e cause dei
fallimenti. Concordare soglie di accettazione dopo la baseline. Nessuna migrazione
necessaria in questa fase; usare copie/isole di test per evitare effetti sulla produzione.
