"""Client Qdrant e gestione collezioni."""
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from app.config import settings
from app.core.embeddings import get_current_embedding_size

# Collezione legacy (mantenuta per retrocompatibilità)
COLLECTION_NAME = "documents"


def get_client() -> QdrantClient:
    """Restituisce il client Qdrant."""
    return QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)


# ── Funzioni per Knowledge Base (collezioni dinamiche) ──────────────────

def ensure_collection_for_kb(
    client: QdrantClient,
    collection_name: str,
    recreate_if_wrong_size: bool = False,
) -> None:
    """Crea una collezione per una Knowledge Base se non esiste."""
    vector_size = get_current_embedding_size()
    collections = client.get_collections().collections
    existing = next((c for c in collections if c.name == collection_name), None)

    if existing is not None:
        info = client.get_collection(collection_name)
        current_size = info.config.params.vectors.size
        if current_size == vector_size:
            return
        if recreate_if_wrong_size:
            client.delete_collection(collection_name)
        else:
            return

    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def delete_collection_for_kb(client: QdrantClient, collection_name: str) -> None:
    """Elimina una collezione Qdrant di una Knowledge Base."""
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass  # Collezione non esisteva


# ── Funzioni legacy (singola collezione) ────────────────────────────────

def ensure_collection(client: QdrantClient, recreate_if_wrong_size: bool = False) -> None:
    """Crea la collezione legacy se non esiste o la ricrea se la dimensione è errata."""
    ensure_collection_for_kb(client, COLLECTION_NAME, recreate_if_wrong_size)


def reset_collection(client: QdrantClient) -> None:
    """Elimina e ricrea la collezione legacy (utile per migrazioni)."""
    vector_size = get_current_embedding_size()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )
