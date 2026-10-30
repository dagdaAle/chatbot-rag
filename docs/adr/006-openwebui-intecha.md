# 006 — Open WebUI come base, Anonymizer come confine di uscita

Data: 2026-10-30. Stato: adottata su richiesta del proprietario; passaggio operativo
tracciato nella [fase 05](../plans/05-openwebui-migrazione.md).

## Contesto

Il chatbot custom recuperava pochi frammenti e gestiva male ricerche senza prove.
Riprodurre l'intera piattaforma Open WebUI richiederebbe mantenere UI, strumenti,
modelli, retrieval e recupero dagli errori. Intecha possiede già un Anonymizer separato.

## Decisione

Usare la release ufficiale fissata per digest e un overlay minimo per il marchio
Intecha, senza copiare manualmente il RAG upstream nel backend precedente. Inserire
un gateway OpenAI-compatible tra WebUI e DeepSeek: proteggere ogni chiamata, compresi
strumenti e task, e ripristinare le risposte prima del ritorno a WebUI.

Il proprietario ha confermato il limite <=50 persone in ogni finestra mobile di 30
giorni, usato per l'eccezione di rebranding. Conservare licenza e notice upstream.

## Alternative

- Riscrivere il RAG custom: maggior controllo, ma mantiene il costo dell'intera piattaforma.
- Fork profondo Open WebUI: consente modifiche ampie ma complica aggiornamenti e sicurezza.
- Solo filtro iniziale PII: non offre da solo il controllo dell'uscita su ogni nuova
  chiamata/tool e sul ripristino delle risposte; il gateway centralizza il contratto.

## Conseguenze

Nuovo database/indice separato, import esplicito di account/chat/PDF, riconciliazione
permessi. Conservazione del legacy per ripristino. La prima versione bufferizza SSE,
supporta solo testo e non collega automaticamente listini, quote e audit custom.
Il gateway limita la superficie cloud ma non sostituisce un firewall e non elimina
falsi negativi PII. Nessuna superiorità quantitativa RAG dichiarata senza benchmark.

## Riesame

Prima di ampliare utenti, provider/API, multimodalità o modifica upstream, riesaminare
licenza, privacy, migrazioni, equivalenza IAM e test. Il motore listini potrà essere
riesposto come servizio/tool dedicato. [Dettagli](../OPENWEBUI.md).
