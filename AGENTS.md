# Intecha Chat — istruzioni per gli agenti

## Runtime corrente

Open WebUI v0.12.5 con overlay minimo Intecha e gateway di uscita verso DeepSeek.
Leggere [architettura/deploy](docs/OPENWEBUI.md), [prodotto](docs/PRODUCT.md),
[design](docs/DESIGN.md), [ADR 006](docs/adr/006-openwebui-intecha.md) e
[contratto gateway](services/privacy-gateway/README.md). Risposte in italiano.

`backend/`, `frontend/` e `supabase/` sono il prodotto precedente conservato:
non modificarli come se fossero il runtime nuovo. La fotografia della precedente
architettura è in [ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Stack e percorsi

- Upstream Open WebUI: immagine fissata per versione e digest nel Dockerfile.
- `deploy/openwebui/brand.py`: overlay nome/asset; nessuna riscrittura del RAG upstream.
- `services/privacy-gateway/gateway/main.py`: FastAPI + httpx, protocollo OpenAI testuale.
- `services/anonymizer/`: servizio esistente, Presidio/GLiNER/vault cifrato.
- `docker-compose.yml`: WebUI e gateway; Ollama e Anonymizer su rete privata esistente.
- `deploy/openwebui/`: configurazione, migrazione server-side, licenza e routing.
- `intecha-openwebui-data`: archivio persistente separato; mai riutilizzare direttamente
  lo schema Supabase o il vecchio Qdrant come database Open WebUI.

## Comandi dalla radice

```sh
# Configurare prima .env da deploy/openwebui/.env.example; mai stampare docker compose config senza --quiet.
docker compose config --quiet
docker compose up -d --build
docker compose ps
# Python: venv, mai pip globale sull'host
python3.12 -m venv .venv
.venv/bin/python -m pip install -r services/privacy-gateway/requirements.txt pytest
PYTHONPATH=services/privacy-gateway .venv/bin/python -m pytest services/privacy-gateway/tests -q
# Pubblicazione del dominio solo dopo migrazione/collaudo:
docker compose -f docker-compose.yml -f deploy/openwebui/docker-compose.route.yml up -d
```

Open WebUI gestisce le proprie migrazioni al primo avvio. Le vecchie migrazioni
`supabase/migrations` riguardano solo il legacy; non applicarle al nuovo archivio.
Migrazione dati: script e precauzioni in [OPENWEBUI.md](docs/OPENWEBUI.md). Gli script
specifici del server verificato non vanno eseguiti su ambienti diversi alla cieca.

## Vincoli

- Ogni chiamata cloud, comprese task/query generation e tool loop, passa dal gateway.
  Nessun fallback in chiaro; errori upstream/client sempre sanitizzati.
- Solo gateway possiede DEEPSEEK_API_KEY. Open WebUI possiede una chiave interna distinta.
  Nessuna chiave Fernet nel gateway o WebUI. Mai loggare prompt, risposte, mappe o segreti.
- Embedding locali. Nuove API multimodali/cloud richiedono protezione e test prima di abilitarle.
- Stream bufferizzato intenzionale: non introdurre inoltro parziale senza verificare
  segnaposto divisi tra chunk, tool args, errori e cleanup.
- Preservare chat per proprietario, KB private e condivise e ID mappati nella migrazione.
  Non interpretare i ruoli Open WebUI come equivalenti automatici dell'IAM legacy.
- Rebranding autorizzato con eccezione <=50 utenti/30 giorni: conservare licenza/notice.
  Non aggirare funzioni enterprise; aggiornare la valutazione prima di aumentare il pubblico.
- Per aggiornare upstream verificare brand.py, parametri inviati al gateway, tool calling,
  schema/migrazioni, compatibilità degli account e percorso di ripristino.
- Analisi prima dell'implementazione. Branch `codex/`, preservare modifiche altrui,
  test pertinenti e documentazione aggiornata. Non dichiarare test live o deploy non eseguiti.
- Vecchi dati/volumi si conservano fino a verifica e backup; mai cancellarli durante un deploy.
- Per sole modifiche Markdown controllare link/coerenza; per gateway eseguire la suite.
