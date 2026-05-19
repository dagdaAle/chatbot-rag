"""Endpoint per gestione impostazioni (prompt di sistema)."""
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from app.core.chat import get_system_prompt, save_system_prompt, DEFAULT_SYSTEM_PROMPT

router = APIRouter(prefix="/api/settings", tags=["settings"])


class PromptResponse(BaseModel):
    """Risposta con il prompt di sistema."""
    prompt: str
    is_default: bool


class PromptUpdateRequest(BaseModel):
    """Richiesta di aggiornamento prompt."""
    prompt: str


class PromptUpdateResponse(BaseModel):
    """Risposta aggiornamento prompt."""
    success: bool
    message: str


@router.get("/prompt", response_model=PromptResponse)
async def get_prompt() -> PromptResponse:
    """Ottieni il prompt di sistema corrente."""
    try:
        current_prompt = get_system_prompt()
        is_default = current_prompt == DEFAULT_SYSTEM_PROMPT
        return PromptResponse(prompt=current_prompt, is_default=is_default)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore nel recupero del prompt: {e}")


@router.put("/prompt", response_model=PromptUpdateResponse)
async def update_prompt(request: PromptUpdateRequest) -> PromptUpdateResponse:
    """Aggiorna il prompt di sistema."""
    if not request.prompt or not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Il prompt non può essere vuoto")
    
    try:
        success = save_system_prompt(request.prompt.strip())
        if success:
            return PromptUpdateResponse(success=True, message="Prompt aggiornato con successo")
        else:
            raise HTTPException(status_code=500, detail="Errore nel salvataggio del prompt")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore nell'aggiornamento del prompt: {e}")


@router.post("/prompt/reset", response_model=PromptUpdateResponse)
async def reset_prompt() -> PromptUpdateResponse:
    """Ripristina il prompt di sistema al valore di default."""
    try:
        success = save_system_prompt(DEFAULT_SYSTEM_PROMPT)
        if success:
            return PromptUpdateResponse(success=True, message="Prompt ripristinato al valore di default")
        else:
            raise HTTPException(status_code=500, detail="Errore nel ripristino del prompt")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore nel ripristino del prompt: {e}")


@router.get("/prompt/default", response_model=PromptResponse)
async def get_default_prompt() -> PromptResponse:
    """Ottieni il prompt di default (senza modificarlo)."""
    return PromptResponse(prompt=DEFAULT_SYSTEM_PROMPT, is_default=True)
