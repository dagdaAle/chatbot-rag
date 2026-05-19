"""Endpoint health e readiness."""
from fastapi import APIRouter, HTTPException

from app.core.qdrant_client import get_client

router = APIRouter()


@router.get("")
async def health_detailed() -> dict:
    """Health check dettagliato."""
    return {"status": "ok", "service": "chatbot-rag-api"}


@router.get("/qdrant")
async def health_qdrant() -> dict:
    """Verifica connettività a Qdrant."""
    try:
        client = get_client()
        collections = client.get_collections()
        return {
            "status": "ok",
            "qdrant": "connected",
            "collections_count": len(collections.collections),
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail={"qdrant": "unavailable", "error": str(e)})
