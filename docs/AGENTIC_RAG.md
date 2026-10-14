# RAG agentico con DeepSeek Flash

La chat DeepSeek approfondisce la domanda con strumenti in sola lettura.
Restano FastAPI, Supabase/RLS, Docling, Qdrant, embedding locali e listini SQLite.
Non occorre reindicizzare i documenti o installare un framework agentico.

## Percorso

1. L'endpoint verifica utente, knowledge, conversazione e modello e riserva la
   richiesta tramite la quota esistente. La cronologia proviene dal server.
2. Le domande riconosciute dal motore listini mantengono la risposta
   deterministica senza LLM. Le altre chat DeepSeek entrano nell'orchestratore.
3. La ricerca ibrida locale recupera fino a sei frammenti iniziali, usando anche
   le ultime due domande per le richieste successive nella conversazione.
4. DeepSeek riceve domanda, cronologia e prove protette e propone strumenti.
   Il backend valida gli argomenti, esegue nel perimetro autorizzato e protegge
   i nuovi risultati prima della chiamata successiva.
5. La risposta deve citare almeno una `[Fonte N]` ricevuta e nessuna fonte
   inesistente. Un tentativo di correzione consuma gli stessi limiti. In assenza
   di prove, al limite o con output troncato si restituisce un messaggio esplicito.
6. Si ripristina solo la risposta finale; risposta e fonti si salvano come prima.
   Il transcript degli strumenti e il ragionamento restano in memoria e non
   vengono restituiti al browser o salvati nelle conversazioni.

Ollama e gli altri provider mantengono il percorso RAG precedente.

## Strumenti e perimetro

| Strumento | Input | Operazione |
|---|---|---|
| `search_documents` | query, top_k 1–6, document_ref opzionale | Ricerca ibrida nel perimetro del chiamante |
| `read_section` | source_id già ricevuto | Espansione gerarchica con indicazione di completezza |
| `find_document_versions` | filtro sul nome, anche vuoto | Fino a 20 candidati, riferimenti Dn e metadati dei listini |
| `query_price_list` | domanda italiana con operazione e codici | Motore deterministico esistente: lookup, count, compare, stats |

Il modello non può scegliere knowledge/tenant, inviare SQL, aprire URL o file,
scrivere dati o chiamare strumenti arbitrari. `document_ref` deve provenire dal
catalogo della stessa esecuzione. I riferimenti `Fonte N` conservano la propria
identità tra ricerche ed espansioni: massimo 24 fonti e budget testuale del
retrieval. Le ricerche identiche non si ripetono. I permessi di pubblicazione/RLS
si ricontrollano negli strumenti e prima di restituire/salvare gli originali.
La revoca di una fonte raccolta blocca la risposta.

Il modello vede alias `Documento Dn`, non i nomi originali dei file, che possono
contenere dati personali anche con underscore. Etichette di versione prive di
un formato numerico noto vengono omesse/sostituite; gli originali restano nella
risposta delle fonti per l'utente autorizzato.

Il catalogo generico non è un registro giuridico delle versioni: le date di
caricamento non attestano vigenza e `filename_date_hint` è ricavata dal nome del
listino. Occorre leggere i documenti. Se manca un calcolo verificabile, lo
strumento lo dichiara senza stimare dati mancanti.

## Protezione su più passaggi

Il primo batch usa `/v1/protect`; i successivi `/v1/protect/extend`, con lo stesso
UUID temporaneo per l'intera domanda. L'estensione richiede autenticazione,
riconoscitori completi e una mappa temporanea esistente/non scaduta. Non prolunga
il TTL e non usa mappe persistenti legacy. I segnaposto precedenti non vengono
analizzati nuovamente; i valori già noti si proteggono anche quando il
riconoscitore non li rileva nel nuovo testo. I token ammessi sono cumulativi.

Si proteggono contenuti, ragionamento e argomenti degli strumenti. Gli ID delle
chiamate e i nomi degli strumenti sono validati e mantenuti per il protocollo.
JSON con escape Unicode viene normalizzato prima della protezione. Le query
con segnaposto si ripristinano **solo per la ricerca interna**: DeepSeek non
riceve gli originali del vault. Nessuna chiave Fernet è condivisa con il backend.
La mappa viene cancellata nel finally; il TTL gestisce interruzioni e pulizie
fallite. Un errore di protezione blocca ulteriori chiamate esterne.

