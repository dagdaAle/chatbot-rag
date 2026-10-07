"""Endpoint CRUD per Knowledge Base."""
from fastapi import Depends
from app.auth import require_admin
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from app.core.knowledge import (
    create_knowledge,
    delete_knowledge,
    get_knowledge,
    list_knowledges,
)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


class KnowledgeCreate(BaseModel):
    """Richiesta creazione knowledge."""
    name: str
    description: str = ""


class KnowledgeResponse(BaseModel):
    """Risposta singola knowledge."""
    id: str
    name: str
    description: str
    created_at: str
    documents_count: int
    can_manage: bool = False


class KnowledgeListResponse(BaseModel):
    """Risposta lista knowledge."""
    knowledges: list[KnowledgeResponse]
    total: int


@router.get("", response_model=KnowledgeListResponse)
def list_all_knowledges() -> KnowledgeListResponse:
    """Restituisce tutte le Knowledge Base."""
    try:
        kbs = list_knowledges()
        items = [
            KnowledgeResponse(
                id=kb.id,
                name=kb.name,
                description=kb.description,
                created_at=kb.created_at,
                documents_count=kb.documents_count,
                can_manage=kb.can_manage,
            )
            for kb in kbs
        ]
        return KnowledgeListResponse(knowledges=items, total=len(items))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=KnowledgeResponse, status_code=201, dependencies=[Depends(require_admin)])
def create_new_knowledge(body: KnowledgeCreate) -> KnowledgeResponse:
    """Crea una nuova Knowledge Base."""
    if not body.name or not body.name.strip():
        raise HTTPException(status_code=400, detail="Il nome è obbligatorio")
    try:
        kb = create_knowledge(body.name.strip(), body.description.strip())
        return KnowledgeResponse(
            id=kb.id,
            name=kb.name,
            description=kb.description,
            created_at=kb.created_at,
            documents_count=kb.documents_count,
                can_manage=kb.can_manage,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{knowledge_id}", response_model=KnowledgeResponse)
def get_single_knowledge(knowledge_id: str) -> KnowledgeResponse:
    """Restituisce una singola Knowledge Base."""
    kb = get_knowledge(knowledge_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="Knowledge non trovata")
    return KnowledgeResponse(
        id=kb.id,
        name=kb.name,
        description=kb.description,
        created_at=kb.created_at,
        documents_count=kb.documents_count,
                can_manage=kb.can_manage,
    )


@router.delete("/{knowledge_id}", dependencies=[Depends(require_admin)])
def delete_single_knowledge(knowledge_id: str) -> dict:
    """Elimina una Knowledge Base e tutti i suoi documenti."""
    success = delete_knowledge(knowledge_id)
    if not success:
        raise HTTPException(status_code=404, detail="Knowledge non trovata")
    return {"id": knowledge_id, "status": "deleted"}

