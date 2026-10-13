"""Safely rebuild existing dense collections with the lexical sparse index.

Run this while the API and import worker are stopped. The original point set is
copied to a dense backup collection before the application collection is rebuilt.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from qdrant_client import models

from app.core.lexical import LEXICAL_INDEX_VERSION, hybrid_vector
from app.core.qdrant_client import (
    collection_supports_hybrid,
    get_client,
    sparse_vectors_config,
)


def _exists(client, name: str) -> bool:
    return any(collection.name == name for collection in client.get_collections().collections)


def _count(client, name: str) -> int:
    return client.count(collection_name=name, exact=True).count


def _records(client, collection_name: str, batch_size: int = 100):
    offset = None
    while True:
        records, offset = client.scroll(
            collection_name=collection_name,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        if records:
            yield records
        if offset is None:
            return


def _copy_dense(client, source: str, target: str) -> None:
    for records in _records(client, source):
        client.upsert(
            collection_name=target,
            points=[models.PointStruct(id=record.id, vector=record.vector, payload=record.payload) for record in records],
            wait=True,
        )


def _copy_hybrid(client, source: str, target: str) -> None:
    for records in _records(client, source):
        points = []
        for record in records:
            dense = record.vector.get("") if isinstance(record.vector, dict) else record.vector
            if dense is None:
                raise ValueError(f"Il punto {record.id} non contiene il vettore semantico")
            payload = dict(record.payload or {})
            payload["lexical_index_version"] = LEXICAL_INDEX_VERSION
            points.append(models.PointStruct(
                id=record.id,
                vector=hybrid_vector(dense, str(payload.get("text", ""))),
                payload=payload,
            ))
        client.upsert(collection_name=target, points=points, wait=True)


def migrate_collection(client, collection_name: str) -> str | None:
    """Migrate one collection and return the retained backup collection name."""
    if not _exists(client, collection_name):
        raise ValueError(f"Collezione inesistente: {collection_name}")
    if collection_supports_hybrid(client, collection_name):
        return None

    info = client.get_collection(collection_name)
    dense_config = info.config.params.vectors
    if not isinstance(dense_config, models.VectorParams):
        raise ValueError("La migrazione supporta le collezioni dense senza nome usate da questa applicazione")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_name = f"{collection_name}__dense_backup_{stamp}"
    if _exists(client, backup_name):
        raise ValueError(f"Backup già esistente: {backup_name}")

    source_count = _count(client, collection_name)
    client.create_collection(collection_name=backup_name, vectors_config=dense_config)
    try:
        _copy_dense(client, collection_name, backup_name)
        if _count(client, backup_name) != source_count:
            raise RuntimeError("Il backup Qdrant non contiene tutti i punti; migrazione annullata")
    except Exception:
        client.delete_collection(backup_name)
        raise

    original_deleted = False
    try:
        client.delete_collection(collection_name)
        original_deleted = True
        client.create_collection(
            collection_name=collection_name,
            vectors_config=dense_config,
            sparse_vectors_config=sparse_vectors_config(),
        )
        _copy_hybrid(client, backup_name, collection_name)
        if _count(client, collection_name) != source_count:
            raise RuntimeError("La collezione ibrida non contiene tutti i punti")
        return backup_name
    except Exception as migration_error:
        if original_deleted:
            try:
                if _exists(client, collection_name):
                    client.delete_collection(collection_name)
                client.create_collection(collection_name=collection_name, vectors_config=dense_config)
                _copy_dense(client, backup_name, collection_name)
                if _count(client, collection_name) != source_count:
                    raise RuntimeError("numero di punti non coerente dopo il ripristino")
            except Exception as restore_error:
                raise RuntimeError(
                    f"Migrazione fallita e ripristino automatico fallito; usa {backup_name}: {restore_error}"
                ) from migration_error
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Reindicizza Qdrant per la ricerca ibrida")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--collection", action="append", help="Nome Qdrant; ripetibile")
    group.add_argument("--all", action="store_true", help="Tutte le collezioni applicative")
    args = parser.parse_args()

    client = get_client()
    names = args.collection or [
        item.name for item in client.get_collections().collections
        if (item.name == "documents" or item.name.startswith("kb_")) and "__dense_backup_" not in item.name
    ]
    for name in names:
        backup = migrate_collection(client, name)
        if backup:
            print(f"{name}: indice ibrido creato; backup conservato in {backup}")
        else:
            print(f"{name}: indice ibrido già presente")


if __name__ == "__main__":
    main()
