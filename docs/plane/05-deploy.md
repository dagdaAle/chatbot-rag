Stato: bozza generata da agente · Aggiornato: 2026-11-16 · Fonte: chatbot-rag@09467b4 (main) + codex/docling-integration@c5e9379

# Deploy e operations

## Stato attuale (16/11/2026)

| Risorsa | Stato |
|---|---|
| intecha-chat (webui + privacy-gateway) | Archiviato il 10/11. Volume `intecha-openwebui-data` presente |
| Legacy `chatbot-rag` + `rag-import-worker` | Eliminati da Coolify il 12/11 |
| Route `chatbot.intecha.dev` | Tolta dal tunnel il 12/11 |
| Supabase, Qdrant, Anonymizer | Ancora attivi, nel progetto Coolify **intecha** |
| `intecha-docling-preview` | Attivo, fuori da Coolify |

## Runtime Open WebUI

| Voce | Valore |
|---|---|
| Gestione | Docker Compose a mano in `~/intecha-chat` sul server (cartella 0700, `.env` 0600). **Non registrato come risorsa Coolify** |
| Progetto compose | `intecha-chat` |
| Rete | `private` (internal) + `coolify` (esterna) |
| Dominio | `chatbot.intecha.dev`, router Traefik con priority 1000 da `deploy/openwebui/docker-compose.route.yml`, porta interna 8080. HTTPS dall'infrastruttura esistente |
| Authentik | Non usato: login nativo Open WebUI, signup chiuso |
| Healthcheck | webui: quello dell'immagine upstream. gateway: `HEALTHCHECK` su `/health`; webui parte solo con gateway healthy |
| Log | `docker compose logs`. Il gateway non scrive accessi, testi né errori upstream |
| Hardening gateway | `read_only`, `tmpfs /tmp`, `cap_drop ALL`, `no-new-privileges`, utente 65532 |

### Avvio / riattivazione

```sh
cd ~/intecha-chat
# anteprima privata su 127.0.0.1:3080
docker compose up -d --build
# pubblicazione dominio (serve anche la route nel tunnel, tolta il 12/11)
docker compose -f docker-compose.yml -f deploy/openwebui/docker-compose.route.yml up -d
```

Per ripartire sullo stesso volume serve lo stesso `WEBUI_SECRET_KEY`.

### Aggiornamento

Cambiare `OPENWEBUI_IMAGE` solo dopo aver verificato: `brand.py` (fallisce se il blocco upstream cambia), parametri inviati al gateway, tool calling, migrazioni schema, compatibilità account, percorso di ripristino. Il gateway si può ricostruire senza riavviare webui.

### Migrazione e cutover (30/10, storico)

Script in `deploy/openwebui/`, specifici per quel server: `server-bootstrap.py` → `export-legacy.py` → `migrate.py` (dentro webui, stadi riprendibili con `state.json`) → `verify-migration.py` → `builtin-smoke.py` / `synthetic-smoke.py` → `cutover.py`. File `auth.json` e `legacy.json` sensibili: restano solo sul server. Backup del cutover: `~/intecha-chat/backups/20261030T104300Z` con `checksums.json`; manifest `migration/cutover.json`.

### Rollback al legacy

Riavviare API e worker legacy dalla revisione nel manifest, fermare webui o ricrearlo senza override route. Non cancellare volumi. Le chat nuove su Open WebUI non tornano nel legacy: esportarle prima. `docker-compose.legacy.yml` non ricrea le risorse Coolify originali. Dopo il 12/11 il legacy non esiste più in Coolify: ripristino da `~/backups/chatbot-rag-20261112/` (procedura DA VERIFICARE).

## Legacy (fino al 30/10)

| Voce | Valore |
|---|---|
| Gestione | Coolify. Worker import: servizio id **19**. ID del backend: DA VERIFICARE |
| Immagini | API: `backend/Dockerfile` o `Dockerfile` radice (multi-stage, FastAPI serve anche la SPA). Worker: stessa immagine con `python -m app.worker`, oppure `backend/Dockerfile.cuda` + `docker-compose.gpu.yml` |
| Altri Dockerfile | `backend/Dockerfile.railway`, `frontend/Dockerfile.prod` + `nginx.conf`, `Dockerfile.qdrant`: residui del primo deploy su Railway |
| Authentik | Possibile filtro al proxy, non sostituisce JWT Supabase. Presenza reale DA VERIFICARE |
| Healthcheck | `GET /health` pubblico, `GET /health/qdrant` autenticato |
| Dati | `DATA_DIR=/data` sul server (compose locale usa `/app/data`): allineare API e worker |
| Migrazioni | 4 file SQL in `supabase/migrations`, a mano |

## Anonymizer

Compose a mano (`services/anonymizer/docker-compose.server.yml`), stessa forma di sbobina: container `anonymizer`, rete `coolify`, GPU NVIDIA riservata, nessuna porta né label Traefik. Percorso sul server al 06/10: `/home/mulo/anonymizer`. Aggiornare l'immagine senza cambiare volume `/data`, chiave e token. Prima: backup consistente del SQLite e conservare l'immagine precedente.

## Backup

| Cosa | Come |
|---|---|
| Anonymizer | `/opt/app-backup/app-backup.sh` alle 02:30 → restic cifrato sul NAS, host `anonymizer`, retention 7g/4s/12m. Restore: `restic restore latest --host anonymizer` |
| Docling preview | Stesso script, host `docling-preview` |
| Open WebUI | Manuale: `~/backups/intecha-chat-20261110/` (server) e `~/Progetti/archivio/intecha-chat-20261110/` (Mac, contiene segreti) |
| Legacy | Manuale: `~/backups/chatbot-rag-20261112/` |
| Qdrant | Nessuno |
| Supabase | DA VERIFICARE |

Al 10/11 non era stata fatta una prova di ripristino dei backup off-site (task #1506 nella todo-app).
