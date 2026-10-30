# Intecha Chat

Aggiornamento: 30 ottobre 2026. Base applicativa scelta: Open WebUI; protezione dati
tramite Anonymizer Intecha e gateway interno. [Decisione](adr/006-openwebui-intecha.md).

## Perché esiste

Interrogare documenti e PDF con una chat che sappia cercare di nuovo, leggere i testi
e citare le fonti quando una prima ricerca non basta. La base generalista è Open WebUI;
le integrazioni specifiche Intecha rimangono servizi separati e verificabili.

## Superfici del prodotto

Chat nuova e cronologia, selezione modello, allegati/KB, fonti documentali,
workspace Knowledge, impostazioni personali e pannello amministrativo upstream.
Accesso con i due account migrati e password esistenti; registrazione pubblica chiusa.
Per i flussi dettagliati usare la UI della release fissata, non le vecchie route React.

## Obiettivi e limiti

- Ricerca documentale con strumenti e possibilità di approfondimento; citazioni consultabili.
- Embedding locali e protezione obbligatoria di tutte le chiamate DeepSeek.
- Conservazione di proprietari, condivisione KB, PDF e conversazioni nella migrazione.
- Marchio Intecha per il deployment entro 50 persone/30 giorni confermato dal proprietario.
- Dichiarare prove insufficienti senza inventare informazioni; misurare la qualità reale.

La prima integrazione è testuale. Il testo della risposta appare dopo la generazione
completa e il ripristino. Immagini/audio cloud non sono supportati dal gateway.
Listini deterministici, quote/audit legacy e relative statistiche non diventano
funzioni native per effetto della migrazione; sorgenti e dati precedenti sono conservati.
Non si certificano vigenza, esaustività o assenza di falsi negativi PII.

## Hermes e MCP

Open WebUI supporta integrazioni, ma questa distribuzione non aggiunge ancora un
collegamento Hermes o un server listini MCP. Non c'è sync Obsidian. Il vault
Anonymizer è l'archivio delle mappe cifrate, non il vault delle note.

[Architettura e migrazione](OPENWEBUI.md) · [Piani](plans/README.md).
