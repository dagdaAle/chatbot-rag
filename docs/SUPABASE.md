# Attivazione Supabase

Il codice usa Auth Supabase ES256, database applicativo via PostgREST con JWT
utente e RLS, Qdrant per vettori/chunk, PDF sul volume DATA_DIR.
Per la versione multiutente con admin e consumi, completare questa procedura
iniziale e poi seguire [ADMIN_READER.md](ADMIN_READER.md): richiede una seconda
migrazione e `SUPABASE_ADMIN_KEY` solo sul backend. Il browser usa la chiave
pubblica. Non sono presenti signup pubblico, OAuth o magic link.
Dopo la seconda migrazione, ruoli e permessi si gestiscono dal pannello admin;
modificare gli app_metadata non aggiorna più il ruolo applicativo corrente.

## Operazioni da eseguire sul server (amministratore)

1. Fare backup del volume dati, Qdrant e degli eventuali file `/app/data` prima
   del deploy. La nuova versione non legge più le conversazioni SQLite né i
   metadati JSON: non li cancella e non assegna automaticamente chat preesistenti
   a un utente. L'importazione è esplicita (vedi sotto).
2. Eseguire una sola volta `supabase/migrations/202610070001_chatbot.sql` come
   amministratore del database (SQL editor di Studio oppure psql interno).
3. Assegnare il ruolo amministratore dell'app all'utente previsto:

```sql
update auth.users
set raw_app_meta_data = coalesce(raw_app_meta_data, '{}'::jsonb)
  || '{"chatbot_role":"admin"}'::jsonb
where email = 'dagda.ale@gmail.com';
```

   Verificare che la modifica interessi un solo utente. Non cambiare `role` da
   `authenticated` a `admin`: il ruolo app sta soltanto negli `app_metadata`.
   Fare logout/login dopo la modifica per ricevere un nuovo JWT.
4. Configurare in Coolify:

```env
SUPABASE_URL=https://supabase.intecha.dev
SUPABASE_PUBLISHABLE_KEY=sb_publishable_eOn6jCKOJYVPzRh39CQIFJ_0zYEU4iV
SUPABASE_JWT_ISSUER=https://supabase.intecha.dev/auth/v1
DATA_DIR=/data
QDRANT_LOCAL_PATH=/data/qdrant
```

   Confermare che `iss` nei token ES256 corrisponda al valore configurato; se
   l'istanza self-hosted usa un issuer differente, impostare quello esatto,
   senza disattivare la verifica. Gli altri campi richiesti sono `exp`, `iat`,
   `sub` UUID, `aud=authenticated`, `role=authenticated`.
5. Build frontend: `VITE_SUPABASE_URL` e `VITE_SUPABASE_PUBLISHABLE_KEY` sono
   argomenti di build nel Dockerfile principale; i default sono già quelli
   dell'istanza. Il container backend deve poter raggiungere JWKS pubblico e
   `/rest/v1`. Nessun collegamento diretto al PostgreSQL è necessario.
6. Se Authentik protegge ancora il dominio chatbot, l'utente vedrà due login.
   Dopo la verifica del login Supabase, rimuovere soltanto il forward-auth
   Authentik da questo host se si vuole un unico accesso. Non cambiare il routing
   dei domini Supabase o delle altre applicazioni.

## Verifiche dopo il deploy

- Senza bearer token, `/api/knowledge`, `/api/conversations`, `/health/qdrant`
  devono rispondere 401; `/health` rimane pubblico per il monitoraggio.
- Utente normale: può leggere KB/PDF e chattare; upload, delete documenti,
  modifica prompt/modelli devono rispondere 403 anche chiamando le API a mano.
- Due utenti distinti: la conversazione creata da A non deve apparire a B;
  GET/DELETE e aggiunta messaggi con ID di A devono fallire o non trovare righe.
- Anche PostgREST diretto, chiamato con publishable key e JWT di B, deve
  restituire zero conversazioni/messaggi di A. Con sola publishable key nessuna
  delle quattro tabelle deve essere leggibile.
- Refresh pagina, rinnovo della sessione, logout, cambio utente, PDF in nuova
  scheda: le richieste devono usare il token corrente; il token non va nell'URL.

Il logout rimuove la sessione dal browser. La verifica JWT è stateless: un access
 token già copiato resta valido fino alla scadenza. Non sostituisce la revoca
 immediata lato Auth; configurare la durata delle sessioni secondo le esigenze.

## Dati precedenti

Se esistono KB/indici legacy, gli ID di Supabase devono restare quelli originali
per conservare il collegamento alle collezioni `kb_<uuid_con_underscore>` e ai
PDF. `scripts/export_legacy_supabase.py` genera SQL da JSON/SQLite/metadata
Qdrant, senza contattare servizi remoti e senza cambiare i file originali.
Richiede un UUID proprietario esplicito per tutte le chat legacy. Eseguirlo
solo se quelle chat appartengono effettivamente a quell'utente; altrimenti
separare l'importazione per proprietario.

```bash
python scripts/export_legacy_supabase.py \
  --data-dir /percorso/copia-backup \
  --owner-user-id UUID_UTENTE_SUPABASE \
  --output import-legacy.sql
```

La directory deve contenere `knowledges.json`, `conversations.db` (se presente)
e `qdrant/` (se presente). Usare una copia coerente del backup, non aprire lo
storage Qdrant live da un secondo processo. Il SQL contiene i testi delle chat:
conservarlo in un percorso protetto, importarlo come admin e poi eliminarlo.
I PDF vanno copiati in DATA_DIR/uploads preservando le directory UUID. Nessun
embedding viene rigenerato o spostato. Il modello embedding deve restare quello
usato dagli indici: non passare a Ollama su vettori OpenAI esistenti.

## Test locali

```bash
PYTHONPATH=backend python -m pytest backend/tests
npm ci --prefix supabase/tests
npm test --prefix supabase/tests
npm ci --prefix frontend
npm run build --prefix frontend
npm run lint --prefix frontend
```

I test RLS usano PostgreSQL locale in WebAssembly (PGlite), con funzioni Auth
simulate, e non si collegano all'istanza Supabase. La conferma sull'istanza reale
richiede l'applicazione della migrazione e prove con due account creati dall'admin.
