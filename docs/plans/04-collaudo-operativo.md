# Fase 04 — Collaudo operativo e distribuzione

Stato: proposta. L'inventario può iniziare prima; il rilascio segue le fasi validate.
Questa attività documentale non accede al server né distribuisce modifiche.

## Obiettivo

Far coincidere codice, schema, volumi e indici effettivamente usati; provare il
ripristino e rendere distinguibili errori di import, ricerca e generazione.

## Attività

- [ ] Inventariare revisioni/immagini API, worker e Anonymizer, configurazione effettiva,
  catalogo modelli, runtime_config e raggiungibilità Ollama dai container.
- [ ] Controllare le quattro migrazioni, proprietari delle RPC e isolamento con due utenti.
- [ ] Verificare Qdrant server, collezioni ibride, modello/dimensione/encoder compatibili,
  conteggi e documenti pubblicati; non dedurre la migrazione dalla sola presenza del codice.
- [ ] Allineare DATA_DIR/mount API-worker e provare import, crash, lease scaduto e retry.
- [ ] Riprovare i PDF dei ticket storici con misure attuali prima di chiudere i problemi;
  confrontare CPU/GPU solo su ambiente e carichi misurati.
- [ ] Collaudare protect/extend/restore/delete e assenza di chiamate esterne su errore.
- [ ] Verificare routing Coolify, health check e necessità del filtro Authentik;
  mantenere Supabase come identità applicativa.
- [ ] Eseguire backup coerente e ripristino isolato di Postgres, Qdrant, DATA_DIR e
  vault Anonymizer con la chiave custodita separatamente.
- [ ] Pubblicare configurazione scelta, risultati RAG e procedura di ritorno alla revisione precedente.

## Verifiche e completamento

Suite backend/SQL/frontend pertinenti, smoke UI e prove live con account distinti.
Confermare chat private, autorizzazioni KB/PDF, quote, fonti, listini e import completo.
Conservare data, revisione e risultato delle verifiche senza credenziali o contenuti
sensibili. I test simulati non sostituiscono queste verifiche operative.

## Ripristino e rischi

Separare rollback di codice, schema e indice: vecchie immagini possono richiedere
schemi differenti. Nessun rollback deve riattivare invio esterno senza protezione.
Non rilanciare migrazioni non idempotenti e non sovrascrivere volumi esistenti.
Il piano si completa quando rilascio e ripristino sono stati provati e documentati,
non quando termina soltanto una build.
