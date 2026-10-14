# Protezione chatbot → Anonymizer → DeepSeek

La ricerca ibrida/gerarchica usa i dati originali nell'infrastruttura applicativa.
Prima di ogni chiamata chat esterna, il backend invia domanda, cronologia
server-side, prompt di sistema e contesto a `/v1/protect` dell'Anonymizer.
I nomi dei file delle fonti sono sostituiti con `Fonte N`; titoli e testo vengono
protetti insieme. Le fonti originali e le coordinate PDF rimangono nella risposta
API per l'utente autorizzato. Non occorre reindicizzare né migrare Supabase.

Ogni richiesta crea un UUID indipendente. La mappa temporanea è condivisa tra
tutti i suoi messaggi, rimane cifrata nell'Anonymizer e viene cancellata nel
`finally`. Le mappe orfane scadono dopo 15 minuti. La risposta del modello viene
ripristinata solo con i segnaposto emessi in quella richiesta, poi salvata in
Supabase. Gli SDK ricevono esclusivamente i messaggi protetti.

Timeout, schema inatteso, GLiNER disabilitato, segnaposto estranei o alterati e
fallimenti di ripristino producono un errore controllato HTTP 503. In caso di
protezione fallita non parte nessuna chiamata al modello. Il client interno non
segue redirect né usa proxy d'ambiente. Il token non viene inviato al browser.

Gli embedding esterni sono bloccati sia nelle impostazioni sia nei metodi di
query/importazione: il provider deve essere `ollama`. Non viene cambiato
silenziosamente il modello degli indici esistenti. Le risposte deterministiche
dei listini e la chat locale Ollama non richiedono una chiamata esterna.

## Configurazione

Backend, solo variabili server:

```env
ANONYMIZER_URL=http://anonymizer:8000
ANONYMIZER_TOKEN=<segreto condiviso>
ANONYMIZER_CONNECT_TIMEOUT=5
ANONYMIZER_READ_TIMEOUT=120
ANONYMIZER_MAX_CHARS=200000
EMBEDDING_PROVIDER=ollama
```

Anonymizer: stessa `ANONYMIZER_TOKEN`, `ANONYMIZER_KEY` Fernet originale,
`DEVICE=cuda`, `MAPPING_TTL_SECONDS=900`. Un solo worker Uvicorn.
Non impostare la chiave Fernet sul backend. Per i dettagli del contratto, dei
limiti e della migrazione SQLite vedere [il servizio](../services/anonymizer/README.md).
I limiti si applicano anche ai testi protetti, che possono crescere per effetto
dei segnaposto. Il token di servizio è comune ai client interni autorizzati:
non deve essere distribuito ai client finali.

## Deploy coordinato tramite Coolify

1. Salvare configurazione Coolify, immagine precedente e backup SQLite coerente
   del vault, oltre alla chiave custodita separatamente. Conservare il volume.
2. Costruire l'Anonymizer da `services/anonymizer` e aggiornare il suo servizio
   interno mantenendo rete, alias `anonymizer`, volume `/data` e GPU NVIDIA.
   L'aggiunta di `expires_at` è automatica e preserva le mappe legacy persistenti.
3. Verificare `/health`: `device=cuda`, `protocol_version=1`,
   `recognizers_complete=true`; collaudare protect/restore/delete con dati fittizi.
4. Configurare il token originale sul chatbot e aggiornare app e worker alla
   stessa revisione. Confermare Ollama anche in `runtime_config.json`, che ha
   precedenza sulle variabili d'ambiente. Le chiavi OpenAI restano vuote.
5. Verificare login, due utenti, conversazioni successive, riferimenti PDF,
   listini e pulizia delle mappe. Simulare un servizio non raggiungibile in un
   ambiente di prova e verificare HTTP 503 e zero chiamate esterne.

Non aggiornare solo il backend: il vecchio Anonymizer non espone `/v1/protect`
e il nuovo backend bloccherebbe correttamente le chat esterne. Un rollback di
sicurezza deve conservare il controllo di protezione, oppure disabilitare la
chat esterna; ripristinare il vecchio chatbot riaprirebbe l'invio non protetto.

## Verifica

```bash
PYTHONPATH=backend python -m pytest backend/tests
cd services/anonymizer
python -m pytest tests
```

`scripts/privacy/verify_live.py` va eseguito in un container backend isolato con
`PYTHONPATH=/app`, codice candidato e variabili rivolte a un Anonymizer di prova.
Usa solo dati sintetici, controlla il payload prima della chiamata DeepSeek reale,
verifica ripristino e concorrenza e misura testi da 10k, 40k e 80k caratteri.
Le misure singole non sono percentili di produzione.

La pseudonimizzazione protegge l'uscita verso il modello; non anonimizza PDF,
Supabase, Qdrant o dati mostrati all'utente autorizzato. Il riconoscimento può
avere falsi negativi e va calibrato con documenti italiani rappresentativi.
Le regole privilegiano checksum e contesto per non confondere codici di atto,
prezzi e identificativi di prodotto con dati personali.
