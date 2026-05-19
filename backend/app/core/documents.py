"""Estrazione testo da PDF, chunking e preparazione punti per Qdrant."""
import io
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader

from app.core.embeddings import get_embeddings_batch

CHUNK_SIZE = 1000  # chunk più grandi per più contesto
CHUNK_OVERLAP = 150

# Directory base per salvare i PDF originali
UPLOADS_DIR = Path(__file__).parent.parent.parent / "data" / "uploads"


def get_upload_path(knowledge_id: str, document_id: str) -> Path:
    """Restituisce il path su disco per un PDF caricato."""
    return UPLOADS_DIR / knowledge_id / f"{document_id}.pdf"


def save_pdf_to_disk(content: bytes, knowledge_id: str, document_id: str) -> Path:
    """Salva il PDF originale su disco e restituisce il path."""
    path = get_upload_path(knowledge_id, document_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def delete_pdf_from_disk(knowledge_id: str, document_id: str) -> None:
    """Elimina il PDF originale dal disco."""
    path = get_upload_path(knowledge_id, document_id)
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def delete_knowledge_pdfs(knowledge_id: str) -> None:
    """Elimina tutti i PDF di una knowledge dal disco."""
    folder = UPLOADS_DIR / knowledge_id
    if folder.exists():
        import shutil
        try:
            shutil.rmtree(folder)
        except Exception:
            pass


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
    """Divide il testo (pagina per pagina) in chunk con overlap.

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

    full_text = full_text.strip()
    if not full_text:
        return []

    chunks: list[dict] = []
    start = 0
    while start < len(full_text):
        end = start + chunk_size
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
        start = end - overlap
        if start >= len(full_text):
            break

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
) -> tuple[str, list[tuple[str, list[float], dict]]]:
    """
    Processa un PDF e restituisce (document_id, lista di (id, vector, payload)).
    Ogni chunk contiene anche page_start e page_end.
    """
    doc_id = str(uuid.uuid4())
    uploaded_at = datetime.now(timezone.utc).isoformat()

    pages = extract_text_by_page(content)
    chunks = chunk_text_with_pages(pages)

    if not chunks:
        return doc_id, []

    # Genera embedding per tutti i chunk
    texts = [c["text"] for c in chunks]
    embeddings = get_embeddings_batch(texts)

    points = []
    for i, (chunk, vector) in enumerate(zip(chunks, embeddings)):
        point_id = str(uuid.uuid4())
        payload = {
            "document_id": doc_id,
            "filename": filename,
            "uploaded_at": uploaded_at,
            "chunk_index": i,
            "text": chunk["text"][:2000],
            "page_start": chunk["page_start"],
            "page_end": chunk["page_end"],
        }
        points.append((point_id, vector, payload))
    return doc_id, points
