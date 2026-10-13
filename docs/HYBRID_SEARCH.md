# Ricerca ibrida

La ricerca combina due classifiche Qdrant:

- il vettore denso dell'embedding trova passaggi semanticamente affini;
- il vettore lessicale sparso trova parole, sigle e numeri realmente presenti nel
  testo. I riferimenti compatti come `123/2024`, `A-17/2025`, CIG e CUP ricevono
  anche una feature normalizzata con peso maggiore.

Qdrant applica IDF alla componente lessicale e fonde le due classifiche con
Reciprocal Rank Fusion (RRF). In questo modo non vengono confrontati direttamente
score di scale diverse. La soglia configurata continua a filtrare il ramo semantico;
un codice esatto può quindi recuperare un chunk anche quando la somiglianza
semantica è bassa. MMR viene applicato dopo la fusione per ridurre i duplicati.
La parte semantica include fino alle ultime due domande per comprendere i follow-up;
la parte lessicale usa soltanto la domanda corrente, così codici citati in precedenza
non contaminano una nuova ricerca esatta.

L'implementazione non scarica un altro modello e non usa API esterne: normalizzazione,
tokenizzazione e hashing sono deterministici. Ogni fonte API espone
`retrieval_method`, valorizzato con `hybrid_rrf` oppure `semantic_legacy` durante la
migrazione.

## Collezioni esistenti

Qdrant non permette di aggiungere un nuovo tipo di vettore a una collezione già
creata. Il comando di migrazione esegue quindi questi passaggi per ogni collezione:

1. copia tutti i punti e i vettori densi in una collezione di backup;
2. verifica che il numero di punti coincida;
3. ricrea la collezione applicativa con vettori densi e lessicali;
4. ricava l'indice lessicale dal testo già presente nei payload;
5. verifica nuovamente il numero di punti.

Se la ricostruzione fallisce, il comando tenta di ripristinare automaticamente la
collezione densa dal backup. Il backup `__dense_backup_<data>` viene conservato anche
dopo un esito positivo e va eliminato soltanto dopo il collaudo.

La migrazione richiede una finestra senza scritture. Dopo aver spostato la produzione
da Qdrant embedded al servizio Qdrant previsto dal worker:

```sh
docker compose stop backend import-worker
docker compose run --rm backend python -m app.hybrid_reindex --all
docker compose start backend import-worker
```

Per migrare una sola collezione:

```sh
python -m app.hybrid_reindex --collection kb_<uuid_con_underscore>
```

Prima di procedere, conservare anche il normale backup esterno di Qdrant. Durante il
deploy, le collezioni vecchie restano interrogabili con la ricerca semantica; il
worker rifiuta esplicitamente nuovi import su una collezione non migrata, evitando
indici misti o parziali.

## Collaudo

Dopo la migrazione, verificare almeno:

1. stesso numero di punti tra collezione applicativa e backup;
2. domanda concettuale, senza parole identiche al PDF;
3. ricerca di un numero di atto con separatori equivalenti, per esempio `123/2024`
   e `123-2024`;
4. fonte restituita con `retrieval_method: hybrid_rrf`;
5. caricamento di un nuovo PDF tramite il worker e successiva ricerca per codice.
