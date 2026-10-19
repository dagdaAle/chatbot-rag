# Analisi: spostare il worker di import PDF da CPU a GPU

**Data evento:** 19 ottobre 2026
**Macchina:** Ubuntu 24.04, Xeon W-2123 (8 thread), 64 GB RAM, RTX 3060 12 GB
**Ticket:** BUG-001 (`bug/BUG-001-docling-timeout-pdf-digitali.md`)

## Perché stiamo parlando di GPU

Non è un'idea astratta: nasce da un fallimento reale misurato stasera.

Il PDF `professional-it-it-2026-web.pdf` (listino Liebherr, 100 pagine, 6,8 MB,
376.013 caratteri di testo nativo) non riusciva a essere importato. Tre tentativi,
tre misure, in ordine cronologico.

### Tentativo 1 — configurazione originale

```
18:52:28  job reclamato, stage=extracting
18:52:29  tesseract --list-langs
18:55:41  Finished converting document document.pdf in 192.23 sec
          ValueError: Estrazione PDF incompleta: documento non indicizzato
```

Il converter aveva `do_ocr=True` forzato. Su un PDF che ha già il testo
selezionabile, Tesseract veniva invocato su ogni pagina inutilmente e falliva
**184 volte** con `Too few characters. Skipping this page`.

Timeout configurato: 180 s. Tempo impiegato: 192,23 s. Oltre il limite.

### Tentativo 2 — dopo il fix dell'OCR

Il commit `98e0e31` introduce `has_native_text()`: campiona 5 pagine con pypdf,
e se il testo è già selezionabile usa un converter senza OCR. Sul PDF in
questione il campione restituisce **8.556 caratteri su 5 pagine** contro una
soglia di 1.000, quindi l'OCR viene escluso.

```
19:27:02  job reclamato
19:27:12  Processing document document.pdf
          [nessuna chiamata a tesseract: 0 occorrenze nei log]
19:30:12  WARNING Document processing time (180.017s) exceeded timeout of 180.000s
19:30:28  Finished converting document document.pdf in 199.81 sec
          ValueError: Estrazione PDF incompleta: documento non indicizzato
```

L'OCR è stato eliminato con successo — da 184 chiamate a zero. **Ma il tempo è
sceso solo da 192 a 199 secondi**. Il costo non era l'OCR.

Il tempo residuo è tutto qui: layout detection (modello Transformers su ogni
pagina) e table structure (TableFormer). Su 100 pagine, in CPU, con
`num_threads=2` hardcoded.

Durante l'elaborazione: CPU al **380%**, RAM **3,9 GB**.

### Tentativo 3 — più thread e timeout più alto

`PDF_CONVERSION_TIMEOUT` 180 → 900, nuovo `PDF_CPU_THREADS=8` (prima era
letteralmente `num_threads=2` scritto nel codice, su una macchina da 8 thread).

Dopo il redeploy: CPU al **403%**, RAM **4,3 GB**. Il container usa 4 core
pieni invece di 2.

## Il dato che conta

```
$ docker exec import-worker-... python3 -c "import torch; print(torch.__version__, torch.cuda.is_available())"
torch 2.14.1+cpu cuda False
```

**La RTX 3060 da 12 GB non è mai stata usata.** L'immagine Docker installa
`torch torchvision --index-url https://download.pytorch.org/whl/cpu`, cioè
esplicitamente la build CPU.

Docling per layout detection e TableFormer usa modelli PyTorch. Sono esattamente
il tipo di carico per cui una GPU esiste: inferenza su molte immagini piccole,
in sequenza, con batch. Su 100 pagine questo si traduce in minuti di CPU che
diventerebbero secondi su CUDA.

## Da verificare prima di decidere (non ancora fatto)

Alcune cose vanno misurate, non ipotizzate:

1. **Tempo effettivo del tentativo 3.** Se con 8 thread e 900 s il PDF passa in
   ~120 s, il problema pratico è risolto e la GPU diventa un'ottimizzazione.
   Se resta sopra i 300 s, ogni listino pagherà quel prezzo e la GPU diventa
   necessaria.
2. **Benchmark Docling CPU vs CUDA affidabili.** Esistono dichiarazioni del
   progetto Docling su accelerazione GPU, ma vanno lette le condizioni (modello,
   batch size, tipo di documento). Nessun numero va copiato senza verifica.
3. **VRAM disponibile.** 12 GB sulla 3060, ma altri servizi sull'host (Ollama,
   Supabase) potrebbero contendere memoria. Docling carica layout model +
   TableFormer + eventuale OCR: da misurare.
4. **Immagine Docker.** La build CUDA di torch pesa sensibilmente più della CPU.
   Vanno confrontate le dimensioni reali prima di scegliere.

## Modifiche previste (bozza, non applicate)

### Dockerfile

Oggi:
```dockerfile
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

Dovrebbe diventare una build CUDA (base image con CUDA runtime, indice
`.../whl/cu121` o versione corrente), più `nvidia-container-toolkit` sull'host.

### pdf_extraction.py

Oggi:
```python
accelerator_options=AcceleratorOptions(
    device=AcceleratorDevice.CPU,
    num_threads=settings.pdf_cpu_threads,
)
```

Dovrebbe diventare configurabile:
```python
device=AcceleratorDevice.CUDA if settings.pdf_device == "cuda" else AcceleratorDevice.CPU
```
con fallback automatico a CPU se CUDA non è disponibile, così il codice resta
portabile su macchine senza GPU.

### docker-compose

Il servizio worker necessita di `deploy.resources.reservations.devices` per la
GPU (o `runtime: nvidia`), diversamente dalla parte API che non ne ha bisogno.

## Rischi

- **Immagine più grande**: build CUDA di torch è molto più pesante. Va misurato
  l'impatto su build e pull.
- **VRAM contesa**: Ollama gira sullo stesso host e usa la 3060. Due processi
  che chiedono VRAM possono portare a OOM. Serve un budget esplicito.
- **Complessità di deploy**: nvidia-container-toolkit, driver, compatibilità
  CUDA. Se si rompe, il worker non parte e gli import si fermano.
- **Rollback**: tenerlo semplice. `PDF_DEVICE=cpu` deve bastare a tornare
  indietro senza rebuild, altrimenti il rollback diventa un'operazione lunga.

## Verdetto

Sospeso fino alla misura del tentativo 3. La GPU è chiaramente la strada giusta
sul medio periodo — stiamo usando un quarto della macchina quando ne abbiamo una
intera disponibile — ma la priorità immediata è che i listini entrino. Prima si
verifica se 900 s + 8 thread bastano; poi si decide se il salto vale il lavoro.

Nessun numero di speedup è riportato qui di proposito: non ne ho misurato
nessuno, e inventarlo sarebbe peggio che non scriverlo.
