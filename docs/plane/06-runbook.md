Stato: bozza generata da agente · Aggiornato: 2026-11-16 · Fonte: chatbot-rag@09467b4 (main) + codex/docling-integration@c5e9379

# Runbook

## Open WebUI + gateway

| Sintomo | Causa | Fix |
|---|---|---|
| Un semplice saluto dà errore, DeepSeek non viene chiamato | GLiNER riconosce il nome tool builtin `ask_user` come persona; il gateway rifiuta richieste con PII in chiavi/identificativi | Fix `2921808`: eccezione solo per la costante nel campo nome-funzione. Se torna dopo un upgrade, aggiungere la nuova costante con test, mai esentare valori |
| Errore con tool calendario attivi | Falsi positivi su chiavi schema `location` e `rrule` | Stesso fix: stabili solo come chiavi strutturate e riferimenti `required` |
| Il collaudo passa su istanza pulita ma fallisce in produzione | Il fixture non riproduce i flag funzionalità di produzione | Usare `deploy/openwebui/builtin-smoke.py`, che legge i builtin realmente abilitati |
| La risposta compare tutta insieme, non in streaming | Voluto: SSE bufferizzato per non spezzare i segnaposto | Non introdurre inoltro parziale senza test su segnaposto divisi, tool args, errori |
| 503 dal gateway / dall'Anonymizer | Anonymizer in coda piena (4 richieste) o GLiNER non attivo | Controllare `docker logs anonymizer` e GPU. Nessun fallback in chiaro: è il comportamento atteso |
| Modifiche fatte dalla UI admin spariscono al riavvio | `ENABLE_PERSISTENT_CONFIG=false` | Cambiare il Compose |
| Dopo il ripristino gli utenti non riescono a entrare | `WEBUI_SECRET_KEY` diverso | Riusare lo stesso segreto con lo stesso volume |
| Build webui fallisce in `brand.py` | Blocco di branding upstream cambiato | Aggiornare `brand.py` dopo verifica, non forzare |

## Import PDF (legacy)

| Sintomo | Causa | Fix |
|---|---|---|
| Job `failed`, errore "Estrazione PDF incompleta: documento non indicizzato." su PDF digitale grande (BUG-001, 19/10) | Docling supera `PDF_CONVERSION_TIMEOUT=180`. Prima per OCR inutile, poi per layout + TableFormer su CPU con 2 thread fissi | `98e0e31`: OCR solo se manca testo nativo. `6a3406a`: `PDF_CPU_THREADS` letto davvero, `PDF_DEVICE=cuda` con fallback. Alzare `PDF_CONVERSION_TIMEOUT` (max 1800). Poi redeploy worker e **Riprova** |
| La GPU non accelera Docling | Immagine con torch CPU (`torch.cuda.is_available()` = False) | Worker con `backend/Dockerfile.cuda` + `docker-compose.gpu.yml` e nvidia-container-toolkit. Rollback: `PDF_DEVICE=cpu`. VRAM condivisa con Ollama e Anonymizer |
| "Il worker non gira" | Diagnosi sbagliata del 19/10: si guardava il container API, che esegue solo uvicorn | Il worker è un servizio separato (Coolify id 19) |
| Comportamento diverso fra API e worker | Le due risorse Coolify puntavano a immagini di commit diversi (`a0ca2dd` vs `40bc8b3`) | Deployare API e worker dalla stessa revisione |
| Worker non parte / errore su Qdrant | `QDRANT_LOCAL_PATH` impostato: lo storage embedded non si apre da due processi | Usare Qdrant server |
| Riaccodare un job a mano | — | `update import_jobs set status='pending', stage=null, progress=0, lease_owner=null, lease_expires_at=null, attempts=0 where id='<job>';` |

## Configurazione e dati (legacy)

| Sintomo | Causa | Fix |
|---|---|---|
| Cambio modello embedding rifiutato | Esistono vettori indicizzati | Migrazione/reindicizzazione esplicita. Le collezioni non vengono più ricreate da sole |
| Le variabili d'ambiente sembrano ignorate | `runtime_config.json` in `DATA_DIR` ha precedenza | Aggiornare via API impostazioni |
| Collezione vecchia non accetta nuovi import | Collezione senza indice lessicale | `python -m app.hybrid_reindex --all` (vedi `docs/HYBRID_SEARCH.md`) |
| Ollama non raggiungibile dal container | `host.docker.internal` non vale sul server; Mac mini spento, in sleep o con firewall | Puntare a `http://ollama:11434` sulla rete coolify. Per il Mac mini: firewall applicativo sbloccato per ollama e `pmset` senza sleep (comandi nel README) |
| Ogni chiamata autenticata risponde 503 | Cloudflare blocca come bot (403, code 1010) il download JWKS fatto con urllib; inoltre GoTrue self-hosted non emette il claim `iss` | Fix `f7df3a9`: JWKS scaricato con `requests`, token senza `iss` accettati mantenendo firma ES256, `aud`, `exp`, `sub` |
| Docling (preview) cambia `–` in `-` negli intervalli | Bug `docling-parse` #362 | Usare `pdf_backend=pypdfium2` (già fissato nella preview) |

## GDPR: cose da non dire

- L'Anonymizer fa pseudonimizzazione con possibili falsi negativi: non è anonimizzazione né conformità GDPR.
- Non proteggere i PDF e il DB dalla lettura sul server: protegge solo il testo verso il cloud.
- Uso dell'API `api.deepseek.com` per pratiche comunali reali: non proposto (provvedimento Garante 30/01/2025 n. 33, trasferimenti extra SEE). Dettagli nel vault `server/Chatbot RAG - GDPR e servizio ai Comuni.md`.
