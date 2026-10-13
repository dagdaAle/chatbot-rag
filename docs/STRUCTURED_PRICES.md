# Listini strutturati e versioni

Questa funzione separa le domande numeriche dal normale RAG testuale. Durante
l'importazione, ogni tabella Docling con un'intestazione esplicita riconducibile a
prezzo, importo, tariffa o costo viene trasformata in righe tipizzate. Per ciascun
valore vengono conservati:

- codice, descrizione e unità di misura, quando presenti nelle rispettive colonne;
- valore `Decimal`, testo originale della cella, valuta esplicitamente indicata e
  nome della colonna prezzo;
- tutte le celle originali della riga;
- documento, tabella, indice di riga, pagina e coordinate della tabella nel PDF;
- serie, etichetta di versione e data effettiva ricavate dal nome file.

Il database `DATA_DIR/structured_prices.sqlite` è un indice derivato. Usa WAL per le
letture dell'API mentre il singolo worker importa; tutte le sostituzioni di un
documento avvengono in transazione. Eliminare un documento o una knowledge base
rimuove anche le relative righe strutturate.

## Versioni

I nomi seguenti vengono collegati automaticamente alla serie `listino materiali`:

```text
Listino materiali 2025.pdf
Listino materiali 2026.pdf
Listino materiali 2026-10-01.pdf
Listino materiali rev2.pdf
```

Una data completa viene registrata come data effettiva; un solo anno rimane
un'etichetta di versione e non viene trasformato in una data inventata. Nomi che non
contengono indicatori chiari restano versioni distinte con il nome completo.

## Interrogazioni verificate

Il backend riconosce richieste di consultazione, conteggio, statistiche e confronto,
per esempio:

```text
Quanto costa 001-A?
Quanti prodotti costano meno di 20 euro nel 2025?
Confronta il prezzo di 001-A tra 2025 e 2026.
Qual è il prezzo medio delle voci manutenzione?
```

Filtri, conteggi, minimi, massimi, medie, differenze e percentuali vengono calcolati
in Python con `Decimal`. La risposta viene costruita deterministicamente e non passa
al modello linguistico. Ogni riferimento numerato apre il PDF e mostra la riga
originale; l'interfaccia usa il badge **Verificato**. Se la domanda non trova righe
strutturate coerenti, il flusso torna alla ricerca RAG normale.

Il sistema non attribuisce una valuta assente, non completa celle vuote e non tratta
come prezzo una colonna priva di intestazione riconoscibile. Tabelle senza header o
con layout ambiguo restano disponibili nel normale contesto documentale.

## Documenti già importati

Dopo il deploy, ricostruire l'indice dai JSON Docling già salvati:

```sh
python -m app.price_reindex --all
# oppure
python -m app.price_reindex --knowledge <uuid>
```

Il comando richiede `SUPABASE_ADMIN_KEY`, legge soltanto i metadati dei documenti e
sostituisce l'indice derivato di ciascun documento. I file senza struttura salvata
vengono segnalati e non sono modificati.

## Backup e collaudo

Il backup operativo deve includere `structured_prices.sqlite`, `-wal` e `-shm`
insieme al resto di `DATA_DIR`. In alternativa, dopo il ripristino di Supabase,
`extracted/` e dei PDF, l'indice può essere ricostruito con il comando precedente.

Per il collaudo usare almeno due versioni reali dello stesso listino e verificare:

1. corrispondenza fra cella PDF, valore normalizzato e valuta;
2. codici con zeri, barre e trattini;
3. conteggio con soglie superiori, inferiori e intervalli;
4. confronto fra due versioni, inclusa la percentuale;
5. tabelle con più colonne prezzo;
6. eliminazione e nuova importazione dello stesso documento;
7. apertura delle fonti sulle pagine corrette.
