# Persistent PDF import worker

Uploads are persisted under `DATA_DIR/imports/<knowledge_id>/<job_id>.pdf` and inserted
in the Supabase `import_jobs` queue. The HTTP request returns after enqueueing. A
dedicated Python process claims one job at a time, extracts and embeds it, then writes
Qdrant, the original PDF, structured JSON and finally the public `documents` row.
Until that final publication, chat and the document list cannot see the new document.

## Database

Apply `supabase/migrations/202610130001_import_jobs.sql` after the two existing
migrations. It provides:

- job status, stage, progress, attempts, safe error text and extractor metadata;
- an atomic `FOR UPDATE SKIP LOCKED` claim RPC;
- a renewable 10-minute lease (configurable from 60 to 1800 seconds);
- recovery of expired leases and failure after three interrupted attempts;
- RLS visibility through existing knowledge permissions;
- a manager-authorized retry RPC for failed jobs.

Only a service-role request can claim or advance jobs. Browsers receive only the
publishable key and their own JWT. Failed jobs retain the pending PDF so a manager can
retry; successful jobs remove it. Deleting a knowledge base cascades its database jobs
and application cleanup removes its `imports/` directory.

## Processes

Start the API and exactly one worker with the same image/configuration:

```sh
uvicorn app.main:app --host 0.0.0.0 --port 8000
python -m app.worker
```

Both processes need the same persistent `DATA_DIR` volume. The worker also needs
`SUPABASE_ADMIN_KEY`; keep it server-side. Configuration:

```dotenv
IMPORT_WORKER_POLL_SECONDS=3
IMPORT_WORKER_LEASE_SECONDS=600
```

The worker renews its lease while Docling or embedding runs. Every retry removes any
partial vector points, document row, final PDF and extracted JSON for its fixed
`document_id` before rebuilding them. This prevents duplicate chunks after a crash.
Errors exposed to the UI are bounded and sanitized; full exceptions stay in worker
logs.

## Qdrant requirement

The separate worker requires **Qdrant server mode** (`QDRANT_HOST`/`QDRANT_PORT`). It
refuses to start when `QDRANT_LOCAL_PATH` is set because two processes must never open
the same embedded Qdrant directory. Local `docker-compose.yml` already uses a Qdrant
service.

The current production deployment previously used embedded `/data/qdrant`. Before
starting this worker in Coolify:

1. make a verified backup/snapshot of the existing collection and PDFs;
2. create a Qdrant service inside the Chatbot RAG project with persistent storage;
3. restore the collection into that service and compare collection name, vector size
   and point count;
4. configure both API and worker with the Qdrant service host and remove
   `QDRANT_LOCAL_PATH` from both;
5. mount the existing application data volume at `/data` in both resources;
6. apply the import-jobs migration, then start one worker.

Do not point the worker at the live embedded directory. Deployment and migration of
production Qdrant are deliberately separate from merging this code branch.

## UI and operations

The knowledge page polls active jobs every three seconds and shows queue, extraction,
embedding, indexing and publication progress. Failed jobs display a safe message and
a **Riprova** action. Published jobs disappear from the queue and appear in the normal
document list.

Backups must now include `DATA_DIR/imports` as well as `uploads`, `extracted`, Qdrant
and Supabase. A database backup without the pending PDF cannot resume an incomplete
job; the API rejects retry when that file is missing.
