"""Endpoint chat RAG."""
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from app.core.chat import chat as rag_chat
from app.core.conversations import (
    create_conversation,
    add_message,
)

router = APIRouter(prefix="/api/chat", tags=["chat"])


class MessageItem(BaseModel):
    """Messaggio nella cronologia."""
    role: str  # "user" o "assistant"
    content: str


class ChatRequest(BaseModel):
    """Richiesta chat con supporto cronologia e knowledge."""
    question: str
    top_k: int = 5
    conversation_history: list[MessageItem] = []
    knowledge_id: str | None = None
    conversation_id: str | None = None  # ID conversazione per salvataggio automatico


class SourceItem(BaseModel):
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
async def chat(request: ChatRequest) -> ChatResponse:
    """Invia una domanda al chatbot RAG con supporto cronologia e knowledge."""
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="La domanda non può essere vuota")

    try:
        # Converti la cronologia in formato dict
        history = [{"role": msg.role, "content": msg.content} for msg in request.conversation_history]

        # Genera la risposta
        result = rag_chat(
            request.question.strip(),
            top_k=request.top_k,
            conversation_history=history if history else None,
            knowledge_id=request.knowledge_id,
        )

        conversation_id = request.conversation_id

        # Salvataggio automatico
        try:
            # Se non c'è conversation_id, crea una nuova conversazione
            if not conversation_id:
                # Genera titolo dalla prima domanda (troncato a 40 caratteri)
                title = request.question.strip()
                if len(title) > 40:
                    title = title[:37] + "..."
                
                new_conv = create_conversation(title, request.knowledge_id)
                conversation_id = new_conv["id"]

            # Salva i messaggi nella conversazione
            if conversation_id:
                # Salva il messaggio utente
                add_message(
                    conversation_id=conversation_id,
                    role="user",
                    content=request.question.strip(),
                )

                # Salva il messaggio assistant con le fonti
                # result["sources"] è già una lista di dict, non serve .dict()
                add_message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=result["answer"],
                    sources=result["sources"] if result["sources"] else None,
                )
        except Exception as save_error:
            # Se il salvataggio fallisce, continua comunque (non bloccare la chat)
            print(f"Errore salvataggio conversazione: {save_error}")

        return ChatResponse(
            answer=result["answer"],
            sources=result["sources"],
            contexts_used=result["contexts_used"],
            conversation_id=conversation_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore durante l'elaborazione: {e}")
