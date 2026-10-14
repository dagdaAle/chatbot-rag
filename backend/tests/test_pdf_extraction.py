"""Document structure, table associations and ingestion rollback regressions."""
import asyncio
import io
import json
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from docling_core.types.doc import (
    BoundingBox, DocItemLabel, DoclingDocument, ProvenanceItem, Size, TableCell, TableData,
)

from app.core import documents, pdf_extraction


def provenance(page):
    return ProvenanceItem(page_no=page, bbox=BoundingBox(l=10, t=100, r=200, b=50), charspan=(0, 20))


def structured_fixture():
    doc = DoclingDocument(name="regolamento")
    for page in (1, 2, 3):
        doc.add_page(page_no=page, size=Size(width=600, height=800))
    doc.add_heading("Titolo I", level=1, prov=provenance(1))
    doc.add_heading("Articolo 1", level=2, prov=provenance(1))
    doc.add_text(label=DocItemLabel.TEXT, text="Requisito obbligatorio.", prov=provenance(1))
    doc.add_text(label=DocItemLabel.TEXT, text="Eccezione alla pagina seguente.", prov=provenance(2))
    doc.add_text(label=DocItemLabel.PAGE_FOOTER, text="Pagina due", prov=provenance(2))
    doc.add_heading("Articolo 2", level=2, prov=provenance(2))
    doc.add_text(label=DocItemLabel.TEXT, text="Una condizione diversa.", prov=provenance(2))
    cells = []
    for r, row in enumerate([
        ["Codice", "Prezzo EUR", "Unità"],
        ["001-A", "12,50", "kg"],
        ["001/B", "21,00", "pezzo"],
    ]):
        for c, text in enumerate(row):
            cells.append(TableCell(text=text, start_row_offset_idx=r, end_row_offset_idx=r + 1,
                                   start_col_offset_idx=c, end_col_offset_idx=c + 1, column_header=r == 0))
    doc.add_table(data=TableData(num_rows=3, num_cols=3, table_cells=cells), prov=provenance(3))
    return {"schema_version": 1, "extractor": "docling", "extractor_version": "test",
            "document": doc.export_to_dict(), "blocks": pdf_extraction.normalize_document(doc)}


def test_sections_keep_cross_page_conditions_and_provenance():
    structure = structured_fixture()
    chunks = pdf_extraction.chunk_structured_document(structure)
    first = chunks[0]
    assert first["section_path"] == ["Titolo I", "Articolo 1"]
    assert "Requisito obbligatorio" in first["text"]
    assert "Eccezione alla pagina seguente" in first["text"]
    assert (first["page_start"], first["page_end"]) == (1, 2)
    assert first["source_regions"][1]["page"] == 2
    assert first["source_regions"][0]["bbox"]["l"] == 10
    assert "condizione diversa" not in first["text"]
    assert all("Pagina due" not in c["text"] for c in chunks)
    # The persisted representation remains a valid, lossless Docling document.
    restored = DoclingDocument.model_validate(structure["document"])
    assert len(restored.tables) == 1


def test_split_tables_repeat_headers_without_detaching_prices():
    chunks = pdf_extraction.chunk_structured_document(structured_fixture(), chunk_size=80)
    tables = [c for c in chunks if c["content_kind"] == "table"]
    assert len(tables) == 2
    assert all("Codice | Prezzo EUR | Unità" in c["text"] for c in tables)
    assert "001-A | 12,50 | kg" in tables[0]["text"]
    assert "001/B | 21,00 | pezzo" in tables[1]["text"]
    assert [c["table_row_indices"] for c in tables] == [[1], [2]]
    assert all(c["page_start"] == 3 for c in tables)


