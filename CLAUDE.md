# CLAUDE.md — chatbot-rag

Chatbot RAG su documenti PDF: **Qdrant** (vector db) + **FastAPI** + **React/Vite/TS**.
Chunking semantico, ricerca MMR, provider intercambiabili (OpenAI o Ollama) per chat
ed embeddings separatamente. In produzione su `chatbot.intecha.dev`, dietro Authentik
(gruppo `utenti-app`).

Stack, provider supportati e avvio: `README.md`. Qui le regole operative.

## ⚠️ Questa repo è pubblica, l'app è in produzione

È una scelta, non una dimenticanza (rilievo **REP-02**). Conseguenza pratica:
**niente documenti, chiavi, prompt di clienti o nomi propri** in questa repo.
La chiave OpenAI vive solo nelle variabili d'ambiente su Coolify.

## Da non toccare

| Elemento | Regola | Perché |
|---|---|---|
| Chunking **2000 caratteri / overlap 250** | Non cambiare senza reindicizzare tutto | I chunk già in Qdrant sono stati creati con questi valori. Cambiarli a metà produce un indice misto, dove i risultati vecchi e nuovi non sono confrontabili: le risposte peggiorano senza un errore. |
| Il modello di embedding | Cambiarlo = **reindicizzare da zero** | I vettori di modelli diversi non sono nello stesso spazio. Mescolarli rende la ricerca semantica silenziosamente sbagliata, non rotta. |
| La collection Qdrant | Non cancellare senza avere i PDF originali | I documenti indicizzati sono ricostruibili solo se hai ancora le fonti. |
| MMR nella ricerca | Non sostituire con una top-k semplice | Serve a evitare che le prime 5 risposte siano lo stesso paragrafo cinque volte. |
| Il filtro per score | Non alzare la soglia per "avere più risultati" | Chunk poco rilevanti nel contesto peggiorano la risposta più di quanto un chunk in meno la impoverisca. |
| `.env` | Git-ignored, e va così | `.env.example` elenca le chiavi: `OPENAI_API_KEY` non entra nella repo. |

## Comandi

```bash
docker compose up -d                  # tutto lo stack
docker compose up -d --build          # dopo modifiche

# frontend: :5173 · API: :8000 · docs: :8000/docs · Qdrant: :6333/dashboard
```

## Regole operative

- Commit in italiano, indicativo presente: "Sopprimi warning pypdf nei log".
- **Citazioni verbatim**: le risposte citano i documenti testualmente. Non
  introdurre riformulazioni del testo citato — è la garanzia di verificabilità
  che rende utile un RAG su documenti.
- Chat ed embeddings possono usare **provider diversi** (es. Ollama + embeddings
  OpenAI): mantenere i due percorsi indipendenti, non accorparli.
- Il frontend compila in `/app/static`, servito da FastAPI nell'immagine unica.
- `Dockerfile.railway` / `nginx.railway.conf`: residui di Railway, non la produzione.

## Cosa non fare

- **Non committare PDF di prova.** Finirebbero in una repo pubblica e nella storia
  di git per sempre.
- **Non cambiare provider in produzione senza verificare il costo**: Ollama gira
  sul server (GPU RTX 3060), OpenAI si paga a token. Il default non è neutro.
- **Non riavviare su Coolify per applicare una variabile**: serve **stop + start**.
- **Non presumere che Ollama sia raggiungibile solo in locale**: sul server è in
  ascolto su `*:11434` (rilievo SEC-07). Non costruirci sopra assunzioni di sicurezza.
- Non confondere questa repo con `lookover-labs/chatbot_sorg-`: stesso stack, ma
  quella è il chatbot sui documenti di un **comune** ed è privata.

## Riferimenti

- `README.md` — stack, provider, chunking, avvio
- Cugina: `lookover-labs/chatbot_sorg-` (stesso stack, documenti comunali)
- Vault Obsidian, `server/STATO-SERVER.md`
