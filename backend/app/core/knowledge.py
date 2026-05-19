"""Gestione Knowledge Base: CRUD metadati + collezioni Qdrant."""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, asdict

from app.core.qdrant_client import get_client, ensure_collection_for_kb, delete_collection_for_kb
from app.core.documents import delete_knowledge_pdfs

# File persistenza metadati knowledge
KNOWLEDGES_FILE = Path(__file__).parent.parent.parent / "data" / "knowledges.json"


@dataclass
class Knowledge:
    """Modello dati per una Knowledge Base."""
    id: str
    name: str
    description: str
    created_at: str
    documents_count: int = 0


def _load_knowledges() -> list[dict]:
    """Carica la lista delle knowledge dal file JSON."""
    try:
        if KNOWLEDGES_FILE.exists():
            with open(KNOWLEDGES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("knowledges", [])
    except Exception:
        pass
    return []


def _save_knowledges(knowledges: list[dict]) -> None:
    """Salva la lista delle knowledge nel file JSON."""
    KNOWLEDGES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(KNOWLEDGES_FILE, "w", encoding="utf-8") as f:
        json.dump({"knowledges": knowledges}, f, ensure_ascii=False, indent=2)


def get_collection_name(knowledge_id: str) -> str:
    """Restituisce il nome della collezione Qdrant per una knowledge."""
    return f"kb_{knowledge_id.replace('-', '_')}"


def list_knowledges() -> list[Knowledge]:
    """Restituisce tutte le knowledge."""
    raw = _load_knowledges()
    return [Knowledge(**k) for k in raw]


def get_knowledge(knowledge_id: str) -> Knowledge | None:
    """Restituisce una knowledge per ID."""
    raw = _load_knowledges()
    for k in raw:
        if k["id"] == knowledge_id:
            return Knowledge(**k)
    return None


def create_knowledge(name: str, description: str = "") -> Knowledge:
    """Crea una nuova knowledge con la relativa collezione Qdrant."""
    kb_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    kb = Knowledge(
        id=kb_id,
        name=name,
        description=description,
        created_at=now,
        documents_count=0,
    )

    # Crea collezione Qdrant
    client = get_client()
    collection_name = get_collection_name(kb_id)
    ensure_collection_for_kb(client, collection_name)

    # Salva metadati
    knowledges = _load_knowledges()
    knowledges.append(asdict(kb))
    _save_knowledges(knowledges)

    return kb


def delete_knowledge(knowledge_id: str) -> bool:
    """Elimina una knowledge e la sua collezione Qdrant."""
    knowledges = _load_knowledges()
    found = False
    updated = []
    for k in knowledges:
        if k["id"] == knowledge_id:
            found = True
        else:
            updated.append(k)

    if not found:
        return False

    # Elimina collezione Qdrant
    client = get_client()
    collection_name = get_collection_name(knowledge_id)
    delete_collection_for_kb(client, collection_name)

    # Elimina tutti i PDF dal disco
    delete_knowledge_pdfs(knowledge_id)

    # Aggiorna metadati
    _save_knowledges(updated)
    return True


def update_documents_count(knowledge_id: str, delta: int = 0, absolute: int | None = None) -> None:
    """Aggiorna il conteggio documenti di una knowledge."""
    knowledges = _load_knowledges()
    for k in knowledges:
        if k["id"] == knowledge_id:
            if absolute is not None:
                k["documents_count"] = absolute
            else:
                k["documents_count"] = max(0, k.get("documents_count", 0) + delta)
            break
    _save_knowledges(knowledges)

