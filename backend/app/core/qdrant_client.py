"""Client Qdrant e gestione collezioni.

Supporta due modalità:
  - server mode (default): si connette a un server Qdrant remoto
  - local mode: Qdrant embedded, scrive su disco (ideale per Railway single-instance)
"""
import os
from functools import lru_cache
from threading import RLock

class LockedLocalClient:
    """Serialize embedded storage access across FastAPI worker threads."""
    def __init__(self, client):
        self.client = client
        self.lock = RLock()

    def __getattr__(self, name):
        value = getattr(self.client, name)
        if not callable(value):
            return value
        def call(*args, **kwargs):
            with self.lock:
                return value(*args, **kwargs)
        return call

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from app.config import settings
from app.core.embeddings import get_current_embedding_size

COLLECTION_NAME = "documents"


@lru_cache(maxsize=1)
def get_client() -> QdrantClient:
    """Restituisce il client Qdrant.

    Se QDRANT_LOCAL_PATH è impostato, usa la modalità embedded (local).
    Altrimenti si connette a un server remoto.
    """
    local_path = os.getenv("QDRANT_LOCAL_PATH")
    if local_path:
        return LockedLocalClient(QdrantClient(path=local_path, force_disable_check_same_thread=True))

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
        raise ValueError("Il modello embedding non è compatibile con questa knowledge base. "
                         "Crea una nuova knowledge base e reindicizza i documenti; nessun indice è stato cancellato.")

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
