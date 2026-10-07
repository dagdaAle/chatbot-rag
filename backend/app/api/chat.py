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
    model_key: str | None = Field(default=None, max_length=250)


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
    model_key: str | None = None


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
    from app.core.supabase import rest, identifier
    from app.core.admin import privileged
    from app.core.usage import operation_context
    from app.auth import request_user
    from app.config import runtime_config, settings
    from time import perf_counter
    models = rest('GET','app_models',params={'enabled':'eq.true','kind':'eq.chat'})
    available = {m['key']:m for m in models if m['provider']=='ollama' or (m['provider']=='openai' and settings.openai_api_key) or (m['provider']=='deepseek' and settings.deepseek_api_key)}
    key = request.model_key or f'{runtime_config.chat_provider}:{runtime_config.chat_model}'
    if request.model_key is None and key not in available and available:
        key = next(iter(available))
    if key not in available:
        raise HTTPException(403,'Modello non consentito o non configurato')
    chosen = available[key]
    reservation = privileged('POST','/rest/v1/rpc/chatbot_reserve_request',body={
        'p_user':request_user.get().id,'p_kb':identifier(request.knowledge_id),'p_conversation':conversation_id})
    marker = operation_context.set({'parent_id':reservation,'knowledge_id':request.knowledge_id,'conversation_id':conversation_id})
    started = perf_counter()
    try:
        result = rag_chat(request.question.strip(),top_k=request.top_k,conversation_history=history,
            knowledge_id=request.knowledge_id,score_threshold=request.score_threshold,provider=chosen['provider'],model=chosen['model_id'])
        if not conversation_id:
            conversation_id = create_conversation(request.question.strip()[:40], request.knowledge_id)['id']
        save_turn(conversation_id, request.question.strip(), result['answer'], result['sources'])
        privileged('PATCH','/rest/v1/usage_events',params={'parent_id':f'eq.{reservation}'},body={'conversation_id':conversation_id})
        privileged('PATCH','/rest/v1/usage_events',params={'id':f'eq.{reservation}'},body={
            'status':'success' if result['contexts_used'] else 'no_context','provider':chosen['provider'],'model_id':chosen['model_id'],
            'conversation_id':conversation_id,'duration_ms':int((perf_counter()-started)*1000)})
        return ChatResponse(**result,conversation_id=conversation_id,model_key=key)
    except Exception as exc:
        privileged('PATCH','/rest/v1/usage_events',params={'id':f'eq.{reservation}'},body={'status':'error','error_code':type(exc).__name__,'duration_ms':int((perf_counter()-started)*1000)})
        raise
    finally:
        operation_context.reset(marker)
