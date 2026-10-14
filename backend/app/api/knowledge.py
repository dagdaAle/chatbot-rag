"""Endpoint CRUD e condivisione per Knowledge Base."""
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import require_creator, require_kb_owner, request_user
from app.core.knowledge import (
    Knowledge, create_knowledge, delete_knowledge, get_knowledge, list_knowledges,
    list_members, save_access, update_knowledge,
)
from app.core.supabase import rest

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])
Visibility = Literal['private', 'organization']


class KnowledgeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    visibility: Visibility = 'private'


class KnowledgeUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)


class AccessMember(BaseModel):
    user_id: UUID
    role: Literal['editor', 'viewer'] = 'viewer'


class KnowledgeAccess(BaseModel):
    visibility: Visibility
    members: list[AccessMember] = Field(default_factory=list, max_length=1000)
    owner_user_id: UUID | None = None  # solo admin


class KnowledgeResponse(BaseModel):
    id: str
    name: str
    description: str
    created_at: str
    documents_count: int
    owner_user_id: str
    visibility: Visibility
    permission: Literal['owner', 'editor', 'viewer'] | None
    can_edit: bool
    can_own: bool


class KnowledgeListResponse(BaseModel):
    knowledges: list[KnowledgeResponse]
    total: int


def _response(kb: Knowledge) -> KnowledgeResponse:
    return KnowledgeResponse(id=kb.id, name=kb.name, description=kb.description, created_at=kb.created_at,
                             documents_count=kb.documents_count, owner_user_id=kb.owner_user_id,
                             visibility=kb.visibility, permission=kb.permission,
                             can_edit=kb.can_edit, can_own=kb.can_own)


def _found(kb):
    if kb is None:
        raise HTTPException(404, "Knowledge non trovata")
    return kb


@router.get("", response_model=KnowledgeListResponse)
def list_all_knowledges() -> KnowledgeListResponse:
    items = [_response(kb) for kb in list_knowledges()]
    return KnowledgeListResponse(knowledges=items, total=len(items))


@router.post("", response_model=KnowledgeResponse, status_code=201, dependencies=[Depends(require_creator)])
def create_new_knowledge(body: KnowledgeCreate) -> KnowledgeResponse:
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Il nome è obbligatorio")
    return _response(_found(create_knowledge(name, body.description.strip(), body.visibility)))


@router.get("/{knowledge_id}", response_model=KnowledgeResponse)
def get_single_knowledge(knowledge_id: str) -> KnowledgeResponse:
    return _response(_found(get_knowledge(knowledge_id)))


@router.put("/{knowledge_id}", response_model=KnowledgeResponse, dependencies=[Depends(require_kb_owner)])
def update_single_knowledge(knowledge_id: str, body: KnowledgeUpdate) -> KnowledgeResponse:
    return _response(_found(update_knowledge(knowledge_id, body.name.strip(), body.description.strip())))


@router.get("/{knowledge_id}/access", dependencies=[Depends(require_kb_owner)])
def get_access(knowledge_id: str) -> dict:
    kb = _found(get_knowledge(knowledge_id))
    return {'visibility': kb.visibility, 'owner_user_id': kb.owner_user_id, 'members': list_members(knowledge_id)}


@router.put("/{knowledge_id}/access", dependencies=[Depends(require_kb_owner)])
def put_access(knowledge_id: str, body: KnowledgeAccess) -> dict:
    if body.owner_user_id and not request_user.get().is_admin:
        raise HTTPException(403, "Solo un amministratore può trasferire la proprietà")
    save_access(knowledge_id, body.visibility, [m.model_dump(mode='json') for m in body.members],
                str(body.owner_user_id) if body.owner_user_id else None)
    return {'success': True}


@router.delete("/{knowledge_id}", dependencies=[Depends(require_kb_owner)])
def delete_single_knowledge(knowledge_id: str) -> dict:
    if not delete_knowledge(knowledge_id):
        raise HTTPException(404, "Knowledge non trovata")
    return {"id": knowledge_id, "status": "deleted"}


directory_router = APIRouter(prefix="/api/directory", tags=["knowledge"])


@directory_router.get("")
def directory() -> list[dict]:
    """Utenti attivi, per scegliere con chi condividere."""
    return rest('POST', 'rpc/chatbot_directory', body={})
