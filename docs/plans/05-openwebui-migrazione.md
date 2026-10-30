# Fase 05 — Sostituzione con Open WebUI Intecha

Data: 30 ottobre 2026. Decisione: [ADR 006](../adr/006-openwebui-intecha.md).
Stato: completata. Dominio attivo il 30 ottobre 2026 alle 11:44 (Europe/Rome).

- [x] Autorizzazione del proprietario per installazione entro 50 utenti/30 giorni.
- [x] Immagine Open WebUI fissata per release/digest e overlay Intecha con licenza conservata.
- [x] Gateway autenticato, protezione obbligatoria, tool/cronologia e SSE bufferizzato.
- [x] 33 test di isolamento/protocollo/blocco su errore del gateway.
- [x] Test DeepSeek reali con dati esclusivamente sintetici e ripristino nome/email.
- [x] Nuova istanza privata avviata, separata dai dati legacy.
- [x] Backup/esportazione privata di dati e hash login senza password in chiaro.
- [x] Importati 2 account, 2 KB, 4 PDF, 14 chat e 40 messaggi.
- [x] Verificati hash password/PDF, proprietari, contenuti chat e condivisione KB.
- [x] Verificata ricerca locale su entrambe le KB senza chiamate LLM esterne.
- [x] Test RAG completo su istanza isolata e documento fittizio INTECHA-42: risposta
  corretta, citazione e nessun segnaposto esposto.
- [x] Backup finale coerente e verifica che i dati legacy non siano cambiati.
- [x] Attivazione dominio e stop API/worker legacy conservando volumi e immagini.
- [x] Verifica HTTPS pubblico, accesso e interfaccia italiana/Intecha.

## Esclusioni e seguito

Il test con estratti dei PDF reali verso DeepSeek è stato bloccato dalla revisione
automatica delle autorizzazioni; consenso specifico richiesto al proprietario.
I test sintetici e le verifiche locali sono indipendenti da quel consenso.
Nessuna prova comparativa di qualità con il vecchio chatbot è stata ancora completata.

Listini deterministici e quote/consumi/audit storici rimangono conservati nel legacy;
non sono funzioni native del nuovo runtime. Non eliminare i vecchi archivi finché
il passaggio non è accettato e il ripristino non è verificato.

## Esito operativo

`https://chatbot.intecha.dev` restituisce Intecha v0.12.5, lingua `it-IT`.
WebUI e gateway risultano healthy; API e worker legacy risultano exited.
Schermata pubblica verificata nel browser: «Accedi a Intecha».
Backup coerente: `/home/mulo/intecha-chat/backups/20261030T104300Z`,
archivi legacy e WebUI verificati con lettura tar completa e SHA-256 registrati in
`checksums.json`. Il manifest del passaggio è `migration/cutover.json` sul server.

Gli account mantengono le password precedenti, ma richiedono un nuovo login.
I servizi sono gestiti dal Compose in `/home/mulo/intecha-chat` sulla rete Coolify;
la nuova applicazione non è ancora registrata come risorsa nel pannello Coolify.

### Correzione saluto con strumenti builtin (30 ottobre 2026)

Il collaudo RAG con KB allegata non copriva il saluto con tutti i builtin predefiniti.
Il riconoscitore reale classifica `ask_user` come dato personale: il gateway fermava
la richiesta prima di DeepSeek. Eccezione limitata alla costante pubblica nel campo
nome-funzione, con test di regressione su cronologia/tool choice e protezione ancora
attiva su contenuti, argomenti e chiavi JSON. Il collaudo isolato include ora anche
un saluto senza documenti prima della prova RAG sintetica.

Verifica eseguita: 35 test gateway superati; gateway aggiornato sul server senza
riavviare WebUI. Istanza temporanea senza volumi utente: saluto con builtin
predefiniti riuscito e RAG su documento interamente sintetico riuscito (HTTP 200,
risposta attesa, citazioni, nessun errore o segnaposto). Entrambi i servizi healthy.
Nessuna chat o documento reale usato nel collaudo.
