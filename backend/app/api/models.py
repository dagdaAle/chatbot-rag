"""Endpoint per gestione modelli LLM e embedding."""
import requests
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from app.config import settings, runtime_config

router = APIRouter(prefix="/api/settings/models", tags=["models"])


# ============ Modelli di risposta ============

class ModelInfo(BaseModel):
    """Informazioni su un modello."""
    id: str
    name: str
    provider: str  # "openai" o "ollama"


class ModelsListResponse(BaseModel):
    """Lista modelli disponibili."""
    models: list[ModelInfo]
    current: str
    provider: str


class ModelSetRequest(BaseModel):
    """Richiesta per impostare il modello."""
    model_id: str
    provider: str


class ModelSetResponse(BaseModel):
    """Risposta impostazione modello."""
    success: bool
    model_id: str
    provider: str
    message: str


class ProviderConfigResponse(BaseModel):
    """Configurazione provider corrente."""
    chat_provider: str
    chat_model: str
    embedding_provider: str
    embedding_model: str
    ollama_available: bool
    openai_available: bool


# ============ Modelli OpenAI predefiniti ============

OPENAI_CHAT_MODELS = [
    ModelInfo(id="gpt-4o-mini", name="GPT-4o Mini", provider="openai"),
    ModelInfo(id="gpt-4o", name="GPT-4o", provider="openai"),
    ModelInfo(id="gpt-4-turbo", name="GPT-4 Turbo", provider="openai"),
    ModelInfo(id="gpt-3.5-turbo", name="GPT-3.5 Turbo", provider="openai"),
]

OPENAI_EMBEDDING_MODELS = [
    ModelInfo(id="text-embedding-3-small", name="Text Embedding 3 Small (1536d)", provider="openai"),
    ModelInfo(id="text-embedding-3-large", name="Text Embedding 3 Large (3072d)", provider="openai"),
    ModelInfo(id="text-embedding-ada-002", name="Text Embedding Ada 002 (1536d)", provider="openai"),
]


def _fetch_ollama_models() -> list[ModelInfo]:
    """Recupera la lista dei modelli disponibili su Ollama."""
    try:
        resp = requests.get(
            f"{settings.ollama_base_url}/api/tags",
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        models = []
        for m in data.get("models", []):
            name = m.get("name", "")
            models.append(ModelInfo(
                id=name,
                name=name,
                provider="ollama",
            ))
        return models
    except Exception:
        return []


def _is_ollama_available() -> bool:
    """Verifica se Ollama è raggiungibile."""
    try:
        resp = requests.get(f"{settings.ollama_base_url}/api/tags", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False


# ============ Endpoint ============

@router.get("/config", response_model=ProviderConfigResponse)
async def get_config() -> ProviderConfigResponse:
    """Ottieni la configurazione corrente del provider LLM."""
    return ProviderConfigResponse(
        chat_provider=runtime_config.chat_provider,
        chat_model=runtime_config.chat_model,
        embedding_provider=runtime_config.embedding_provider,
        embedding_model=runtime_config.embedding_model,
        ollama_available=_is_ollama_available(),
        openai_available=bool(settings.openai_api_key),
    )


@router.get("/chat", response_model=ModelsListResponse)
async def list_chat_models() -> ModelsListResponse:
    """Lista dei modelli chat disponibili (OpenAI + Ollama)."""
    models: list[ModelInfo] = []
    
    # Aggiungi modelli OpenAI se la chiave è configurata
    if settings.openai_api_key:
        models.extend(OPENAI_CHAT_MODELS)
    
    # Aggiungi modelli Ollama se disponibile
    ollama_models = _fetch_ollama_models()
    # Filtra solo modelli non-embedding per la chat
    for m in ollama_models:
        if "embed" not in m.id.lower():
            models.append(m)
    
    return ModelsListResponse(
        models=models,
        current=runtime_config.chat_model,
        provider=runtime_config.chat_provider,
    )


@router.get("/embedding", response_model=ModelsListResponse)
async def list_embedding_models() -> ModelsListResponse:
    """Lista dei modelli embedding disponibili (OpenAI + Ollama)."""
    models: list[ModelInfo] = []
    
    # Aggiungi modelli OpenAI se la chiave è configurata
    if settings.openai_api_key:
        models.extend(OPENAI_EMBEDDING_MODELS)
    
    # Aggiungi modelli Ollama per embedding
    ollama_models = _fetch_ollama_models()
    for m in ollama_models:
        if "embed" in m.id.lower() or "nomic" in m.id.lower():
            models.append(m)
    
    return ModelsListResponse(
        models=models,
        current=runtime_config.embedding_model,
        provider=runtime_config.embedding_provider,
    )


@router.put("/chat", response_model=ModelSetResponse)
async def set_chat_model(request: ModelSetRequest) -> ModelSetResponse:
    """Imposta il modello chat corrente (indipendente dagli embedding)."""
    if request.provider not in ("openai", "ollama"):
        raise HTTPException(status_code=400, detail="Provider non valido. Usa 'openai' o 'ollama'.")
    
    if request.provider == "openai" and not settings.openai_api_key:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY non configurata.")
    
    # Cambia SOLO il provider/modello della chat, NON tocca gli embedding
    runtime_config.chat_provider = request.provider
    runtime_config.chat_model = request.model_id
    
    return ModelSetResponse(
        success=True,
        model_id=request.model_id,
        provider=request.provider,
        message=f"Modello chat impostato a {request.model_id} ({request.provider})",
    )


@router.put("/embedding", response_model=ModelSetResponse)
async def set_embedding_model(request: ModelSetRequest) -> ModelSetResponse:
    """Imposta il modello embedding corrente (indipendente dalla chat)."""
    if request.provider not in ("openai", "ollama"):
        raise HTTPException(status_code=400, detail="Provider non valido. Usa 'openai' o 'ollama'.")
    
    if request.provider == "openai" and not settings.openai_api_key:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY non configurata.")
    
    # Cambia SOLO il provider/modello degli embedding, NON tocca la chat
    runtime_config.embedding_provider = request.provider
    runtime_config.embedding_model = request.model_id
    
    return ModelSetResponse(
        success=True,
        model_id=request.model_id,
        provider=request.provider,
        message=f"Modello embedding impostato a {request.model_id} ({request.provider})",
    )