def test_long_paragraph_preserves_all_words_and_section():
    structure = structured_fixture()
    block = structure["blocks"][2]
    block["text"] = " ".join(f"word{i}" for i in range(1000))
    structure["blocks"] = [block]
    chunks = pdf_extraction.chunk_structured_document(structure, chunk_size=500)
    joined = " ".join(c["text"] for c in chunks)
    assert all(f"word{i}" in joined.split() for i in range(1000))
    assert all(c["section_path"] == ["Titolo I", "Articolo 1"] for c in chunks)


def test_missing_provenance_is_not_fabricated():
    structure = structured_fixture()
    structure["blocks"][2]["source_regions"] = []
    structure["blocks"] = [structure["blocks"][2]]
    with pytest.raises(ValueError, match="senza pagina"):
        pdf_extraction.chunk_structured_document(structure)


def test_partial_conversion_never_indexes_or_falls_back(monkeypatch):
    from docling.datamodel.base_models import ConversionStatus
    monkeypatch.setattr(pdf_extraction, "_get_converter", lambda: SimpleNamespace(
        convert=lambda *a, **kw: SimpleNamespace(status=ConversionStatus.PARTIAL_SUCCESS)))
    with pytest.raises(ValueError, match="incompleta"):
        pdf_extraction.extract_structured_pdf(b"%PDF")
    assert not pdf_extraction._conversion_lock.locked()


