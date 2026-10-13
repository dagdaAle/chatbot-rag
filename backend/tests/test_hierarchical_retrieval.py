"""Section expansion after dense/sparse anchor retrieval."""
from qdrant_client import QdrantClient, models

from app.core.hierarchical import expand_hierarchical_contexts


def collection(tmp_path, points):
    current = QdrantClient(path=str(tmp_path / "qdrant"), force_disable_check_same_thread=True)
    current.create_collection(
        "documents",
        vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE),
    )
    current.upsert("documents", [
        models.PointStruct(id=index + 1, vector=[1.0, 0.0], payload=payload)
        for index, payload in enumerate(points)
    ])
    return current


def anchor(**changes):
    return {
        "text": "Articolo 7\n\nsecondo frammento",
        "filename": "regolamento.pdf",
        "document_id": "doc-1",
        "chunk_index": 1,
        "page_start": 2,
        "page_end": 2,
        "section_path": ["Titolo I", "Articolo 7"],
        "section_refs": ["#/headers/1", "#/headers/2"],
        "source_regions": [],
        "content_kind": "text",
        "score": .8,
        "retrieval_method": "hybrid_rrf",
        **changes,
    }


def section_chunks():
    common = {
        "document_id": "doc-1",
        "filename": "regolamento.pdf",
        "section_path": ["Titolo I", "Articolo 7"],
        "section_refs": ["#/headers/1", "#/headers/2"],
        "content_kind": "text",
    }
    return [
        {**common, "chunk_index": 0, "text": "Titolo I > Articolo 7\n\nprimo frammento", "page_start": 1, "page_end": 1},
        {**common, "chunk_index": 1, "text": "Titolo I > Articolo 7\n\nsecondo frammento", "page_start": 2, "page_end": 2},
        {**common, "chunk_index": 2, "text": "Titolo I > Articolo 7\n\nterzo frammento", "page_start": 3, "page_end": 3},
        {**common, "chunk_index": 3, "text": "Titolo I > Articolo 8\n\nnon pertinente", "page_start": 4, "page_end": 4,
         "section_path": ["Titolo I", "Articolo 8"], "section_refs": ["#/headers/1", "#/headers/3"]},
    ]


def test_expands_complete_structural_section_and_collapses_duplicate_anchors(tmp_path):
    current = collection(tmp_path, section_chunks())

    result = expand_hierarchical_contexts(
        current,
        "documents",
        [anchor(), anchor(chunk_index=2, text="terzo frammento")],
        section_char_limit=5000,
        total_char_limit=10000,
        neighbor_chunks=1,
    )

    assert len(result) == 1
    assert result[0]["context_scope"] == "section"
    assert result[0]["section_complete"] is True
    assert result[0]["expanded_chunks"] == 3
    assert result[0]["page_start"] == 1 and result[0]["page_end"] == 3
    assert result[0]["text"].count("Articolo 7") == 1
    assert "primo frammento" in result[0]["text"]
    assert "terzo frammento" in result[0]["text"]
    assert "non pertinente" not in result[0]["text"]


def test_section_limit_keeps_anchor_and_marks_extract_incomplete(tmp_path):
    chunks = section_chunks()
    for index in range(3):
        chunks[index]["text"] += " " + (str(index) * 120)
    current = collection(tmp_path, chunks)

    result = expand_hierarchical_contexts(
        current,
        "documents",
        [anchor()],
        section_char_limit=190,
        total_char_limit=500,
        neighbor_chunks=1,
    )

    assert result[0]["section_complete"] is False
    assert "secondo frammento" in result[0]["text"]
    assert result[0]["expanded_chunks"] == 1


def test_unstructured_document_uses_adjacent_chunks(tmp_path):
    chunks = [
        {"document_id": "doc-1", "filename": "scan.pdf", "chunk_index": index,
         "text": f"pagina {index}", "page_start": index + 1, "page_end": index + 1}
        for index in range(5)
    ]
    current = collection(tmp_path, chunks)

    result = expand_hierarchical_contexts(
        current,
        "documents",
        [anchor(text="pagina 2", chunk_index=2, section_path=[], section_refs=[])],
        section_char_limit=5000,
        total_char_limit=10000,
        neighbor_chunks=1,
    )

    assert result[0]["context_scope"] == "neighbors"
    assert result[0]["section_complete"] is False
    assert result[0]["expanded_chunks"] == 3
    assert "pagina 0" not in result[0]["text"]
    assert all(f"pagina {index}" in result[0]["text"] for index in (1, 2, 3))


def test_incomplete_section_keeps_a_second_distant_anchor(tmp_path):
    chunks = section_chunks()
    for index in range(3):
        chunks[index]["text"] += " " + str(index) * 120
    current = collection(tmp_path, chunks)
    result = expand_hierarchical_contexts(current, "documents", [anchor(chunk_index=0), anchor(chunk_index=2)],
        section_char_limit=190, total_char_limit=500, neighbor_chunks=1)
    assert len(result) == 2
    assert "primo frammento" in result[0]["text"] and "terzo frammento" in result[1]["text"]


def test_oversized_first_anchor_respects_global_budget(tmp_path):
    current = collection(tmp_path, [])
    result = expand_hierarchical_contexts(current, "documents", [anchor(text="x" * 1000)],
        section_char_limit=200, total_char_limit=100, neighbor_chunks=1)
    assert len(result[0]["text"]) <= 100
    assert result[0]["section_complete"] is False
