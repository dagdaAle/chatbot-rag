"""Endpoint upload, list, download e delete documenti per Knowledge Base."""
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from qdrant_client.models import PointStruct

from app.core.documents import (
    process_pdf_to_points,
    save_pdf_to_disk,
    delete_pdf_from_disk,
    get_upload_path,
)
from app.core.knowledge import get_knowledge, get_collection_name, update_documents_count
from app.core.qdrant_client import get_client, ensure_collection_for_kb

router = APIRouter(prefix="/api/knowledge", tags=["documents"])


@router.post("/{knowledge_id}/documents/upload")
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
    ensure_collection_for_kb(client, collection_name, recreate_if_wrong_size=True)

    results = []
    errors = []

    for file in files:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            errors.append({"filename": file.filename or "sconosciuto", "error": "Solo file PDF sono accettati"})
            continue

        content = await file.read()
        if not content:
            errors.append({"filename": file.filename, "error": "File vuoto"})
            continue

        filename = file.filename or "documento.pdf"
        try:
            doc_id, points = process_pdf_to_points(content, filename)
        except Exception as e:
            errors.append({"filename": filename, "error": f"Errore elaborazione: {e}"})
            continue

        if not points:
            errors.append({"filename": filename, "error": "Nessun testo estratto dal PDF"})
            continue

        # Salva il PDF originale su disco
        save_pdf_to_disk(content, knowledge_id, doc_id)

        # Upsert in batch da 100
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            qdrant_points = [
                PointStruct(id=pid, vector=vec, payload=payload)
                for pid, vec, payload in batch
            ]
            client.upsert(collection_name=collection_name, points=qdrant_points)

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
async def list_documents(knowledge_id: str) -> dict:
    """Elenco documenti di una Knowledge Base."""
    kb = get_knowledge(knowledge_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="Knowledge non trovata")

    collection_name = get_collection_name(knowledge_id)
    client = get_client()

    try:
        collections = client.get_collections().collections
        if not any(c.name == collection_name for c in collections):
            return {"documents": [], "total": 0}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Qdrant non disponibile: {e}")

    docs_by_id: dict[str, dict] = {}
    offset = None
    limit = 5000

    while True:
        records, offset = client.scroll(
            collection_name=collection_name,
            limit=limit,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for rec in records:
            payload = rec.payload or {}
            doc_id = payload.get("document_id")
            if not doc_id:
                continue
            if doc_id not in docs_by_id:
                docs_by_id[doc_id] = {
                    "document_id": doc_id,
                    "filename": payload.get("filename", ""),
                    "uploaded_at": payload.get("uploaded_at", ""),
                    "chunks_count": 0,
                }
            docs_by_id[doc_id]["chunks_count"] += 1
        if offset is None:
            break

    documents = list(docs_by_id.values())
    update_documents_count(knowledge_id, absolute=len(documents))
    return {"documents": documents, "total": len(documents)}


@router.get("/{knowledge_id}/documents/{document_id}/file")
async def download_document_file(knowledge_id: str, document_id: str) -> FileResponse:
    """Serve il file PDF originale di un documento."""
    kb = get_knowledge(knowledge_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="Knowledge non trovata")

    path = get_upload_path(knowledge_id, document_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File PDF non trovato su disco")

    return FileResponse(
        path=str(path),
        media_type="application/pdf",
        filename=f"{document_id}.pdf",
    )


@router.delete("/{knowledge_id}/documents/{document_id}")
async def delete_document(knowledge_id: str, document_id: str) -> dict:
    """Elimina un documento, i suoi chunk da Qdrant e il PDF dal disco."""
    kb = get_knowledge(knowledge_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="Knowledge non trovata")

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

    update_documents_count(knowledge_id, delta=-1)
    return {"document_id": document_id, "status": "deleted"}
