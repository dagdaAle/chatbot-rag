# Lettore integrato e amministrazione multiutente

## Comportamento

Le fonti si aprono nella stessa pagina della chat: PDF autenticato, pagina citata e testo evidenziato. Il pannello si ridimensiona con il separatore (anche con frecce da tastiera); «Comprimi chat» conserva conversazione e bozza. Su telefono si alternano chat e PDF senza smontare la chat. I vecchi URL `/pdf-viewer` restano compatibili. L'evidenziazione richiede testo estraibile dal PDF: documenti immagine senza OCR o testo diverso dal chunk possono non produrre una corrispondenza; il passaggio originale è comunque consultabile nel lettore.

La sezione **Amministrazione** è riservata agli amministratori e gestisce:

- Utenti: creazione diretta senza SMTP, nome, email, ruolo, sospensione, password temporanea con cambio obbligatorio, revoca delle sessioni.
- Quote chat: richieste mensili (mese UTC), per minuto e simultanee. Comprendono errori e risposte senza contesto. Le prenotazioni interrotte scadono dopo 15 minuti. Le quote non limitano i caricamenti documenti.
- Knowledge base: elenco completo, condivisione con tutti o assegnazione individuale. I gestori possono caricare/eliminare documenti solo nelle KB loro assegnate con «Gestisce documenti». Creazione/eliminazione KB resta amministrativa.
- Modelli: catalogo consentito, abilitazione e assegnazioni individuali. Ogni richiesta sceglie il proprio modello; non cambia quello degli altri utenti. Un catalogo abilitato non installa un modello Ollama e non configura una chiave provider.
- Utilizzi: filtro per periodo, utente, provider e modello; richieste, chiamate chat/embedding, errori, token, durata, stime di costo e CSV. L'account personale vede solo i propri consumi.
- Registro delle modifiche amministrative. Le chat restano private del proprietario anche rispetto agli amministratori.

I permessi sono verificati a ogni richiesta e nelle politiche RLS del database, usando il profilo corrente e non il vecchio ruolo nel token. Non è possibile rimuovere/sospendere l'ultimo amministratore operativo. Un amministratore cambia la propria password da **Account**, non tramite il reset amministrativo.

## Attivazione su installazione esistente

1. Eseguire un backup del database Supabase. Verificare che la migrazione `202610070001_chatbot.sql` sia già applicata e che esista almeno un utente con `raw_app_meta_data.chatbot_role = admin`.
2. Applicare **una volta**, come amministratore del database, `supabase/migrations/202610070002_admin_usage.sql` nell'istanza Supabase corretta. La migrazione è transazionale. I ruoli admin esistenti vengono importati; gli altri utenti diventano utenti ordinari. Le KB esistenti restano condivise per mantenere gli accessi correnti. La migrazione non cancella chat, PDF o vettori.
3. Impostare `SUPABASE_ADMIN_KEY` esclusivamente nell'ambiente del backend sul server, usando la credenziale `service_role` valida per l'istanza. Non inserirla nel frontend, in variabili `VITE_*`, in Git o nei log. La chiave pubblica resta quella già configurata. Questa credenziale serve anche alla contabilizzazione delle richieste chat: se manca, le nuove richieste sono rifiutate prima di chiamare il modello.
4. Distribuire backend e frontend insieme, dopo la migrazione. La versione nuova richiede il nuovo schema. Per Docker Compose, ricostruire i servizi backend/frontend con la configurazione locale del server.
5. Accedere con l'admin esistente. Nel catalogo verificare i modelli realmente disponibili e aggiungere l'eventuale modello personalizzato attualmente configurato (per esempio quello Ollama). Disabilitare i modelli non disponibili. I valori iniziali del catalogo sono esempi dei modelli già supportati, non una verifica della loro disponibilità attuale.
6. Inserire le tariffe correnti dei provider. Registrare anche il modello embedding configurato, con tipo «Embedding (tariffe)»; per embedding impostare la tariffa output a zero se prevista dal provider. Cambiare qui il tipo/tariffa non modifica il modello embedding operativo: quello resta nelle impostazioni esistenti e può richiedere reindicizzazione.
7. Verificare con un account ordinario e un gestore: isolamento delle KB, divieto di amministrazione, cambio password obbligatorio, revoca sessioni e limite richieste. Aprire una fonte da una chat e controllare bozza, pagina, evidenziazione e visualizzazione mobile.

## Precisione dei consumi e limiti

Il monitoraggio parte dalla distribuzione: non ricostruisce token storici. Ogni chiamata completata registra i token restituiti dal provider; se assenti restano sconosciuti, non zero. I costi stimati conservano una copia delle tariffe applicate e distinguono USD/EUR senza conversione. Non sono una fattura: cache, sconti, retry interni al client/provider, chiamate fallite con consumo non restituito e infrastruttura Ollama possono non essere quantificabili. Una richiesta può generare più eventi: prenotazione, embedding e generazione; non sommarli come numero di domande.

I riepiloghi paginano il database fino a 100.000 eventi per filtro; oltre richiedono di restringere il periodo. La dimensione dei documenti preesistenti non viene ricostruita. Il reset password/email dipende dall'API amministrativa GoTrue dell'istanza; va collaudato sul server di destinazione. Il cambio password personale richiede la password attuale. La sospensione blocca l'applicazione; non elimina l'identità o i suoi contenuti.

## Verifiche eseguite localmente

- Backend: `cd backend && python -m pytest tests -q` — 56 test passati.
- Autorizzazioni SQL: `cd supabase/tests && npm test` — suite RLS originaria e suite admin passate, eseguendo entrambe le migrazioni in PGlite con schema auth simulato.
- Frontend: `cd frontend && npm run lint && npm run build` — verificati; la build segnala alcuni bundle grandi già legati all'editor e alla sintassi dei messaggi.
- Browser: `node frontend/tests/integrated-ui.cjs` con Vite su `127.0.0.1:5173`, Playwright disponibile e, opzionalmente, `CHROME_PATH`. Passati: PDF nella stessa pagina, testo evidenziato, cambio pagina, bozza conservata, compressione, ridimensionamento, mobile, moduli admin, consumi e blocco admin per utenti ordinari. Autenticazione/API simulate e PDF reale locale. Nessuna verifica effettuata sul server di produzione, nessun accesso a credenziali riservate.
