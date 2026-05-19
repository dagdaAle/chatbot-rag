"""Embedding con OpenAI o Ollama."""
from openai import OpenAI

from app.config import settings, runtime_config
from app.core.ollama_client import generate_embedding as ollama_generate_embedding

# Mappa dimensioni embedding per modelli noti
EMBEDDING_SIZES = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
    "nomic-embed-text": 768,
    "nomic-embed-text:latest": 768,
    "mxbai-embed-large": 1024,
    "all-minilm": 384,
    "snowflake-arctic-embed": 1024,
}

# Dimensione di default
EMBEDDING_SIZE = 1536

_client: OpenAI | None = None


def get_current_embedding_size() -> int:
    """Restituisce la dimensione degli embedding in base al modello corrente."""
    model = runtime_config.embedding_model
    return EMBEDDING_SIZES.get(model, EMBEDDING_SIZES.get(model.split(":")[0], 1536))


def _get_openai_client() -> OpenAI:
    """Restituisce il client OpenAI (singleton)."""
    global _client
    if _client is None:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY non configurata")
        api_key = settings.openai_embedding_api_key or settings.openai_api_key
        base_url = settings.openai_embedding_base_url  # vuoto = default OpenAI
        _client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
    return _client


def get_embedding(text: str) -> list[float]:
    """Genera embedding per un testo usando OpenAI o Ollama."""
    if runtime_config.embedding_provider == "ollama":
        return ollama_generate_embedding(text, model=runtime_config.embedding_model)
    
    # Usa OpenAI
    client = _get_openai_client()
    # Tronca testo troppo lungo (limite circa 8k token)
    text = text[:8000] if len(text) > 8000 else text
    response = client.embeddings.create(
        model=runtime_config.embedding_model,
        input=text,
    )
    return response.data[0].embedding


def get_query_embedding(query: str) -> list[float]:
    """Genera embedding per una query usando OpenAI o Ollama."""
    return get_embedding(query)


def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Genera embedding per più testi in batch."""
    if runtime_config.embedding_provider == "ollama":
        # Ollama non supporta batch nativamente, processiamo sequenzialmente
        results = []
        for text in texts:
            results.append(ollama_generate_embedding(text, model=runtime_config.embedding_model))
        return results
    
    # Usa OpenAI con batch
    client = _get_openai_client()
    # OpenAI supporta batch di max 2048 input
    results = []
    batch_size = 100
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        batch = [t[:8000] if len(t) > 8000 else t for t in batch]
        response = client.embeddings.create(
            model=runtime_config.embedding_model,
            input=batch,
        )
        # Mantieni l'ordine originale
        batch_embeddings = [None] * len(batch)
        for item in response.data:
            batch_embeddings[item.index] = item.embedding
        results.extend(batch_embeddings)
    return results
