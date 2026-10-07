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
    "bge-m3": 1024,
    "bge-m3:latest": 1024,
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
        if not (settings.openai_embedding_api_key or settings.openai_api_key):
            raise RuntimeError("OPENAI_API_KEY non configurata")
        api_key = settings.openai_embedding_api_key or settings.openai_api_key
        base_url = settings.openai_embedding_base_url  # vuoto = default OpenAI
        _client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
    return _client


def get_embedding(text: str, operation: str = 'query_embedding') -> list[float]:
    from app.core.usage import measure
    provider, model = runtime_config.embedding_provider, runtime_config.embedding_model
    with measure(provider, model, operation) as usage:
        if provider == 'ollama':
            return ollama_generate_embedding(text, model=model, usage=usage)
        response = _get_openai_client().embeddings.create(model=model, input=text[:8000])
        if response.usage:
            usage.update(input_tokens=response.usage.total_tokens, output_tokens=0)
        return response.data[0].embedding


def get_query_embedding(query: str) -> list[float]:
    return get_embedding(query)


def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    from app.core.usage import measure
    provider, model = runtime_config.embedding_provider, runtime_config.embedding_model
    if provider == 'ollama':
        return [get_embedding(text, 'document_embedding') for text in texts]
    results = []
    for start in range(0, len(texts), 100):
        batch = [text[:8000] for text in texts[start:start+100]]
        with measure(provider, model, 'document_embedding') as usage:
            response = _get_openai_client().embeddings.create(model=model,input=batch)
            if response.usage:
                usage.update(input_tokens=response.usage.total_tokens,output_tokens=0)
            results.extend(item.embedding for item in sorted(response.data,key=lambda item:item.index))
    return results
