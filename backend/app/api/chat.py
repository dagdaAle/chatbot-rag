"""Endpoint chat RAG."""
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from app.core.chat import chat as rag_chat
from app.core.conversations import (
    create_conversation,
    get_conversation,
    save_turn,
)

router = APIRouter(prefix="/api/chat", tags=["chat"])


class MessageItem(BaseModel):
    """Messaggio nella cronologia."""
    role: str  # "user" o "assistant"
    content: str


class ChatRequest(BaseModel):
    """Richiesta chat con supporto cronologia e knowledge."""
    question: str = Field(min_length=1, max_length=8000)
    top_k: int = Field(default=12, ge=1, le=24)
    score_threshold: float = Field(default=0.3, ge=0, le=1)
    conversation_history: list[MessageItem] = Field(default_factory=list, max_length=200)
    knowledge_id: str | None = None
    conversation_id: str | None = None  # ID conversazione per salvataggio automatico


class SourceItem(BaseModel):
    knowledge_id: str | None = None
    """Fonte documento con testo del chunk e riferimento pagina."""
    filename: str
    score: float
    text: str = ""
    chunk_index: int = 0
    document_id: str = ""
    page_start: int = 1
    page_end: int = 1


class ChatResponse(BaseModel):
    """Risposta chat."""
    answer: str
    sources: list[SourceItem]
    contexts_used: int
    conversation_id: str | None = None  # ID conversazione creata/aggiornata


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """Invia una domanda al chatbot RAG con supporto cronologia e knowledge."""
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="La domanda non può essere vuota")

    from app.core.knowledge import get_knowledge
    if not request.knowledge_id or not get_knowledge(request.knowledge_id):
        raise HTTPException(status_code=404, detail="Knowledge non trovata")
    conversation_id = request.conversation_id
    history = []
    if conversation_id:
        conversation = get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversazione non trovata")
        if conversation['knowledge_id'] != request.knowledge_id:
            raise HTTPException(status_code=409, detail="La knowledge base della conversazione non può essere cambiata")
        history = [{"role": m["role"], "content": m["content"]} for m in conversation['messages']]
    # History is authoritative on the server; ignore client-supplied messages.
    result = rag_chat(request.question.strip(), top_k=request.top_k,
        conversation_history=history, knowledge_id=request.knowledge_id,
        score_threshold=request.score_threshold)
    if not conversation_id:
        conversation_id = create_conversation(request.question.strip()[:40], request.knowledge_id)['id']
    save_turn(conversation_id, request.question.strip(), result['answer'], result['sources'])
    return ChatResponse(**result, conversation_id=conversation_id)
