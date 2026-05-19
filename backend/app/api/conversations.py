"""Endpoint CRUD per Conversazioni."""
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from typing import Optional

from app.core.conversations import (
    create_conversation,
    delete_conversation,
    get_conversation,
    list_conversations,
    add_message,
)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class ConversationCreate(BaseModel):
    """Richiesta creazione conversazione."""
    title: str
    knowledge_id: Optional[str] = None


class ConversationResponse(BaseModel):
    """Risposta singola conversazione (senza messaggi)."""
    id: str
    title: str
    created_at: str
    updated_at: str
    knowledge_id: Optional[str] = None


class ConversationListResponse(BaseModel):
    """Risposta lista conversazioni."""
    conversations: list[ConversationResponse]
    total: int


class MessageItem(BaseModel):
    """Messaggio nella conversazione."""
    id: str
    role: str
    content: str
    sources: Optional[list[dict]] = None
    timestamp: Optional[str] = None


class ConversationDetailResponse(BaseModel):
    """Risposta conversazione con messaggi."""
    id: str
    title: str
    created_at: str
    updated_at: str
    knowledge_id: Optional[str] = None
    messages: list[MessageItem]


class MessageCreate(BaseModel):
    """Richiesta creazione messaggio."""
    role: str  # "user" o "assistant"
    content: str
    sources: Optional[list[dict]] = None


class MessageResponse(BaseModel):
    """Risposta messaggio creato."""
    id: str
    conversation_id: str
    role: str
    content: str
    sources: Optional[list[dict]] = None
    timestamp: Optional[str] = None


@router.get("", response_model=ConversationListResponse)
async def list_all_conversations() -> ConversationListResponse:
    """Restituisce tutte le conversazioni ordinate per updated_at DESC."""
    try:
        convs = list_conversations()
        items = [
            ConversationResponse(
                id=conv["id"],
                title=conv["title"],
                created_at=conv["created_at"],
                updated_at=conv["updated_at"],
                knowledge_id=conv.get("knowledge_id"),
            )
            for conv in convs
        ]
        return ConversationListResponse(conversations=items, total=len(items))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=ConversationResponse, status_code=201)
async def create_new_conversation(body: ConversationCreate) -> ConversationResponse:
    """Crea una nuova conversazione vuota."""
    if not body.title or not body.title.strip():
        raise HTTPException(status_code=400, detail="Il titolo è obbligatorio")
    try:
        conv = create_conversation(body.title.strip(), body.knowledge_id)
        return ConversationResponse(
            id=conv["id"],
            title=conv["title"],
            created_at=conv["created_at"],
            updated_at=conv["updated_at"],
            knowledge_id=conv.get("knowledge_id"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_single_conversation(conversation_id: str) -> ConversationDetailResponse:
    """Restituisce una conversazione con tutti i suoi messaggi."""
    conv = get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversazione non trovata")
    
    messages = [
        MessageItem(
            id=msg["id"],
            role=msg["role"],
            content=msg["content"],
            sources=msg.get("sources"),
            timestamp=msg.get("timestamp"),
        )
        for msg in conv["messages"]
    ]
    
    return ConversationDetailResponse(
        id=conv["id"],
        title=conv["title"],
        created_at=conv["created_at"],
        updated_at=conv["updated_at"],
        knowledge_id=conv.get("knowledge_id"),
        messages=messages,
    )


@router.delete("/{conversation_id}")
async def delete_single_conversation(conversation_id: str) -> dict:
    """Elimina una conversazione e tutti i suoi messaggi."""
    success = delete_conversation(conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversazione non trovata")
    return {"id": conversation_id, "status": "deleted"}


@router.post("/{conversation_id}/messages", response_model=MessageResponse, status_code=201)
async def add_message_to_conversation(
    conversation_id: str,
    body: MessageCreate,
) -> MessageResponse:
    """Aggiunge un messaggio a una conversazione."""
    if not body.content or not body.content.strip():
        raise HTTPException(status_code=400, detail="Il contenuto del messaggio è obbligatorio")
    if body.role not in ["user", "assistant"]:
        raise HTTPException(status_code=400, detail="Il ruolo deve essere 'user' o 'assistant'")
    
    try:
        msg = add_message(
            conversation_id=conversation_id,
            role=body.role,
            content=body.content.strip(),
            sources=body.sources,
        )
        return MessageResponse(
            id=msg["id"],
            conversation_id=msg["conversation_id"],
            role=msg["role"],
            content=msg["content"],
            sources=msg.get("sources"),
            timestamp=msg.get("timestamp"),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

