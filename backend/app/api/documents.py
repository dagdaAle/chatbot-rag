"""Endpoint upload, list, download e delete documenti per Knowledge Base."""
from fastapi import Depends
from app.auth import require_admin
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from qdrant_client.models import PointStruct

from app.core.documents import (
    process_pdf_to_points,
    save_pdf_to_disk,
    delete_pdf_from_disk,
    get_upload_path,
)
from app.core.knowledge import get_knowledge, get_collection_name, update_documents_count
from app.core.qdrant_client import get_client, ensure_collection_for_kb
from app.core.supabase import rest, identifier

router = APIRouter(prefix="/api/knowledge", tags=["documents"])


@router.post("/{knowledge_id}/documents/upload", dependencies=[Depends(require_admin)])
async def upload_documents(
    knowledge_id: str,
    files: list[UploadFile] = File(...),
) -> dict:
    """Carica uno o più PDF in una Knowledge Base."""
    kb = get_knowledge(knowledge_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="Knowledge non trovata")

    if not files:
        raise HTTPException(status_code=400, detail="Nessun file fornito")

    collection_name = get_collection_name(knowledge_id)
    client = get_client()
    try:
        ensure_collection_for_kb(client, collection_name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    results = []
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
        try:
            doc_id, points = await run_in_threadpool(process_pdf_to_points, content, filename)
        except Exception as e:
            errors.append({"filename": filename, "error": f"Errore elaborazione: {e}"})
            continue

        if not points:
            errors.append({"filename": filename, "error": "Nessun testo estratto dal PDF"})
            continue

        # Compensate partial indexing failures; never publish an incomplete document row.
        try:
            await run_in_threadpool(save_pdf_to_disk, content, knowledge_id, doc_id)
            for i in range(0, len(points), 100):
                batch = [PointStruct(id=pid, vector=vec, payload=payload) for pid, vec, payload in points[i:i + 100]]
                await run_in_threadpool(client.upsert, collection_name=collection_name, points=batch)
            await run_in_threadpool(rest, 'POST', 'documents', body={
                'document_id': doc_id, 'knowledge_id': identifier(knowledge_id),
                'filename': filename, 'chunks_count': len(points)})
        except Exception:
            from qdrant_client import models
            await run_in_threadpool(client.delete, collection_name=collection_name,
                points_selector=models.FilterSelector(filter=models.Filter(must=[models.FieldCondition(
                    key='document_id', match=models.MatchValue(value=doc_id))])))
            delete_pdf_from_disk(knowledge_id, doc_id)
            raise

        results.append({
            "document_id": doc_id,
            "filename": filename,
            "chunks_count": len(points),
            "status": "uploaded",
        })

    # Aggiorna conteggio documenti nella knowledge
    if results:
        update_documents_count(knowledge_id, delta=len(results))

    return {
        "uploaded": results,
        "errors": errors,
        "total_uploaded": len(results),
        "total_errors": len(errors),
    }


@router.get("/{knowledge_id}/documents")
def list_documents(knowledge_id: str) -> dict:
    """Elenco documenti di una Knowledge Base."""
    kb = get_knowledge(knowledge_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="Knowledge non trovata")

    rows = rest('GET', 'documents', params={'knowledge_id': f'eq.{identifier(knowledge_id)}', 'order':'uploaded_at.asc'})
    return {"documents": rows, "total": len(rows)}


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


@router.delete("/{knowledge_id}/documents/{document_id}", dependencies=[Depends(require_admin)])
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Elimina il PDF dal disco
    delete_pdf_from_disk(knowledge_id, document_id)

    rest("DELETE", "documents", params={"document_id": f"eq.{identifier(document_id)}", "knowledge_id": f"eq.{identifier(knowledge_id)}"})
    return {"document_id": document_id, "status": "deleted"}
