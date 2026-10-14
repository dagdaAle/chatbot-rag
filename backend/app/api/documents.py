"""PDF upload queue, status, download and deletion for knowledge bases."""
import logging
import uuid
from fastapi import Depends
from app.auth import require_kb_editor
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.core.documents import (
    save_import_pdf,
    delete_import_pdf,
    get_import_path,
    delete_pdf_from_disk,
    get_upload_path,
)
from app.core.knowledge import get_knowledge, get_collection_name
from app.core.qdrant_client import get_client
from app.core.supabase import rest, identifier

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/knowledge", tags=["documents"])


@router.post("/{knowledge_id}/documents/upload", dependencies=[Depends(require_kb_editor)])
async def upload_documents(
    knowledge_id: str,
    files: list[UploadFile] = File(...),
) -> dict:
    """Persist PDF bytes and enqueue imports; conversion happens in the worker."""
    kb = get_knowledge(knowledge_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="Knowledge non trovata")

    if not files:
        raise HTTPException(status_code=400, detail="Nessun file fornito")

    jobs = []
    errors = []

    for file in files:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            errors.append({"filename": file.filename or "sconosciuto", "error": "Solo file PDF sono accettati"})
            continue

        content = await file.read(20 * 1024 * 1024 + 1)
        if len(content) > 20 * 1024 * 1024:
            errors.append({"filename": file.filename, "error": "PDF troppo grande: massimo 20 MB"})
            continue
        if not content:
            errors.append({"filename": file.filename, "error": "File vuoto"})
            continue

        filename = file.filename or "documento.pdf"
        job_id = str(uuid.uuid4())
        created = None
        try:
            save_import_pdf(content, knowledge_id, job_id)
            try:
                created = rest("POST", "import_jobs", body={
                    "id": job_id, "knowledge_id": identifier(knowledge_id),
                    "filename": filename, "size_bytes": len(content),
                })
            finally:
                if created is None:
                    delete_import_pdf(knowledge_id, job_id)
            jobs.append(created[0])
        except Exception as exc:
            delete_import_pdf(knowledge_id, job_id)
            if isinstance(exc, HTTPException):
                raise
            errors.append({"filename": filename, "error": "Impossibile mettere il PDF in coda"})

    return {
        "jobs": jobs,
        "errors": errors,
        "total_queued": len(jobs),
        "total_errors": len(errors),
    }


@router.get("/{knowledge_id}/documents")
def list_documents(knowledge_id: str) -> dict:
    """Elenco documenti di una Knowledge Base."""
    kb = get_knowledge(knowledge_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="Knowledge non trovata")

    kb_id = identifier(knowledge_id)
    rows = rest('GET', 'documents', params={'knowledge_id': f'eq.{kb_id}', 'order':'uploaded_at.asc'})
    jobs = rest('GET', 'import_jobs', params={
        'knowledge_id': f'eq.{kb_id}', 'status': 'in.(queued,running,failed)',
        'order': 'status.desc,created_at.desc', 'limit': '50',
    })
    return {"documents": rows, "jobs": jobs, "total": len(rows)}


@router.post("/{knowledge_id}/imports/{job_id}/retry", dependencies=[Depends(require_kb_editor)])
def retry_import(knowledge_id: str, job_id: str) -> dict:
    kb_id, valid_job = identifier(knowledge_id), identifier(job_id)
    rows = rest("GET", "import_jobs", params={"id": f"eq.{valid_job}", "knowledge_id": f"eq.{kb_id}"})
    if not rows:
        raise HTTPException(404, "Importazione non trovata")
    if not get_import_path(kb_id, valid_job).exists():
        raise HTTPException(409, "Il PDF originale non è più disponibile per il nuovo tentativo")
    changed = rest("POST", "rpc/chatbot_retry_import_job", body={"p_job": valid_job})
    if changed is not True:
        raise HTTPException(409, "Solo un’importazione fallita può essere riprovata")
    return {"job_id": valid_job, "status": "queued"}


@router.get("/{knowledge_id}/documents/{document_id}/file")
def download_document_file(knowledge_id: str, document_id: str) -> FileResponse:
    """Serve il file PDF originale di un documento."""
    kb = get_knowledge(knowledge_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="Knowledge non trovata")

    if not rest("GET", "documents", params={"document_id": f"eq.{identifier(document_id)}", "knowledge_id": f"eq.{identifier(knowledge_id)}"}):
        raise HTTPException(404, "Documento non trovato")
    path = get_upload_path(knowledge_id, document_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File PDF non trovato su disco")

    return FileResponse(
        path=str(path),
        media_type="application/pdf",
        filename=f"{document_id}.pdf",
    )


@router.delete("/{knowledge_id}/documents/{document_id}", dependencies=[Depends(require_kb_editor)])
def delete_document(knowledge_id: str, document_id: str) -> dict:
    """Elimina un documento, i suoi chunk da Qdrant e il PDF dal disco."""
    kb = get_knowledge(knowledge_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="Knowledge non trovata")

    if not rest("GET", "documents", params={"document_id": f"eq.{identifier(document_id)}", "knowledge_id": f"eq.{identifier(knowledge_id)}"}):
        raise HTTPException(404, "Documento non trovato")
    from qdrant_client import models

    collection_name = get_collection_name(knowledge_id)
    client = get_client()

    try:
        client.delete(
            collection_name=collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=document_id),
                        ),
                    ],
                )
            ),
        )
    except Exception as exc:
        logger.exception('Qdrant delete failed for document %s', document_id)
        raise HTTPException(status_code=502, detail="Indice vettoriale non raggiungibile") from exc

    # Elimina il PDF dal disco
    from app.core.price_lists import delete_price_document
    delete_price_document(document_id)
    delete_pdf_from_disk(knowledge_id, document_id)

    rest("DELETE", "documents", params={"document_id": f"eq.{identifier(document_id)}", "knowledge_id": f"eq.{identifier(knowledge_id)}"})
    return {"document_id": document_id, "status": "deleted"}
