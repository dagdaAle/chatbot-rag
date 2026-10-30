# Intecha Chat — Open WebUI + Anonymizer

Open WebUI v0.12.5 è la nuova applicazione chat/RAG. Un overlay minimo applica il
marchio Intecha; un gateway interno protegge tutte le chiamate DeepSeek tramite
l'Anonymizer già esistente. Embedding e indicizzazione restano locali via Ollama.

[Architettura e deploy](docs/OPENWEBUI.md) · [Gateway](services/privacy-gateway/README.md) ·
[Decisione](docs/adr/006-openwebui-intecha.md) · [Documentazione](docs/README.md)

## Avvio

Il Compose richiede una rete Docker esistente (`coolify` predefinita), Ollama e
Anonymizer già raggiungibili su quella rete. Non ricrea i loro volumi o le chiavi.

```sh
cp deploy/openwebui/.env.example .env
# Configurare i segreti server nel .env, senza versionarlo.
# La chiave provider va solo al gateway; la chiave Fernet resta nell'Anonymizer.
docker compose config --quiet
docker compose up -d --build
```

Anteprima su `127.0.0.1:3080`, dati in `intecha-openwebui-data`. Il dominio viene
attivato separatamente con `deploy/openwebui/docker-compose.route.yml` dopo
migrazione e collaudo. La registrazione pubblica è disabilitata.

## Protezione e limiti

Il gateway espone solo chat/completions e models, verifica il protocollo Anonymizer,
protegge anche tool e chiamate successive e ripristina le risposte prima di restituirle.
In caso di errore non invia testi al provider senza protezione. Immagini/audio e
API non supportate sono rifiutate. Le risposte SSE sono bufferizzate: il testo viene
mostrato al termine della generazione, dopo ripristino completo.

Il riconoscimento PII automatico può avere falsi negativi. PDF, indici e chat originali
rimangono sul server. Non configurare connessioni remote che aggirino il gateway.

## Marchio e licenza

Il proprietario ha confermato il 30 ottobre 2026 l'installazione/distribuzione entro
50 persone con accesso diretto in qualsiasi finestra mobile di 30 giorni. Il rebranding
usa questa eccezione della licenza Open WebUI; oltre il limite occorre ripristinare
il marchio originale o ottenere autorizzazione/licenza adeguata.
[Attribuzioni e condizioni](deploy/openwebui/NOTICE.md),
[licenza upstream](deploy/openwebui/UPSTREAM_LICENSE).

## Verifica

```sh
PYTHONPATH=services/privacy-gateway backend/.venv/bin/python -m pytest services/privacy-gateway/tests -q
```

La suite del gateway è indipendente dal vecchio backend. Serve un venv con
`services/privacy-gateway/requirements.txt` e pytest. Per migrazione, verifiche reali
e rollback leggere [OPENWEBUI.md](docs/OPENWEBUI.md).

## Applicazione precedente

`backend/`, `frontend/`, `supabase/`, i runbook e i volumi originali sono conservati
per consultazione, migrazione e ripristino; non sono il runtime del Compose predefinito.
Il Compose precedente è `docker-compose.legacy.yml`, il Dockerfile `Dockerfile.legacy`.
Il motore deterministico dei listini non è collegato automaticamente alla nuova UI;
il relativo codice e indice originale restano conservati. Quote/consumi storici
Supabase restano nell'esportazione e non vengono trasformati in statistiche Open WebUI.
