# Anonymizer interno

Presidio + regole italiane + GLiNER multilingua, eseguito sulla GPU del server.
Nessuna porta pubblicata. Chiave Fernet e token obbligatori; non commetterli.
Il chatbot riceve solo il token, mai ANONYMIZER_KEY.

## Contratto della chat

`POST /v1/protect` con header `X-Anonymizer-Token` e JSON
`{"mapping_id":"UUID-generato-dal-backend","texts":["domanda","cronologia","fonti"]}`.
Risposta: `protocol_version=1`, stessa mappa, `recognizers_complete=true`, testi
protetti nello stesso ordine, elenco dei `tokens` emessi. Tutti i riconoscitori
sono obbligatori per questo endpoint; GLiNER disabilitato => HTTP 503.

`POST /v1/protect/extend` accetta lo stesso schema e protegge nuovi batch nella
mappa temporanea già creata. Conserva i segnaposto, riconosce nuove entità e
propaga i valori già noti. Richiede autenticazione e riconoscitori completi;
mappe mancanti, scadute o persistenti restituiscono 404, token estranei 422.
L'estensione non prolunga il TTL. Un errore di elaborazione elimina la mappa.

Una mappa è creata una sola volta per richiesta. Gli pseudonimi hanno forma
`<PII_UUIDsenzaTrattini_PERSONA_1>`. Prima si analizzano tutti i campi, poi si
sostituiscono anche le altre occorrenze esatte dei valori trovati. Non si inferisce
che un cognome abbreviato identifichi la stessa persona di un nome completo.

`POST /v1/restore` riceve `mapping_id`, `text`, `allowed_tokens` (quelli emessi).
Ripristina esclusivamente segnaposto esatti della mappa; riferimenti estranei
sono rifiutati. `DELETE /mappings/{id}` cancella i valori cifrati al termine.
Mappe temporanee orfane scadono dopo `MAPPING_TTL_SECONDS=900` (300–3600), con
pulizia ogni minuto e all'avvio. Le mappe persistenti preesistenti non scadono.

Limiti: 64 campi, 200.000 caratteri totali e per campo, una inferenza simultanea,
quattro richieste ammesse inclusa quella attiva; ulteriori richieste => 503.
Il server applica GLINER_THRESHOLD anche alla nuova API, senza override client.
Finestre GLiNER sovrapposte limitate con i tokenizzatori del modello.
Avviare un solo worker Uvicorn: la coda è interna al processo.

Restano disponibili le API legacy `/anonymize`, `/anonymize/batch` e
`/deanonymize`; il ripristino ora richiede sempre le parentesi dei segnaposto.
La migrazione SQLite aggiunge solo `expires_at`; preserva mappature e cifratura.

## Esecuzione e verifica

`docker-compose.server.yml` documenta rete interna e assegnazione NVIDIA.
Su Coolify conservare volume `/data`, chiave e token esistenti; aggiornare
l'immagine senza cambiare credenziali o volume. Prima fare un backup consistente
SQLite e conservare l'immagine precedente. Il vault cifrato deve avere permessi
ristretti e deve essere incluso nei backup con la chiave custodita separatamente.

Test CPU (venv dedicato o container): installare `requirements-dev.txt` e il
modello spaCy `it_core_news_sm`, poi `python -m pytest tests` dalla directory del
servizio. I test GLiNER delle finestre usano un modello simulato; il collaudo GPU
reale va eseguito nell'ambiente server con dati sintetici.

La protezione riguarda i testi inviati al modello esterno. I PDF e gli indici
originali restano nell'infrastruttura applicativa. Il riconoscimento automatico
può avere falsi negativi: mantenere un corpus italiano di regressione.