def test_conversion_errors_release_lock(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("conversion failure")
    monkeypatch.setattr(pdf_extraction, "_get_converter", lambda: SimpleNamespace(convert=fail))
    with pytest.raises(RuntimeError, match="conversion failure"):
        pdf_extraction.extract_structured_pdf(b"%PDF")
    assert not pdf_extraction._conversion_lock.locked()


def test_points_embed_section_and_keep_structure_metadata(monkeypatch):
    structure = structured_fixture()
    captured = []
    monkeypatch.setattr(documents.settings, "pdf_extractor", "docling")
    monkeypatch.setattr(pdf_extraction, "extract_structured_pdf", lambda content: structure)
    monkeypatch.setattr(documents, "get_embeddings_batch", lambda texts: captured.extend(texts) or [[.1] * 3 for _ in texts])
    doc_id, points, extracted = documents.process_pdf_to_points(b"PDF", "test.pdf")
    assert extracted == structure
    assert points[0][2]["document_id"] == doc_id
    assert points[0][2]["source_regions"][0]["page"] == 1
    assert points[0][2]["extractor"] == "docling"
    assert captured[0].startswith("Titolo I > Articolo 1")


def test_incomplete_embeddings_are_rejected(monkeypatch):
    monkeypatch.setattr(documents.settings, "pdf_extractor", "docling")
    monkeypatch.setattr(pdf_extraction, "extract_structured_pdf", lambda content: structured_fixture())
    monkeypatch.setattr(documents, "get_embeddings_batch", lambda texts: [])
    with pytest.raises(ValueError, match="Embedding incompleti"):
        documents.process_pdf_to_points(b"PDF", "test.pdf")


def test_delete_document_and_knowledge_remove_extracted_data(monkeypatch, tmp_path):
    monkeypatch.setattr(documents, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(documents, "EXTRACTED_DIR", tmp_path / "extracted")
    kb, doc_id = str(uuid4()), str(uuid4())
    for _ in range(2):
        documents.save_pdf_to_disk(b"PDF", kb, doc_id)
        documents.save_document_structure(structured_fixture(), kb, doc_id)
        assert json.loads(documents.get_structure_path(kb, doc_id).read_text())["extractor"] == "docling"
        if _ == 0:
            documents.delete_pdf_from_disk(kb, doc_id)
        else:
            documents.delete_knowledge_pdfs(kb)
        assert not documents.get_upload_path(kb, doc_id).exists()
        assert not documents.get_structure_path(kb, doc_id).exists()


@pytest.mark.parametrize("fail_queue", [False, True])
def test_upload_persists_pending_pdf_and_cleans_up_on_queue_failure(monkeypatch, tmp_path, fail_queue):
    from app.api import documents as api
    from app.auth import User, request_user
    from fastapi import UploadFile
    monkeypatch.setattr(documents, "IMPORTS_DIR", tmp_path / "imports")
    kb = str(uuid4())
    monkeypatch.setattr(api, "get_knowledge", lambda kb: object())
    def rest(*args, **kwargs):
        if fail_queue:
            raise RuntimeError("queue unavailable")
        return [{**kwargs["body"], "status": "queued"}]
    monkeypatch.setattr(api, "rest", rest)
    upload = UploadFile(filename="test.pdf", file=io.BytesIO(b"PDF"))
    marker = request_user.set(User(str(uuid4()), "token", "admin"))
    try:
        result = asyncio.run(api.upload_documents(kb, [upload]))
    finally:
        request_user.reset(marker)
    if fail_queue:
        assert result["total_queued"] == 0
        assert result["total_errors"] == 1
        assert not list((tmp_path / "imports").rglob("*.pdf"))
    else:
        assert result["total_queued"] == 1
        assert result["jobs"][0]["status"] == "queued"
        assert list((tmp_path / "imports").rglob("*.pdf"))[0].read_bytes() == b"PDF"


@pytest.mark.skipif(os.getenv("RUN_DOCLING_INTEGRATION") != "1", reason="requires local models, reportlab and Tesseract ita+eng")
@pytest.mark.parametrize("scanned", [False, True])
def test_real_local_pdf_conversion(scanned):
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    from PIL import Image, ImageDraw, ImageFont
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream)
    if scanned:
        image = Image.new("RGB", (1600, 1200), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(os.environ.get("PDF_TEST_FONT", "/System/Library/Fonts/Supplemental/Arial.ttf"), 44)
        draw.text((100, 100), "Regolamento comunale", font=font, fill="black")
        draw.text((100, 200), "Il requisito obbligatorio riguarda la residenza.", font=font, fill="black")
        pdf.drawImage(ImageReader(image), 30, 250, width=540, height=405)
    else:
        pdf.setFont("Helvetica-Bold", 20)
        pdf.drawString(60, 760, "Regolamento comunale")
        pdf.setFont("Helvetica", 12)
        pdf.drawString(60, 700, "Il requisito obbligatorio riguarda la residenza.")
        pdf.showPage()
        pdf.drawString(60, 700, "Eccezione per i residenti nel Comune.")
    pdf.save()
    structure = pdf_extraction.extract_structured_pdf(stream.getvalue())
    chunks = pdf_extraction.chunk_structured_document(structure)
    text = " ".join(c["text"] for c in chunks).lower()
    assert "requisito obbligatorio" in text
    assert all(c["source_regions"] for c in chunks)
    assert all("bbox" in r for c in chunks for r in c["source_regions"])
    if not scanned:
        assert "eccezione" in text
        assert max(c["page_end"] for c in chunks) == 2


@pytest.mark.skipif(os.getenv("RUN_DOCLING_INTEGRATION") != "1", reason="requires local models and reportlab")
def test_real_local_pdf_table_conversion():
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
    from reportlab.lib import colors
    stream = io.BytesIO()
    table = Table([
        ["Codice", "Descrizione", "Prezzo EUR", "Unita"],
        ["001-A", "Prodotto primo", "12,50", "kg"],
        ["001/B", "Prodotto secondo", "21,00", "pezzo"],
    ], colWidths=[80, 160, 90, 70], rowHeights=35)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ]))
    SimpleDocTemplate(stream).build([table])
    structure = pdf_extraction.extract_structured_pdf(stream.getvalue())
    tables = [b for b in structure["blocks"] if b["kind"] == "table"]
    assert tables
    rows = [r["cells"] for t in tables for r in t["rows"]]
    assert ["001-A", "Prodotto primo", "12,50", "kg"] in rows
    assert ["001/B", "Prodotto secondo", "21,00", "pezzo"] in rows
