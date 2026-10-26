"""Local PDF conversion and structure-aware chunks with traceable provenance."""
import io
import logging
from importlib.metadata import version
from threading import Lock

from app.config import settings

logger = logging.getLogger(__name__)
_conversion_lock = Lock()
_converter = None
_converter_ocr = None
SCHEMA_VERSION = 1

_OCR_SAMPLE_PAGES = 5
_OCR_MIN_CHARS_PER_PAGE = 200


def has_native_text(content: bytes) -> bool:
    """True when the PDF already carries selectable text, so OCR would be wasted work.

    Digitally generated PDFs (catalogues, price lists) embed their text: running
    Tesseract over every page costs hundreds of seconds and can push a long document
    past ``pdf_conversion_timeout``, which turns a perfectly readable file into a
    failed import. Sampling a few pages is enough to tell the two cases apart.
    """
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(content))
    except Exception:  # malformed or encrypted: let Docling report the real error
        return False
    pages = min(_OCR_SAMPLE_PAGES, len(reader.pages))
    if pages == 0:
        return False
    chars = 0
    for index in range(pages):
        try:
            chars += len((reader.pages[index].extract_text() or "").strip())
        except Exception:
            return False
    return chars >= _OCR_MIN_CHARS_PER_PAGE * pages


def _accelerator_device():
    """CUDA only when asked for and actually usable, so PDF_DEVICE=cuda never breaks a CPU host."""
    from docling.datamodel.accelerator_options import AcceleratorDevice

    if settings.pdf_device == "cuda":
        try:
            import torch

            if torch.cuda.is_available():
                return AcceleratorDevice.CUDA
        except Exception:
            pass
        logger.warning("PDF_DEVICE=cuda but CUDA is not available: falling back to CPU")
    return AcceleratorDevice.CPU


def _build_converter(*, do_ocr: bool):
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TesseractCliOcrOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions(
        do_ocr=do_ocr,
        do_table_structure=True,
        enable_remote_services=False,
        document_timeout=settings.pdf_conversion_timeout,
        accelerator_options=AcceleratorOptions(
            device=_accelerator_device(), num_threads=settings.pdf_cpu_threads
        ),
    )
    if do_ocr:
        options.ocr_options = TesseractCliOcrOptions(lang=["ita", "eng"])
    if settings.docling_artifacts_path:
        options.artifacts_path = settings.docling_artifacts_path
    options.heading_hierarchy_options.enabled = True
    return DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)},
    )


def _get_converter(*, do_ocr: bool):
    global _converter, _converter_ocr
    if do_ocr:
        if _converter_ocr is None:
            _converter_ocr = _build_converter(do_ocr=True)
        return _converter_ocr
    if _converter is None:
        _converter = _build_converter(do_ocr=False)
    return _converter


def extract_structured_pdf(content: bytes) -> dict:
    """Reject partial conversions; never silently fall back to flattened text."""
    from docling.datamodel.base_models import ConversionStatus, DocumentStream

    if not _conversion_lock.acquire(timeout=5):
        raise ValueError("Un PDF è già in elaborazione. Riprova fra poco.")
    try:
        needs_ocr = not has_native_text(content)
        result = _get_converter(do_ocr=needs_ocr).convert(
            DocumentStream(name="document.pdf", stream=io.BytesIO(content)),
            raises_on_error=True,
            max_num_pages=settings.pdf_max_pages,
            max_file_size=20 * 1024 * 1024,
        )
        if result.status != ConversionStatus.SUCCESS:
            raise ValueError("Estrazione PDF incompleta: documento non indicizzato.")
        document = result.document
        return {
            "schema_version": SCHEMA_VERSION,
            "extractor": "docling",
            "extractor_version": version("docling"),
            "ocr_applied": needs_ocr,
            "document": document.export_to_dict(),
            "blocks": normalize_document(document),
        }
    finally:
        _conversion_lock.release()


def _regions(item) -> list[dict]:
    regions = []
    for prov in item.prov:
        region = {"item_ref": item.self_ref, "page": prov.page_no}
        if prov.bbox is not None:
            region["bbox"] = prov.bbox.model_dump(mode="json")
        regions.append(region)
    return regions


def _table_rows(item) -> list[dict]:
    """Keep spans in the source JSON; repeat merged cell text in the search view."""
    data = item.data
    grid = [[""] * data.num_cols for _ in range(data.num_rows)]
    header_rows = set()
    for cell in data.table_cells:
        for row in range(cell.start_row_offset_idx, cell.end_row_offset_idx):
            for col in range(cell.start_col_offset_idx, cell.end_col_offset_idx):
                if 0 <= row < data.num_rows and 0 <= col < data.num_cols:
                    grid[row][col] = cell.text.strip()
            if cell.column_header:
                header_rows.add(row)
    return [
        {"row_index": index, "cells": cells, "is_header": index in header_rows}
        for index, cells in enumerate(grid) if any(cells)
    ]


