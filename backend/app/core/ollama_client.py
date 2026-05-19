"""Client Ollama per chat e embeddings."""
import requests
from typing import Optional

from app.config import settings


def generate_chat_response(
    messages: list[dict],
    model: Optional[str] = None
) -> str:
    """Genera una risposta usando Ollama per la chat."""
    model = model or settings.ollama_chat_model
    url = f"{settings.ollama_base_url}/api/chat"
    
    try:
        response = requests.post(
            url,
            json={
                "model": model,
                "messages": messages,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 1500,
                },
                "stream": False,
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("message", {}).get("content", "")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Errore durante la generazione con Ollama: {e}")


def generate_embedding(text: str, model: Optional[str] = None) -> list[float]:
    """Genera embedding usando Ollama (API /api/embed)."""
    model = model or settings.ollama_embedding_model
    url = f"{settings.ollama_base_url}/api/embed"
    
    # Tronca testo troppo lungo
    text = text[:8000] if len(text) > 8000 else text
    
    try:
        response = requests.post(
            url,
            json={
                "model": model,
                "input": text,
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        # /api/embed restituisce {"embeddings": [[...]]}
        embeddings = data.get("embeddings", [])
        if embeddings and len(embeddings) > 0:
            return embeddings[0]
        return []
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Errore durante la generazione embedding con Ollama: {e}")

