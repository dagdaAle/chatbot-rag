Stato: bozza generata da agente · Aggiornato: 2026-11-16 · Fonte: chatbot-rag@09467b4 (main) + codex/docling-integration@c5e9379

# Modello dati

## Runtime Open WebUI

| Archivio | Contenuto | Note |
|---|---|---|
| Volume `intecha-openwebui-data` → `/app/backend/data` | DB applicativo Open WebUI (utenti, chat, KB, file, grant) e indice Chroma | Schema e migrazioni gestiti da Open WebUI al primo avvio. Volume ancora presente dopo l'archiviazione del 10/11 |
| Volume Anonymizer `/data` | SQLite con mappe cifrate (Fernet), colonna `expires_at` | Mappe per richiesta, TTL 900 s, pulizia ogni minuto. Le mappe persistenti create con le API legacy non scadono |

Non si riusano lo schema Supabase né le collezioni Qdrant del legacy. I dati sono stati importati con script espliciti (`deploy/openwebui/migrate.py`):

| Dato migrato il 30/10 | Quantità |
|---|---|
| Account (admin attivi) | 2 |
| Knowledge base | 2 |
| PDF | 4 |
| Conversazioni / messaggi | 14 / 40 |

- Gli hash bcrypt sono copiati, le password restano quelle di prima. Le sessioni non sono migrate.
- Mappa degli ID utente/KB/file. Gli ID delle conversazioni restano gli stessi.
- `[Fonte N]` nelle chat importate diventa `[N]` collegato al nuovo file.
- Non migrati: quote e consumi, audit, indice prezzi, risposte deterministiche dei listini.
- Il migratore si ferma su utenti non-admin, inattivi o con reset obbligatorio.

## Legacy (main)

### Supabase Postgres

| Tabella | Ruolo |
|---|---|
| `app_profiles` | Ruolo corrente (`admin/member/viewer`), stato account, quote |
| `knowledge_bases` | KB con proprietario e visibilità |
| `knowledge_members` | Assegnazioni utente ↔ KB |
| `documents` | Documenti pubblicati |
| `import_jobs` | Coda import: stato, stage, progress, attempts, lease, ultimo errore |
| `conversations`, `messages` | Chat personali, messaggi e fonti salvate (anche estratti originali) |
| `app_models`, `model_members` | Catalogo modelli, accessi, tariffe |
| `usage_events` | Consumi e prenotazioni |
| `admin_audit` | Modifiche amministrative |

Relazioni: utente → profilo, KB possedute, assegnazioni, conversazioni. KB → documenti, import, conversazioni. Conversazione → messaggi. Cancellare una KB cancella a cascata anche le chat collegate (migrazione IAM).

Funzioni SQL principali: `chatbot_kb_permission` (fonte unica dei permessi), `chatbot_claim_import_job`, `chatbot_update_import_job`, `chatbot_retry_import_job`, `chatbot_reserve_request`, `save_chat_turn`, `chatbot_admin_save`, `chatbot_usage_summary`.

### Migrazioni

`supabase/migrations/`, da applicare in ordine, senza runner automatico:

1. `202610070001_chatbot.sql` — `knowledge_bases`, `documents`, `conversations`, `messages`, RLS
2. `202610070002_admin_usage.sql` — profili, assegnazioni KB, modelli, consumi, audit
3. `202610130001_import_jobs.sql` — coda import
4. `202610140001_iam_ownership.sql` — ruoli `member/viewer`, ownership, permessi in SQL

Test SQL: `supabase/tests/*.test.mjs` (RLS, IAM, admin).

### Altri archivi legacy

| Archivio | Contenuto |
|---|---|
| Qdrant | Una collezione per KB `kb_<uuid_con_underscore>` (vecchia: `documents`). Vettori dense + sparse lessicali, payload chunk con provenienza |
| `DATA_DIR` (`/app/data` in compose, `/data` sul server) | `imports/` (PDF pendenti), `uploads/`, `extracted/` (JSON Docling), `runtime_config.json`, prompt personalizzato |
| SQLite WAL in `DATA_DIR` | `price_list_versions`, `price_list_entries`: indice listini ricostruibile dai JSON |

Qdrant non è fonte di autorizzazioni. Nessuna transazione distribuita fra Postgres, file e Qdrant: lease, cleanup e pubblicazione finale gestiscono il recupero.

## Stato dei dati dopo l'archiviazione

| Dato | Dove sta | Backup |
|---|---|---|
| Open WebUI | volume `intecha-openwebui-data` + `~/backups/intecha-chat-20261110/` (server) + `~/Progetti/archivio/intecha-chat-20261110/` (Mac, contiene segreti) | manuale |
| Legacy app | `~/backups/chatbot-rag-20261112/` (server) | manuale |
| Qdrant | container ancora attivo | **nessun backup** (indici derivati, considerati ricostruibili) |
| Anonymizer | volume `/data` | restic notturno 02:30 sul NAS; esclusi i modelli (1,1 GB) — dettaglio DA VERIFICARE |
| Supabase | `supabase.intecha.dev` | DA VERIFICARE |
