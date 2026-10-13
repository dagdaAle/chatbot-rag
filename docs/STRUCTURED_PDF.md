# Structured PDF ingestion

New uploads use **Docling 2.138.0**, locally on CPU, with layout/table recognition,
heading hierarchy recovery and Tesseract OCR (`ita`, `eng`). The existing chat,
embedding provider, KB authorization and PDF download routes remain in use.

## Data flow

1. Convert the uploaded PDF using the standard local Docling pipeline.
2. Reject failed/partial conversions rather than indexing incomplete content.
3. Preserve the full Docling JSON and normalize text, headings, tables and source regions.
4. Build chunks within detected sections; keep table rows together and repeat column
   headers in each table chunk. Long paragraphs retain their detected section path.
5. Embed the contextualized chunks through the existing embedding provider.
6. Save the original PDF, extracted JSON and vector points, then publish the document
   row in Supabase. Compensate failed publication by removing points and files.

The saved JSON retains cell spans and provenance. The search representation repeats
merged cell values to retain their association with rows/columns. No prices or missing
cells are inferred. Tables without detected headers remain headerless.

Paths under the existing persistent `DATA_DIR`:

- `uploads/<knowledge_id>/<document_id>.pdf`: original PDF.
- `extracted/<knowledge_id>/<document_id>.json`: versioned extracted representation.
- Qdrant payload: section path/references, source element references, page ranges,
  source bounding boxes, extractor/version, content kind and table row indices.

Document and KB deletion remove extracted JSON as well as original PDFs. Include
`extracted/` in backups together with uploads, Qdrant and Supabase metadata.

Chat sources now include `section_path`, `content_kind` and `source_regions`, in
addition to existing page references. Bounding boxes identify **source elements**;
they are not exact character-level highlights for a split chunk. The current PDF
reader continues to use its text/page highlighting. Coordinate-based highlighting,
including scanned pages, is a separate UI change.

## Configuration and deployment

```dotenv
PDF_EXTRACTOR=docling
PDF_MAX_PAGES=300
PDF_CONVERSION_TIMEOUT=180
DOCLING_ARTIFACTS_PATH=/opt/docling-models
```

The Dockerfiles install Tesseract Italian/English data, CPU PyTorch, and download
layout/table model artifacts during the build. `HF_HUB_OFFLINE=1` prevents model
downloads at runtime. Builds need network access and have a larger image than before.
PDF contents are processed locally; embeddings/chat still use their separately
configured providers. This feature does **not** integrate the Anonymizer.

For a local Python installation, install the system Tesseract executable and both
language packs, install `backend/requirements.txt`, and run:

```sh
DOCLING_ARTIFACTS_PATH=/absolute/model-directory python backend/scripts/download_pdf_models.py
```

Set the same artifacts path when starting the backend. If no path is set, Docling
uses its normal cache and may download model artifacts on first use.

`PDF_EXTRACTOR=pypdf` explicitly restores the legacy extraction path. There is no
automatic fallback on Docling errors. Existing vector collections and documents are
not migrated or deleted; they retain their previous extraction until a separately
planned reindex. No SQL migration or embedding-dimension change is required.

## Limits and verification

Conversion is serialized in the dedicated import worker. Upload requests only persist
the source PDF and enqueue work. Queue state, retry and deployment requirements are
documented in [IMPORT_WORKER.md](IMPORT_WORKER.md). The configured timeout applies to
Docling conversion, not model initialization or embedding calls.

Chunks target 2,000 characters; individual table rows remain atomic and can exceed
that target. Any chunk over 12,000 characters is rejected rather than silently
truncated. Extraction quality and the suitability of these limits must be checked
against real regulations, attachments, scanned documents and price lists. Detected
headings do not establish legal semantics, document validity or cross-references.

Automated checks cover real Docling data types, cross-page conditions, section
boundaries, table header/code/price associations, source coordinates, long passages,
partial conversion failures, embedding completeness, file deletion and publication
rollback. Optional integration checks convert real generated PDFs and Italian scans
using local model artifacts, without external embedding/chat calls.

```sh
PYTHONPATH=backend python -m pytest backend/tests -q
# Also requires reportlab, models, Tesseract ita+eng and a TrueType font:
RUN_DOCLING_INTEGRATION=1 PDF_TEST_FONT=/path/to/font.ttf \
  PYTHONPATH=backend python -m pytest backend/tests/test_pdf_extraction.py -q
```

The extracted table grid and provenance also feed the optional structured price index
described in [STRUCTURED_PRICES.md](STRUCTURED_PRICES.md).
