# BUG-001 — Import PDF: timeout Docling su documenti digitali di grandi dimensioni

**Data:** 2026-10-19
**Severità:** Media (workaround disponibile, ma blocca i listini tecnici)
**Stato:** diagnosticato, causa individuata, fix proposto
**Componente:** `backend/app/core/pdf_extraction.py`, config `PDF_CONVERSION_TIMEOUT`

## Sintomo

L'import di `professional-it-it-2026-web.pdf` (listino Liebherr, 100 pagine, 6,8 MB)
fallisce sempre. Nell'interfaccia il job resta "in elaborazione" per qualche minuto e
poi passa a `failed`. Il retry riproduce lo stesso errore.

```
status        = failed
progress      = 100
attempts      = 1 / 3
last_error_code    = ValueError
last_error_message = "Estrazione PDF incompleta: documento non indicizzato."
completed_at  = 2026-10-19T18:55:42Z
```

## Diagnosi

### Il documento non ha nulla di rotto

Verificato con PyMuPDF sul PDF originale estratto dal volume:

```
pagine          = 100
testo totale    = 376.013 caratteri
pag 1          -> 113 char di testo nativo
pag 2          -> 905 char
pag 3          -> 1.846 char
pag 4          -> 3.009 char
```

È un **PDF nativamente digitale**, con il testo selezionabile. Non è una scansione e
non ha bisogno di OCR.

### Cosa succede realmente

Dal log del worker:

```
18:52:28  job cf9e2b94 reclamato, stage=extracting
18:52:29  tesseract --list-langs          (Docling inizializza l'OCR)
18:55:41  Finished converting document document.pdf in 192.23 sec
18:55:41  ValueError: Estrazione PDF incompleta: documento non indicizzato.
```

Docling impiega **192,23 secondi** e restituisce uno stato diverso da
`ConversionStatus.SUCCESS`. Il codice lo rifiuta:

```python
if result.status != ConversionStatus.SUCCESS:
    raise ValueError("Estrazione PDF incompleta: documento non indicizzato.")
```

Il rifiuto è corretto: un `ConversionStatus` parziale non va indicizzato, altrimenti si
indicizza silenziosamente metà documento. Il problema è a monte.

### Perché 192 secondi

`PDF_CONVERSION_TIMEOUT=180` e Docling ne impiega 192. Il timeout viene superato, la
conversione si interrompe e il risultato è marcato parziale.

Il tempo è dominato dall'OCR, che qui è **completamente inutile**. La configurazione del
converter lo forza su ogni pagina:

```python
options = PdfPipelineOptions(
    do_ocr=True,                       # <-- forzato sempre
    do_table_structure=True,
    document_timeout=settings.pdf_conversion_timeout,
    accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CPU, num_threads=2),
    ocr_options=TesseractCliOcrOptions(lang=["ita", "eng"]),
)
```

Su 100 pagine di un PDF digitale, Docling renderizza ogni pagina come immagine, invoca
Tesseract su finestre di OCR, e su quasi tutte fallisce con `Too few characters.
Skipping this page` (184 occorrenze nei log). Lavoro sprecato che consuma il budget di
tempo.

Il collo di bottiglia è amplificato da `num_threads=2` su CPU. Su questo host c'è una
RTX 3060, ma il worker è configurato in CPU.

### Perché il job resta "in elaborazione" a lungo

Il worker fa conversione, embedding e indicizzazione in sequenza. Con 100 pagine più
l'OCR inutile, l'utente vede un job che macina per minuti prima di fallire. Non è un
blocco, è lentezza dovuta al lavoro sprecato.

## Fix proposti

### 1. Non fare OCR sui PDF che hanno già testo (fix primario)

Docling ha l'opzione `do_ocr` per pipeline: va attivata solo quando il PDF è
effettivamente scansionato. Un pre-check con PyMuPDF costa millisecondi e decide:

```python
import fitz  # pymupdf

def _has_native_text(content: bytes, sample_pages: int = 5, min_chars: int = 200) -> bool:
    with fitz.open(stream=content, filetype="pdf") as doc:
        pages = min(sample_pages, doc.page_count)
        chars = sum(len(doc[i].get_text().strip()) for i in range(pages))
    return chars >= min_chars * pages
```

Poi `do_ocr=_has_native_text(...) is False`. Su `professional-it-it-2026-web.pdf` il
controllo restituirebbe `True` e l'OCR verrebbe saltato: il tempo di conversione
crolla e il timeout smette di essere un problema.

### 2. Alzare il timeout per i documenti grandi

`PDF_CONVERSION_TIMEOUT=180` è troppo stretto per 100 pagine. Il campo accetta fino a
1800:

```dotenv
PDF_CONVERSION_TIMEOUT=900
```

Da solo potrebbe bastare, ma non risolve lo spreco: 900 secondi di OCR inutile sono
peggio di 60 secondi senza OCR.

### 3. Usare la GPU

`AcceleratorOptions(device=AcceleratorDevice.CPU, num_threads=2)` ignora la RTX 3060
dell'host. Con Docling su GPU il layout e la struttura delle tabelle sono molto più
rapidi. Richiede `torch` con CUDA e l'immagine costruita per CUDA.

## Recupero del job bloccato

Il PDF originale è ancora sul volume:

```
/data/imports/529ab1f3-1489-4dea-b0d8-110bcd81250c/cf9e2b94-94d6-43b0-99e2-87f69cb5763a.pdf
6.805.486 byte
```

Il job è `failed` con `attempts=1` su 3, quindi il pulsante **Riprova** funziona
(`chatbot_retry_import_job` accetta i job `failed`). Ma riprovare senza modificare la
configurazione riprodurrà lo stesso timeout.

Ordine corretto: applicare il fix, rideployare il worker, poi riprovare il job.

Per riaccodare a mano:

```sql
update import_jobs
set status = 'pending', stage = null, progress = 0,
    lease_owner = null, lease_expires_at = null, attempts = 0
where id = 'cf9e2b94-94d6-43b0-99e2-87f69cb5763a';
```

## Nota su una diagnosi precedente sbagliata

In fase di analisi si era ipotizzato che il worker non fosse in esecuzione. **Era
falso.** Il servizio `import-worker` esiste in Coolify (id 19), il container
`import-worker-jort9hm5ny7nruhpn6fbtmwz` gira da 18 ore e ha processato il job
correttamente fino all'errore di estrazione. La confusione nasceva
dall'ispezione del solo container del backend, che effettivamente esegue unicamente
uvicorn: il worker è un servizio separato, come da `docs/IMPORT_WORKER.md`.

Resta vero un punto: il servizio worker in Coolify punta all'immagine
`1kx2w4ye7sd5jb9awemsq7yy:a0ca2dda...` mentre il backend usa
`...:40bc8b3a...`. Le due immagini dovrebbero essere allineate, altrimenti il worker
può divergere dal codice dell'API.
