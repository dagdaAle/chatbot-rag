# Chatbot RAG - Qdrant + FastAPI + React

Chatbot RAG avanzato con supporto per documenti PDF, chunking semantico e diversi provider LLM.

## Stack

- **Qdrant**: vector database (ricerca semantica con MMR)
- **FastAPI**: backend Python
- **React + Vite + TypeScript**: frontend

## Caratteristiche

- **Chunking intelligente**: 2000 caratteri con overlap 250, divisione semantica su paragrafi e frasi
- **Ricerca ibrida**: embedding semantici + indice lessicale IDF, fusi con RRF; codici e numeri di atto ricevono un segnale esatto aggiuntivo
- **Recupero gerarchico**: il chunk trovato viene ampliato all'articolo o alla sezione Docling completa, entro un budget configurabile
- **Listini strutturati**: prezzi, conteggi, statistiche e confronti fra versioni sono calcolati su celle tipizzate con provenienza verificabile
- **Risultati diversificati**: MMR (Maximum Marginal Relevance) riduce i chunk duplicati
- **Provider multipli**: DeepSeek e OpenAI con protezione obbligatoria, Ollama locale
- **Protezione dati**: domanda, cronologia e fonti passano dall’Anonymizer prima del modello esterno; ripristino della risposta nel backend
- **Filtro per score**: filtraggio automatico di chunk poco rilevanti
- **Citazioni precise**: risposte con citazioni verbatim dai documenti

## Provider supportati

### Chat
- **DeepSeek**: provider esterno predefinito
- **OpenAI**: GPT-4o, GPT-4o-mini, GPT-4-turbo, GPT-3.5-turbo
- **Ollama**: modelli locali compatibili

### Embeddings
- **Ollama**: nomic-embed-text, mxbai-embed-large, all-minilm

*Gli embedding restano locali con Ollama. Le chiamate chat esterne richiedono
l’Anonymizer configurato: [configurazione e deploy](docs/PRIVACY_PIPELINE.md).*

## Avvio rapido

Configurare prima `.env`, includendo token Anonymizer condiviso e chiave Fernet
esclusiva del servizio. La chiave non viene passata al backend.

```bash
docker compose up -d
```

Servizi:
- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API docs**: http://localhost:8000/docs
- **Qdrant dashboard**: http://localhost:6333/dashboard

## Comandi

```bash
# Avvia
docker compose up -d

# Build + avvio (dopo modifiche)
docker compose up -d --build

# Log
docker compose logs -f

# Stop
docker compose down
```

## Configurazione

Copia `.env.example` in `.env` e configura le chiavi API necessarie:

```bash
cp .env.example .env
```

### Variabili principali

