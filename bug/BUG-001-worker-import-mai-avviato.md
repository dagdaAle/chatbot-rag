# BUG-001 — Import PDF bloccati: il worker non gira in produzione

**Data:** 2026-10-19
**Severità:** Alta (funzionalità core non operativa)
**Stato:** diagnosticato, fix pronto
**Componente:** deployment Coolify di `chatbot-rag`

## Sintomo

Ogni upload PDF resta eternamente "in elaborazione". Il job non avanza, il retry
risponde `409 Conflict`, il documento non compare mai nell'elenco e non è quindi
interrogabile dalla chat.

Job osservato in produzione:

```
id            = cf9e2b94-94d6-43b0-99e2-87f69cb5763a
filename      = professional-it-it-2026-web.pdf
size_bytes    = 6805486  (6,8 MB)
status        = running
stage         = extracting
progress      = 10
attempts      = 1 / 3
started_at    = 2026-10-19T18:52:28Z
updated_at    = 2026-10-19T18:52:29Z   <- fermo da ~2 ore
extractor     = null                   <- Docling mai partito
extractor_version = null
last_error_code = null
last_error_message = null
```

`started_at` e `updated_at` distano 0,7 secondi: la riga è stata scritta una volta
e mai più toccata. L'heartbeat della lease non ha mai battuto.

## Diagnosi

Il container `chatbot-rag` in produzione esegue **un solo processo**:

```
1 :: /bin/sh -c uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
7 :: python3.12 /usr/local/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Nessun `python -m app.worker`. Il worker d'importazione **non è mai stato avviato**.

Il flusso si interrompe esattamente così:

1. `POST /api/knowledge/{kb}/documents` salva il PDF e inserisce una riga in
   `import_jobs` passando per la RPC `chatbot_claim_import_job`/insert.
2. I log mostrano l'upload accettato e il frontend che interroga lo stato.
3. Nessuno processa la coda: `run_worker()` non è mai in esecuzione.
4. Il job resta `running` con `stage=extracting`, `progress=10` (valore della
   transizione iniziale), lease assegnata a un worker fantasma che non rinnova.

Controprova lato container: CPU al **0,17%** e **107 MB** di RAM su 62 GB. Se Docling
stesse estraendo un PDF da 6,8 MB, la CPU sarebbe satura e la memoria sopra il GB.

Il retry che restituisce `409 Conflict` è una conseguenza, non una causa: la RPC
`chatbot_retry_import_job` rifiuta il job perché lo vede ancora `running` e in lease
valida.

### Perché è successo

Nel repository il worker è configurato correttamente. Il `docker-compose.yml` alla
radice definisce il servizio `import-worker`:

```yaml
  import-worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    command: ["python", "-m", "app.worker"]
```

e `docs/IMPORT_WORKER.md` è esplicito:

> Start the API and exactly one worker with the same image/configuration
> ```sh
> uvicorn app.main:app --host 0.0.0.0 --port 8000
> python -m app.worker
> ```

**Coolify però non usa quel file.** Il compose generato da Coolify per
l'applicazione `1kx2w4ye7sd5jb9awemsq7yy` contiene un unico servizio, costruito dal
`Dockerfile`, il cui `CMD` è solo uvicorn. Il servizio `import-worker` non è mai
stato portato nel compose di produzione.

Il codice in produzione è comunque quello giusto: l'immagine
`1kx2w4ye7sd5jb9awemsq7yy:40bc8b3a...` corrisponde al commit `40bc8b3` di
`origin/main`, che include `backend/app/worker.py`. Manca solo il processo che lo
esegue, non il codice.

## Fix

Aggiungere il servizio worker al compose di produzione in Coolify. Stessa immagine,
stesso env, stesso volume `DATA_DIR`, comando diverso. Nessun `expose`, nessuna label
Traefik/Caddy: il worker non serve HTTP.

```yaml
  import-worker:
    image: '1kx2w4ye7sd5jb9awemsq7yy:40bc8b3a28495929a5913c4c1f410877aa9f733d'
    restart: unless-stopped
    command: ["python", "-m", "app.worker"]
    env_file:
      - .env
    volumes:
      - <stesso volume DATA_DIR del backend>:/data
    networks:
      - coolify
```

Dipendenze da rispettare, altrimenti il worker si rifiuta di partire:

- **`QDRANT_LOCAL_PATH` deve essere vuoto.** `run_worker()` solleva
  `RuntimeError("Il worker separato richiede Qdrant server; QDRANT_LOCAL_PATH embedded
  non è multiprocesso")` se è valorizzato. In produzione è già vuoto e il servizio
  Qdrant separato esiste (`rag-qdrant`).
- **`SUPABASE_ADMIN_KEY` è obbligatoria.** Senza, `run_worker()` solleva subito. È già
  presente nel backend.
- **Il volume `DATA_DIR` deve essere lo stesso del backend**, altrimenti il worker non
  trova i PDF caricati in `DATA_DIR/imports/<knowledge_id>/<job_id>.pdf`.

## Recupero dei job bloccati

Dopo il redeploy, il job `cf9e2b94` ha la lease scaduta e `attempts=1` su 3, quindi
`chatbot_claim_import_job` dovrebbe riprenderlo automaticamente. Se non accade, forzare
il reset:

```sql
update import_jobs
set status = 'pending',
    stage = null,
    progress = 0,
    lease_owner = null,
    lease_expires_at = null
where id = 'cf9e2b94-94d6-43b0-99e2-87f69cb5763a';
```

Il PDF originale deve essere ancora presente in `DATA_DIR/imports/`: senza, l'API
rifiuta il retry e il file va ricaricato.

## Prevenzione

Il compose di produzione diverge da quello del repository, e nulla lo segnala. Due
interventi:

1. **Tenere il compose in Coolify allineato al repository.** Se Coolify può puntare al
   `docker-compose.yml` versionato, usarlo come sorgente unica invece di un compose
   generato.
2. **Healthcheck del worker.** Il worker attuale non espone nulla di interrogabile. Un
   log di avvio (`Import worker avviato: <id>` è già emesso da `run_worker`) letto da un
   check esterno renderebbe visibile in un minuto un worker spento.

Nessuno dei due è stato implementato: questo documento è scritto contestualmente al
fix minimo.
