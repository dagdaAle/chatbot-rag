"""Estrazione testo da PDF, chunking e preparazione punti per Qdrant."""
import io
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from app.config import DATA_DIR, settings

from pypdf import PdfReader

from app.core.embeddings import get_embeddings_batch
from app.core.lexical import LEXICAL_INDEX_VERSION, hybrid_vector

CHUNK_SIZE = 2000  # chunk più grandi per più contesto
CHUNK_OVERLAP = 250

# Directory base per salvare i PDF originali
UPLOADS_DIR = DATA_DIR / "uploads"
EXTRACTED_DIR = DATA_DIR / "extracted"
IMPORTS_DIR = DATA_DIR / "imports"


def get_structure_path(knowledge_id: str, document_id: str) -> Path:
    from app.core.supabase import identifier
    return EXTRACTED_DIR / identifier(knowledge_id) / f"{identifier(document_id)}.json"


def save_document_structure(structure: dict, knowledge_id: str, document_id: str) -> None:
    from app.core.storage import write_json
    write_json(get_structure_path(knowledge_id, document_id), structure)


def get_import_path(knowledge_id: str, job_id: str) -> Path:
    from app.core.supabase import identifier
    return IMPORTS_DIR / identifier(knowledge_id) / f"{identifier(job_id)}.pdf"


