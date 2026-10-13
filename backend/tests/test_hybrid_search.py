"""Hybrid semantic/lexical retrieval and safe index migration."""
from qdrant_client import QdrantClient, models

from app.core import chat
from app.hybrid_reindex import migrate_collection
from app.core.lexical import LEXICAL_VECTOR_NAME, hybrid_vector, lexical_terms, sparse_text_vector
from app.core.qdrant_client import collection_supports_hybrid, sparse_vectors_config


def client(tmp_path):
    return QdrantClient(path=str(tmp_path / "qdrant"), force_disable_check_same_thread=True)


def create_hybrid(current, name="documents"):
    current.create_collection(
        collection_name=name,
        vectors_config=models.VectorParams(size=3, distance=models.Distance.COSINE),
        sparse_vectors_config=sparse_vectors_config(),
    )


def test_identifier_normalization_keeps_complete_act_number():
    first = {term for term, _ in lexical_terms("D.G.R. n. 123/2024") if term.startswith("identifier:")}
    second = {term for term, _ in lexical_terms("atto DGR 123-2024") if term.startswith("identifier:")}
    assert "identifier:1232024" in first & second


def test_hybrid_retrieval_finds_exact_number_below_dense_threshold(monkeypatch, tmp_path):
    current = client(tmp_path)
    create_hybrid(current)
    current.upsert("documents", [
        models.PointStruct(
            id=1,
            vector=hybrid_vector([1.0, 0.0, 0.0], "Politiche agricole generali"),
            payload={"text": "Politiche agricole generali", "filename": "generale.pdf"},
        ),
        models.PointStruct(
            id=2,
            vector=hybrid_vector([0.0, 1.0, 0.0], "Delibera DGR 007/2026"),
            payload={"text": "Delibera DGR 007/2026", "filename": "atto.pdf"},
        ),
    ])
    monkeypatch.setattr(chat, "get_client", lambda: current)
    monkeypatch.setattr(chat, "get_query_embedding", lambda _: [1.0, 0.0, 0.0])

    contexts = chat.retrieve_context("Cosa dice la DGR 007-2026?", top_k=2, score_threshold=.99, use_mmr=True)

    assert any(context["filename"] == "atto.pdf" for context in contexts)
    assert all(context["retrieval_method"] == "hybrid_rrf" for context in contexts)


def test_dense_collection_migration_preserves_points_and_keeps_backup(tmp_path):
    current = client(tmp_path)
    current.create_collection(
        collection_name="documents",
        vectors_config=models.VectorParams(size=3, distance=models.Distance.COSINE),
    )
    current.upsert("documents", [
        models.PointStruct(id=1, vector=[1.0, 0.0, 0.0], payload={"text": "Determina 42/2025"}),
        models.PointStruct(id=2, vector=[0.0, 1.0, 0.0], payload={"text": "Altro documento"}),
    ])

    backup = migrate_collection(current, "documents")

    assert backup and current.count(backup, exact=True).count == 2
    assert current.count("documents", exact=True).count == 2
    assert collection_supports_hybrid(current, "documents")
    found = current.query_points(
        "documents",
        query=sparse_text_vector("42-2025"),
        using=LEXICAL_VECTOR_NAME,
        limit=1,
        with_payload=True,
    ).points
    assert found[0].payload["text"] == "Determina 42/2025"
    assert found[0].payload["lexical_index_version"] == 1
