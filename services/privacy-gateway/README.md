# Intecha Privacy Gateway

Confine di uscita testuale OpenAI-compatible fra Open WebUI e DeepSeek.
Le chiavi provider esistono solo qui; Open WebUI possiede una chiave interna diversa.
Anonymizer rimane un servizio esterno privato, con token esistente e chiave Fernet separata.

## Flusso

Ogni POST `/v1/chat/completions` crea una mappa temporanea. Protegge contenuto dei
messaggi (anche parti testuali), cronologia, reasoning, argomenti tool JSON, descrizioni
e campi testuali degli schemi. Le chiavi JSON e gli identificativi protocollo vengono
analizzati come invarianti: se contengono dati riconosciuti come personali, la
richiesta viene rifiutata prima del provider, senza modificare lo schema.
Il nome pubblico builtin `ask_user` di Open WebUI v0.12.5 è riconosciuto come costante
solo nei campi nome-funzione (GLiNER può scambiarlo per un nome utente). Le etichette pubbliche calendario `location` e `rrule` sono stabili solo come chiavi
strutturate e riferimenti `required`. I valori restano protetti, anche quando
contengono le stesse parole. I riferimenti `required` vengono verificati come
invarianti per mantenerli coerenti con le proprietà. Nessuna esenzione per valori
di contenuto/argomenti o identificativi arbitrari. Per più di 64 campi usa protect/extend e una seconda
passata per propagare le entità riconosciute nei batch successivi. La richiesta al
provider parte soltanto dopo validazione del protocollo e dei segnaposto.

La risposta viene controllata e ripristinata, inclusi reasoning e argomenti degli
strumenti, prima di essere restituita a Open WebUI. Gli argomenti JSON vengono
ri-serializzati dopo il ripristino per preservare quote e caratteri speciali.
Ogni chiamata successiva dell'agente ripete la protezione con una nuova mappa: i
testi originali rimangono interni. Il finally elimina la mappa; il TTL recupera le
pulizie fallite. Nessun testo o errore upstream viene scritto nei log del gateway.

## Contratto e limiti

- `/v1/models` autenticato espone solo i modelli configurati.
- Solo chat/completions verso il provider DeepSeek fisso; nessun proxy generico,
  endpoint Responses, embedding remoto, audio, immagine o URL multimodale.
- Upload/documenti vengono estratti localmente da Open WebUI prima del gateway.
- Header `user`, proxy d'ambiente, redirect e credenziali del chiamante non vengono
  inoltrati al provider. Parametri sconosciuti sono rifiutati.
- Massimo 180.000 caratteri originali e 200.000 protetti; payload massimo 1,5 MB.
- Stream del client supportato come SSE **bufferizzato**: il provider genera senza
  streaming; il risultato arriva dopo validazione/ripristino completo. Nessun testo
  progressivo durante la generazione. Questo evita segnaposto spezzati tra chunk.
- Reasoning disabilitato per default; richieste esplicite supportate e protette.
- Health è liveness, non prova disponibilità del provider o completezza riconoscitori;
  quest'ultima è verificata su ogni protect.
- Riconoscimento PII automatico con possibili falsi negativi: non è anonimizzazione
  totale e non protegge i PDF o il database dalla lettura sul server.
- Filtri o altri provider aggiunti dall'amministratore non devono bypassare il gateway.
  Le connessioni dirette sono disabilitate nel deployment; non è un firewall host.

## Verifica

Dalla radice, con ambiente Python contenente requirements e pytest:

```sh
PYTHONPATH=services/privacy-gateway backend/.venv/bin/python -m pytest services/privacy-gateway/tests -q
```

La suite usa Anonymizer/provider simulati per verificare i payload di rete, blocco
su errore, multi-turn, tool JSON, stream, protocollo e credenziali. Il test live va
eseguito con soli dati sintetici e riportato separatamente. Nessuna chiave Fernet
è necessaria al gateway. Variabili: GATEWAY_API_KEY, DEEPSEEK_API_KEY,
ANONYMIZER_TOKEN, ANONYMIZER_URL, GATEWAY_MODELS.