```env
# Provider per chat
LLM_PROVIDER=deepseek  # deepseek, openai, ollama

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_CHAT_MODEL=gpt-4o-mini
EMBEDDING_PROVIDER=ollama


# Ollama (locale)
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

La chat esterna richiede anche `ANONYMIZER_URL` e `ANONYMIZER_TOKEN`, come
descritto in [docs/PRIVACY_PIPELINE.md](docs/PRIVACY_PIPELINE.md).

## Struttura

```
├── backend/          # FastAPI
├── frontend/         # React + Vite + TS
├── docker-compose.yml
└── .env.example
```

## Affidabilità e limiti operativi

- Il worker d’importazione separato richiede Qdrant server. Non avviarlo con
  `QDRANT_LOCAL_PATH`: lo storage embedded non può essere aperto da due processi.
- `DATA_DIR` contiene conversazioni, PDF, prompt, metadati e configurazione runtime;
  il volume persistente deve essere montato su quel percorso. Salvare anche Qdrant
  (percorso `QDRANT_LOCAL_PATH` o volume del server) nei backup.
- Il cambio del modello embedding è rifiutato quando esistono vettori: richiede
  una migrazione esplicita. Non vengono più ricreate automaticamente le collezioni.
- Upload PDF: massimo 20 MB per file. Il PDF viene salvato sul volume e messo nella
  coda persistente Supabase; il worker Docling locale gestisce struttura, tabelle e OCR.
  Stato, avanzamento e nuovo tentativo sono visibili nella pagina Knowledge base.
- Il retrieval ibrido applica la soglia al ramo semantico e fonde con RRF il ramo
  lessicale; include le ultime due domande;
  non è una riscrittura della query tramite LLM. Cronologia: massimo 12 messaggi
  e 16000 caratteri. Le fonti recuperate non costituiscono una validazione delle
  singole affermazioni generate.
- Le collezioni create da questa versione includono l'indice lessicale. Le collezioni
  precedenti restano leggibili in modalità semantica, ma devono essere migrate prima
  di nuovi import seguendo [docs/HYBRID_SEARCH.md](docs/HYBRID_SEARCH.md).
- Dopo il ranking, il recupero gerarchico riunisce i chunk con gli stessi riferimenti
  strutturali; per i PDF senza gerarchia include i chunk adiacenti. Configurazione e
  limiti sono descritti in [docs/HIERARCHICAL_RETRIEVAL.md](docs/HIERARCHICAL_RETRIEVAL.md).
- Le tabelle con colonne prezzo riconoscibili alimentano un indice SQL derivato nel
  volume `DATA_DIR`. Le risposte numeriche non sono affidate al modello: dettagli,
  limiti e reindicizzazione sono in [docs/STRUCTURED_PRICES.md](docs/STRUCTURED_PRICES.md).

Test backend (virtualenv, dipendenze in `backend/requirements.txt` + pytest/httpx):

```bash
PYTHONPATH=backend python -m pytest backend/tests
```

## DeepSeek + Ollama sul Mac mini

Configurazione senza servizi OpenAI (il pacchetto Python `openai` resta soltanto
come client compatibile con l'API DeepSeek):

```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=<impostare come segreto in Coolify>
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_CHAT_MODEL=deepseek-flash
EMBEDDING_PROVIDER=ollama
OLLAMA_BASE_URL=http://192.168.1.22:11434
OLLAMA_CHAT_MODEL=gpt-oss:20b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
DATA_DIR=/data
QDRANT_LOCAL_PATH=/data/qdrant
```

Rimuovere `OPENAI_API_KEY`, `OPENAI_EMBEDDING_API_KEY` e gli override OpenAI
nel deploy dopo aver verificato eventuali indici esistenti. Se esiste
`runtime_config.json`, la configurazione salvata ha precedenza sulle variabili:
aggiornare anche quella tramite le API impostazioni, rispettando il blocco del
cambio embedding quando gli indici contengono documenti.

Prima del primo deploy con `DATA_DIR=/data`, salvare e trasferire gli eventuali
file esistenti da `/app/data` al volume persistente. Non sovrascrivere dati già
presenti. Verificare dal container sia `/api/tags` sia una chiamata `/api/embed`
con `nomic-embed-text`; dalla sola macchina Mac mini il test non prova la LAN.

Sul Mac mini, Terminale locale con privilegi amministratore:

```bash
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add /opt/homebrew/opt/ollama/bin/ollama
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --unblockapp /opt/homebrew/opt/ollama/bin/ollama
sudo pmset -a sleep 0 disksleep 0 powernap 0
```

Questa configurazione usa la LAN. Non pubblicare l'API Ollama direttamente su
Internet. Dopo gli aggiornamenti di Ollama ricontrollare raggiungibilità e regole.

## Autenticazione e database applicativo Supabase

Login email/password per utenti invitati, verifica ES256 tramite JWKS pubblico,
metadati KB/documenti e conversazioni su Supabase Postgres via PostgREST con JWT
utente. Le RLS proteggono conversazioni e messaggi personali. KB e documenti sono
accessibili in base al profilo corrente e alle assegnazioni; gli amministratori
gestiscono tutte le KB e i gestori modificano i documenti delle KB assegnate.
Qdrant conserva vettori e chunk; i PDF rimangono nel volume persistente.

Prima del deploy applicare lo schema e assegnare l'amministratore seguendo
[docs/SUPABASE.md](docs/SUPABASE.md), poi attivare lettore e amministrazione
seguendo [docs/ADMIN_READER.md](docs/ADMIN_READER.md). La gestione utenti e la
contabilizzazione richiedono `SUPABASE_ADMIN_KEY` esclusivamente sul backend;
non esporla nel frontend. I vecchi metadati JSON e le conversazioni SQLite
richiedono un'importazione esplicita, senza attribuzioni automatiche.
