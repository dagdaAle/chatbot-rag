# Recupero gerarchico

La ricerca ibrida individua i frammenti più rilevanti, chiamati *anchor*. Prima di
costruire il prompt, il backend usa la struttura estratta da Docling per recuperare
gli altri chunk appartenenti allo stesso articolo o alla stessa sezione.

L'identità della sezione deriva da `section_refs`, gli identificatori strutturali
univoci prodotti durante l'estrazione. `section_path`, per esempio
`Titolo I > Articolo 7`, viene usato come etichetta leggibile e come fallback per i
documenti indicizzati in precedenza. I chunk vengono ordinati, le intestazioni
ripetute vengono rimosse e gli overlap testuali vengono ricomposti.

Il prompt distingue chiaramente:

- `sezione completa`, quando tutti i chunk della sezione rientrano nel budget;
- `estratto esteso della sezione`, quando la sezione è troppo lunga e vengono scelti
  il frammento trovato e i chunk strutturalmente più vicini;
- `passaggio con contesto adiacente`, per i PDF senza una gerarchia riconosciuta.

Anchor della stessa sezione vengono riuniti una sola volta. Pagine, regioni di
provenienza e contenuto tabellare restano associati alla fonte aggregata. La risposta
API espone `context_scope`, `section_complete` ed `expanded_chunks`, così interfaccia
e log possono mostrare come è stato costruito il contesto.

## Limiti configurabili

```dotenv
RETRIEVAL_SECTION_MAX_CHARS=18000
RETRIEVAL_TOTAL_MAX_CHARS=48000
RETRIEVAL_NEIGHBOR_CHUNKS=1
```

Il primo limite controlla la dimensione massima di un singolo articolo o sezione; il
secondo protegge il budget complessivo della domanda. Il terzo si applica soltanto ai
documenti senza struttura e indica quanti chunk includere prima e dopo l'anchor.

Non serve reindicizzare i PDF strutturati già prodotti dalla feature Docling: i
payload Qdrant contengono già `section_refs` e `section_path`. I vecchi PDF estratti
con pypdf ricevono automaticamente il contesto adiacente.

## Collaudo

Verificare almeno:

1. domanda che colpisce il paragrafo centrale di un articolo distribuito su più
   chunk: la fonte deve indicare `section_complete` e includere inizio e fine;
2. due anchor nello stesso articolo: deve essere restituita una sola fonte aggregata;
3. sezione oltre il limite: l'anchor deve restare presente e la fonte deve risultare
   incompleta;
4. PDF senza intestazioni: devono essere inclusi soltanto i chunk adiacenti previsti;
5. apertura della fonte nel lettore PDF sulle pagine aggregate.
