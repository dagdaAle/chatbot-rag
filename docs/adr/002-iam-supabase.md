# 002 — Identità Supabase e permessi in SQL

Data di ricostruzione: 2026-10-30. Stato: adottata nel codice.

## Contesto

La visibilità delle KB e delle chat deve restare coerente fra browser, API e accesso
PostgREST. Un ruolo contenuto in un token già emesso può essere superato da revoche.

## Decisione

Verificare JWT ES256 con JWKS Supabase e consultare il profilo corrente. Ruoli
`admin/member/viewer`; KB con proprietario, visibilità e assegnazioni. Calcolare il
permesso effettivo in SQL, applicare RLS e passare il JWT utente alle operazioni
ordinarie. Confinare le credenziali privilegiate a worker e funzioni amministrative.
Le chat restano del proprietario e richiedono ancora accesso alla KB.

## Alternative e conseguenze

Solo forward-auth Authentik non fornisce queste regole applicative; autorizzazioni
replicate nel frontend rischiano divergenze. La scelta attuale centralizza i controlli,
ma richiede test SQL e applicazione ordinata delle migrazioni. La migrazione IAM
sostituisce `manager/user` e aggiorna le policy precedenti: non usare il solo schema
iniziale come descrizione del sistema. Authentik può restare un filtro infrastrutturale,
con eventuale doppio login da verificare sul server.

## Evidenze e riesame

`backend/app/auth.py`, `202610140001_iam_ownership.sql`, `supabase/tests/iam.test.mjs`.
Prima di MCP/Hermes o SSO definire delega dell'identità e limiti delle credenziali;
non introdurre un bypass dell'IAM. [Architettura](../ARCHITECTURE.md).