def save_import_pdf(content: bytes, knowledge_id: str, job_id: str) -> Path:
    path = get_import_path(knowledge_id, job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, pending = tempfile.mkstemp(dir=path.parent, prefix=".pending-", suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, path)
    finally:
        if os.path.exists(pending):
            os.unlink(pending)
    return path


def delete_import_pdf(knowledge_id: str, job_id: str) -> None:
    get_import_path(knowledge_id, job_id).unlink(missing_ok=True)


def get_upload_path(knowledge_id: str, document_id: str) -> Path:
    """Restituisce il path su disco per un PDF caricato."""
    from app.core.supabase import identifier
    return UPLOADS_DIR / identifier(knowledge_id) / f"{identifier(document_id)}.pdf"


def save_pdf_to_disk(content: bytes, knowledge_id: str, document_id: str) -> Path:
    """Salva il PDF originale su disco e restituisce il path."""
    path = get_upload_path(knowledge_id, document_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def delete_pdf_from_disk(knowledge_id: str, document_id: str) -> None:
    """Elimina il PDF originale dal disco."""
    for path in (get_upload_path(knowledge_id, document_id), get_structure_path(knowledge_id, document_id)):
        path.unlink(missing_ok=True)


def delete_knowledge_pdfs(knowledge_id: str) -> None:
    """Elimina tutti i PDF di una knowledge dal disco."""
    from app.core.supabase import identifier
    import shutil
    for root in (UPLOADS_DIR, EXTRACTED_DIR, IMPORTS_DIR):
        folder = root / identifier(knowledge_id)
        if folder.exists():
            shutil.rmtree(folder)


def extract_text_by_page(content: bytes) -> list[str]:
    """Estrae il testo da un PDF, una stringa per pagina."""
    reader = PdfReader(io.BytesIO(content))
    pages: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        pages.append(text)
    return pages


def chunk_text_with_pages(
    pages: list[str],
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[dict]:
    """Divide il testo (pagina per pagina) in chunk con overlap e chunking semantico.

    Ogni chunk restituisce: {"text": ..., "page_start": ..., "page_end": ...}
    """
    if not pages:
        return []

    # Costruisci un unico testo annotato con offset pagina
    # Usiamo un approccio: per ogni pagina salviamo (offset_start, offset_end, page_num)
    full_text = ""
    page_ranges: list[tuple[int, int, int]] = []  # (start, end, page_number 1-based)

    for i, page_text in enumerate(pages):
        cleaned = page_text.replace("\r\n", "\n")
        start = len(full_text)
        full_text += cleaned
        end = len(full_text)
        page_ranges.append((start, end, i + 1))
        if i < len(pages) - 1:
            full_text += "\n\n"  # separatore pagine

    if not full_text.strip():
        return []

    chunks: list[dict] = []
    start = 0
    while start < len(full_text):
        end = start + chunk_size

        # Semantic chunking: trova il miglior punto di divisione
        if end < len(full_text):
            # Cerca la fine di un paragrafo (doppio newline)
            paragraph_end = full_text.rfind('\n\n', start, min(end + 200, len(full_text)))
            if paragraph_end > start + overlap:
                end = paragraph_end + 2
            else:
                # Cerca la fine di una frase (. ! ?)
                sentence_end = max(
                    full_text.rfind('. ', start, min(end + 100, len(full_text))),
                    full_text.rfind('! ', start, min(end + 100, len(full_text))),
                    full_text.rfind('? ', start, min(end + 100, len(full_text)))
                )
                if sentence_end > start + overlap:
                    end = sentence_end + 2
                else:
                    # Cerca uno spazio per evitare di spezzare parole
                    space_pos = full_text.rfind(' ', start, min(end + 50, len(full_text)))
                    if space_pos > start + overlap:
                        end = space_pos

        chunk_text = full_text[start:end]
        if chunk_text.strip():
            # Determina pagine coinvolte
            page_start = _offset_to_page(start, page_ranges)
            page_end = _offset_to_page(min(end, len(full_text)) - 1, page_ranges)
            chunks.append({
                "text": chunk_text.strip(),
                "page_start": page_start,
                "page_end": page_end,
            })
        if end >= len(full_text):
            break
        start = max(start + 1, end - overlap)

    return chunks


def _offset_to_page(offset: int, page_ranges: list[tuple[int, int, int]]) -> int:
    """Dato un offset nel testo completo, restituisce il numero di pagina (1-based)."""
    for (ps, pe, page_num) in page_ranges:
        if ps <= offset < pe:
            return page_num
    # Fallback: ultima pagina
    return page_ranges[-1][2] if page_ranges else 1


def process_pdf_to_points(
    content: bytes,
    filename: str,
    progress=None,
    document_id: str | None = None,
) -> tuple[str, list[tuple[str, dict[str, object], dict]], dict]:
    """
    Restituisce document_id, punti e struttura da persistere con il PDF originale.
    I PDF già indicizzati restano leggibili senza migrazioni.
    """
    doc_id = document_id or str(uuid.uuid4())
    uploaded_at = datetime.now(timezone.utc).isoformat()

    if progress:
        progress("extracting", 10)
    if settings.pdf_extractor == "docling":
        from app.core.pdf_extraction import extract_structured_pdf, chunk_structured_document
        structure = extract_structured_pdf(content)
        chunks = chunk_structured_document(structure)
    else:
        from importlib.metadata import version
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        if len(reader.pages) > settings.pdf_max_pages:
            raise ValueError(f"PDF troppo lungo: massimo {settings.pdf_max_pages} pagine")
        # The explicitly selected legacy mode must not hide page extraction errors.
        pages = [page.extract_text() or "" for page in reader.pages]
        chunks = chunk_text_with_pages(pages)
        structure = {"schema_version": 1, "extractor": "pypdf",
                     "extractor_version": version("pypdf"), "pages": pages}

    if not chunks:
        return doc_id, [], structure

    for chunk in chunks:
        chunk.setdefault("extractor", structure["extractor"])
        chunk.setdefault("extractor_version", structure["extractor_version"])
        chunk.setdefault("extraction_schema_version", structure["schema_version"])

    # Genera embedding per tutti i chunk
    if progress:
        progress("embedding", 55, structure)
    texts = [c["text"] for c in chunks]
    embeddings = get_embeddings_batch(texts)
    if len(embeddings) != len(chunks):
        raise ValueError("Embedding incompleti: documento non indicizzato.")
    if progress:
        progress("indexing", 78, structure, len(chunks))

    points = []
    for i, (chunk, vector) in enumerate(zip(chunks, embeddings)):
        point_id = str(uuid.uuid4())
        payload = {
            **chunk,
            "document_id": doc_id,
            "filename": filename,
            "uploaded_at": uploaded_at,
            "chunk_index": i,
            "text": chunk["text"],
            "page_start": chunk["page_start"],
            "page_end": chunk["page_end"],
            "lexical_index_version": LEXICAL_INDEX_VERSION,
        }
        points.append((point_id, hybrid_vector(vector, chunk["text"]), payload))
    return doc_id, points, structure
