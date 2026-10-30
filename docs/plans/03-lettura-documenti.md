# Fase 03 — Lettura e copertura dei documenti

Stato: proposta. Dipendenze: risultati fase 01, ranking validato fase 02.

## Situazione

Il percorso standard amplia sezioni e vicini. Quello agentico parte da frammenti e
richiede una tool call per leggere una sezione. Mancano strumenti generali di ricerca
esatta su tutto il testo e lettura per intervalli. Nessuna modalità documento completo
selezionabile è documentata come implementata.

## Attività

- [ ] Confrontare espansione automatica dei primi risultati agentici con read_section
  facoltativo, usando domande su requisiti/eccezioni e budget equivalenti.
- [ ] Disegnare ricerca testuale e lettura per intervalli su testo estratto, con
  limiti, paginazione, provenienza e controlli di pubblicazione/accesso a ogni uso.
- [ ] Valutare documento completo per PDF brevi selezionati; scegliere il budget in
  token rispetto al modello, mantenendo traccia di eventuali omissioni.
- [ ] Distinguere domanda puntuale, riassunto, elenco esaustivo e confronto: evitare
  di presentare pochi risultati top-k come lettura completa dell'archivio.
- [ ] Preservare pagine, righe/tabelle e riferimenti stabili nelle nuove fonti.
- [ ] Verificare protezione Anonymizer anche sui nuovi contenuti letti e sui follow-up.

## Verifica e completamento

Usare la baseline e casi con eccezioni distanti, tabelle multipagina e versioni.
Provare anche accesso negato, revoca durante la ricerca, import non pubblicato,
contenuto mancante e limite di contesto. Dimostrare copertura maggiore senza
regressioni di isolamento, citazioni o latenza fuori dal limite concordato.

## Dipendenze e ripristino

Riutilizzare JSON strutturati/PDF esistenti; individuare quelli legacy che richiedono
reimport prima di promettere ricerca completa. Ogni nuovo percorso deve poter essere
disabilitato mantenendo quello attuale. Non introdurre MCP/Hermes o sync Obsidian
come effetto collaterale: richiederebbero una decisione di prodotto separata.