La pseudonimizzazione può avere falsi negativi. Le istruzioni nei documenti
sono trattate come dati non fidati; strumenti limitati e prompt riducono
l'impatto della prompt injection, non dimostrano immunità del modello.
Il controllo citazioni verifica esistenza e perimetro, **non** che ogni frase
sia semanticamente provata: occorre un collaudo sui documenti reali.

## Configurazione e costi

```env
AGENTIC_RAG_ENABLED=true
AGENTIC_MAX_STEPS=3
AGENTIC_MAX_TOOL_CALLS=6
AGENTIC_TIMEOUT_SECONDS=120
AGENTIC_MAX_OUTPUT_TOKENS=12000
AGENTIC_MAX_INPUT_BYTES=250000
AGENTIC_REASONING_EFFORT=none
```

Tre cicli di approfondimento consentono al massimo quattro chiamate al modello,
compresa la risposta finale; le correzioni consumano gli stessi passaggi. Al
limite si impone `tool_choice=none`. Il budget output è cumulativo, inclusi i
token di reasoning rendicontati. Senza dati di consumo, si riserva l'intero
massimale della chiamata. Il limite input misura conservativamente byte UTF-8
serializzati, inclusi strumenti e transcript, sommati tra richieste: non è un
tokenizer. Le risposte API aggiungono `research` con numero chiamate, strumenti
eseguiti e motivo d'arresto, senza dati intermedi.

La deadline si verifica tra operazioni; ogni chiamata DeepSeek usa il tempo
residuo e disabilita i retry SDK. Le operazioni locali/DB/Anonymizer mantengono i
propri timeout: non è una cancellazione forzata del thread allo scadere.
Ogni chiamata LLM registra un evento `chat` sotto la stessa richiesta riservata.
I costi restano stime sulle tariffe configurate: non calcolano separatamente
cache e fasce orarie DeepSeek. Non registrare prompt o ragionamenti.

`none` disabilita il ragionamento ma consente tool calling; `low` lo abilita e
lo reinvia protetto nei passaggi successivi, come richiede DeepSeek. Non è
presente escalation automatica a Pro o ad altri provider.

## Merge e deploy

Questa feature dipende dalla PR Anonymizer: unire prima la base, poi questa
feature. La sola branch non modifica la produzione.

1. Backup coerente del vault e chiave originale custodita separatamente.
2. Aggiornare **prima Anonymizer** da `services/anonymizer`, conservando GPU,
   alias, volume e chiavi. Verificare protect → extend → restore → delete.
3. Aggiornare chatbot e worker alla stessa revisione, con embedding locali e
   chiavi OpenAI vuote; collaudare con due utenti.
4. Verificare codici, sezioni, versioni, listini, errori e consumo per domanda.

Un Anonymizer senza `/v1/protect/extend` blocca il secondo passaggio con HTTP 503:
non esiste un ripiego verso l'invio in chiaro. `AGENTIC_RAG_ENABLED=false`
ripristina il RAG precedente protetto. Non ripristinare revisioni che inviano
contesti esterni senza protezione.

## Verifiche ripetibili

```bash
PYTHONPATH=backend python -m pytest backend/tests -q
cd services/anonymizer
python -m pytest tests -q
cd ../../frontend
npm run build
npm run lint
```

I test backend usano un modello simulato e ispezionano i payload per il provider:
ricerche successive, mappa unica, ripristino interno, isolamento, revoca permessi,
fonti stabili, reasoning, limiti, errori e citazioni. I test del servizio coprono
estensione, TTL, mappe estranee e pulizia. `scripts/agentic/verify_live.py` usa
dati fittizi, retrieval simulato e GPU/DeepSeek reali in container di prova:
verifica il protocollo, non la qualità di ricerca dei PDF di produzione.

Riferimenti: [tool calling DeepSeek](https://api-docs.deepseek.com/guides/tool_calls/),
[reasoning](https://api-docs.deepseek.com/guides/thinking_mode/).