def normalize_document(document) -> list[dict]:
    blocks = []
    headings = []
    for item, _depth in document.iterate_items():
        label = str(getattr(item.label, "value", item.label))
        if label in {"page_header", "page_footer", "picture"}:
            continue
        text = getattr(item, "text", "").strip()
        if label in {"title", "section_header"}:
            level = max(1, getattr(item, "level", 1))
            while headings and headings[-1]["level"] >= level:
                headings.pop()
            headings.append({"text": text, "ref": item.self_ref, "level": level})
        if label != "table" and not text:
            continue
        block = {
            "id": item.self_ref,
            "kind": label,
            "text": text,
            "section_path": [h["text"] for h in headings],
            "section_refs": [h["ref"] for h in headings],
            "source_regions": _regions(item),
        }
        if label == "table":
            block["rows"] = _table_rows(item)
        blocks.append(block)
    return blocks


def _markdown_row(cells: list[str]) -> str:
    return "| " + " | ".join(c.replace("|", "\\|").replace("\n", " ") for c in cells) + " |"


def chunk_structured_document(structure: dict, chunk_size: int = 2000) -> list[dict]:
    """Never merge sections or split table rows away from their column headers.

    Coordinates refer to source elements, not exact character-level highlights.
    Detected heading levels are used as supplied, without inventing legal hierarchy.
    """
    from app.core.documents import chunk_text_with_pages

    chunks = []
    pending = None

    def emit(chunk):
        if chunk is None:
            return
        if len(chunk["text"]) > 12000:
            raise ValueError("Elemento PDF troppo lungo: controllare intestazioni o righe della tabella.")
        pages = [r["page"] for r in chunk["source_regions"]]
        if not pages:
            raise ValueError("Passaggio senza pagina di origine: documento non indicizzato.")
        chunks.append({
            **chunk,
            "page_start": min(pages), "page_end": max(pages),
            "extractor": structure["extractor"],
            "extractor_version": structure["extractor_version"],
            "extraction_schema_version": structure["schema_version"],
        })

    for block in structure["blocks"]:
        if block["kind"] in {"title", "section_header"}:
            emit(pending)
            pending = None
            continue
        prefix = " > ".join(block["section_path"])
        prefix = prefix + "\n\n" if prefix else ""
        base = {
            "section_path": block["section_path"], "section_refs": block["section_refs"],
            "source_regions": block["source_regions"], "block_ids": [block["id"]],
            "content_kind": "table" if block["kind"] == "table" else "text",
        }
        if block["kind"] == "table":
            emit(pending)
            pending = None
            headers = [r for r in block["rows"] if r["is_header"]]
            body = [r for r in block["rows"] if not r["is_header"]]
            header_text = "\n".join(_markdown_row(r["cells"]) for r in headers)
            table_prefix = prefix + (header_text + "\n" if header_text else "")
            batch = []

            def emit_rows(rows):
                if rows:
                    emit({**base, "text": table_prefix + "\n".join(_markdown_row(r["cells"]) for r in rows),
                          "table_ref": block["id"], "table_row_indices": [r["row_index"] for r in rows]})

            for row in body:
                if batch and len(table_prefix) + sum(len(_markdown_row(r["cells"])) + 1 for r in batch + [row]) > chunk_size:
                    emit_rows(batch)
                    batch = []
                batch.append(row)
            emit_rows(batch)
            if headers and not body:
                emit({**base, "text": table_prefix.strip(), "table_ref": block["id"], "table_row_indices": []})
            continue

        if pending and pending["section_refs"] == base["section_refs"] and len(pending["text"]) + len(block["text"]) + 2 <= chunk_size:
            pending["text"] += "\n\n" + block["text"]
            pending["source_regions"] = pending["source_regions"] + base["source_regions"]
            pending["block_ids"] += base["block_ids"]
            continue
        emit(pending)
        pending = None
        budget = max(300, chunk_size - len(prefix))
        pieces = chunk_text_with_pages([block["text"]], chunk_size=budget, overlap=min(200, budget // 4))
        for piece in pieces[:-1]:
            emit({**base, "text": prefix + piece["text"]})
        if pieces:
            pending = {**base, "text": prefix + pieces[-1]["text"]}
    emit(pending)
    return chunks
