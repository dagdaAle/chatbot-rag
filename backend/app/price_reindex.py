"""Rebuild the derived structured price index from saved Docling JSON files."""
from __future__ import annotations

import argparse
import json

from app.core.admin import privileged
from app.core.documents import get_structure_path
from app.core.price_lists import index_price_document
from app.core.supabase import identifier


def main() -> None:
    parser = argparse.ArgumentParser(description="Reindicizza i listini strutturati già estratti")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Tutti i documenti accessibili alla service role")
    group.add_argument("--knowledge", help="Una knowledge base specifica")
    args = parser.parse_args()

    params = {"select": "document_id,knowledge_id,filename", "order": "uploaded_at.asc"}
    if args.knowledge:
        params["knowledge_id"] = f"eq.{identifier(args.knowledge)}"
    documents = privileged("GET", "/rest/v1/documents", params=params) or []
    indexed_documents = indexed_entries = missing = 0
    for document in documents:
        path = get_structure_path(document["knowledge_id"], document["document_id"])
        if not path.exists():
            missing += 1
            print(f"{document['filename']}: struttura estratta assente")
            continue
        structure = json.loads(path.read_text(encoding="utf-8"))
        entries = index_price_document(
            structure,
            document["knowledge_id"],
            document["document_id"],
            document["filename"],
        )
        indexed_documents += bool(entries)
        indexed_entries += entries
        print(f"{document['filename']}: {entries} valori di prezzo")
    print(
        f"Completato: {indexed_documents} documenti con listini, "
        f"{indexed_entries} valori, {missing} strutture mancanti"
    )


if __name__ == "__main__":
    main()
