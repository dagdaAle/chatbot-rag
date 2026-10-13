"""Typed price extraction, versioning and deterministic queries."""
from decimal import Decimal

from app.core import price_lists


def structure(prices=("12,50", "21,00"), second_price_column=False):
    header = ["Codice", "Descrizione", "Prezzo EUR", "Unità"]
    rows = [
        ["001-A", "Prodotto primo", prices[0], "kg"],
        ["001/B", "Prodotto secondo", prices[1], "pezzo"],
    ]
    if second_price_column:
        header.insert(3, "Prezzo ingrosso EUR")
        rows[0].insert(3, "10,00")
        rows[1].insert(3, "18,00")
    return {"blocks": [{
        "id": "#/tables/0",
        "kind": "table",
        "rows": [
            {"row_index": 0, "cells": header, "is_header": True},
            *[
                {"row_index": index + 1, "cells": row, "is_header": False}
                for index, row in enumerate(rows)
            ],
        ],
        "source_regions": [{"item_ref": "#/tables/0", "page": 3,
                            "bbox": {"l": 10, "t": 100, "r": 200, "b": 50, "coord_origin": "BOTTOMLEFT"}}],
    }]}


def isolated_db(monkeypatch, tmp_path):
    monkeypatch.setattr(price_lists, "PRICE_DB", tmp_path / "prices.sqlite")


def test_decimal_parser_is_exact_and_rejects_text():
    assert price_lists.parse_decimal("€ 1.234,56") == Decimal("1234.56")
    assert price_lists.parse_decimal("1,234.56 USD") == Decimal("1234.56")
    assert price_lists.parse_decimal("12,50 circa") is None
    assert price_lists.parse_decimal("") is None
    assert price_lists.plan_price_question("Quanto costa il codice 00123?").codes == ("00123",)


def test_indexes_every_explicit_price_column_with_raw_provenance(monkeypatch, tmp_path):
    isolated_db(monkeypatch, tmp_path)
    count = price_lists.index_price_document(
        structure(second_price_column=True), "kb-1", "doc-1", "Listino materiali 2025.pdf",
    )

    assert count == 4
    result = price_lists.query_price_lists("Quanto costa 001-A?", "kb-1")
    assert result and result["intent"] == "lookup"
    assert result["rows_matched"] == 2
    assert "12,50 EUR" in result["answer"]
    assert result["sources"][0]["raw_cells"]["0:Codice"] == "001-A"
    assert result["sources"][0]["page_start"] == 3
    assert result["sources"][0]["verified_data"] is True


def test_count_and_comparison_use_typed_values_and_versions(monkeypatch, tmp_path):
    isolated_db(monkeypatch, tmp_path)
    price_lists.index_price_document(structure(), "kb-1", "doc-2025", "Listino materiali 2025.pdf")
    price_lists.index_price_document(structure(("15,00", "19,00")), "kb-1", "doc-2026", "Listino materiali 2026.pdf")

    count = price_lists.query_price_lists("Quanti prodotti costano meno di 20 euro nel 2025?", "kb-1")
    assert count and "**1 riga di listino**" in count["answer"]

    comparison = price_lists.query_price_lists("Confronta il prezzo di 001-A tra 2025 e 2026", "kb-1")
    assert comparison and comparison["intent"] == "compare"
    assert "12,50 EUR" in comparison["answer"]
    assert "15,00 EUR" in comparison["answer"]
    assert "2,50 EUR (20,00%)" in comparison["answer"]
    assert [source["version_label"] for source in comparison["sources"]] == ["2025", "2026"]

    follow_up = price_lists.query_price_lists(
        "Quanto costa 001-A?\ne nel 2025?\ne nel 2026?",
        "kb-1",
        current_question="e nel 2026?",
    )
    assert follow_up and follow_up["rows_matched"] == 1
    assert "15,00 EUR" in follow_up["answer"] and "12,50 EUR" not in follow_up["answer"]


def test_non_price_tables_and_unrelated_questions_do_not_trigger(monkeypatch, tmp_path):
    isolated_db(monkeypatch, tmp_path)
    no_prices = structure()
    no_prices["blocks"][0]["rows"][0]["cells"][2] = "Note"
    assert price_lists.index_price_document(no_prices, "kb-1", "doc-1", "Allegato.pdf") == 0
    assert price_lists.query_price_lists("Riassumi il regolamento", "kb-1") is None
    assert price_lists.plan_price_question("Importa un documento") is None
    assert price_lists.query_price_lists("Qual è il prezzo?", "kb-1") is None


def test_version_metadata_groups_clear_filename_versions():
    first = price_lists._version_metadata("Listino materiali 2025.pdf")
    second = price_lists._version_metadata("Listino materiali 2026-10-01.pdf")
    revision = price_lists._version_metadata("Listino materiali rev2.pdf")

    assert first == ("listino materiali", "2025", None)
    assert second == ("listino materiali", "2026-10-01", "2026-10-01")
    assert revision == ("listino materiali", "REV2", None)


def test_reindex_replaces_document_rows_atomically(monkeypatch, tmp_path):
    isolated_db(monkeypatch, tmp_path)
    price_lists.index_price_document(structure(), "kb-1", "doc-1", "Listino 2025.pdf")
    price_lists.index_price_document(structure(("9,00", "8,00")), "kb-1", "doc-1", "Listino 2025.pdf")

    result = price_lists.query_price_lists("Quanto costa 001-A?", "kb-1")
    assert result and result["rows_matched"] == 1
    assert "9,00 EUR" in result["answer"]
    assert "12,50" not in result["answer"]

    price_lists.delete_price_document("doc-1")
    assert price_lists.query_price_lists("Quanto costa 001-A?", "kb-1") is None


def test_chat_uses_deterministic_structured_answer_without_llm(monkeypatch):
    from app.core import chat
    structured_source = {
        "filename": "listino.pdf", "document_id": "doc", "text": "001-A | 12,50",
        "chunk_index": 1, "page_start": 3, "page_end": 3, "score": 1.0,
        "verified_data": True, "retrieval_method": "structured_price",
    }
    monkeypatch.setattr(chat, "query_price_lists", lambda *args, **kwargs: {
        "answer": "Il prezzo verificato è 12,50 EUR [1]", "sources": [structured_source],
        "rows_matched": 1, "intent": "lookup",
    })
    monkeypatch.setattr(chat, "retrieve_context", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("RAG non necessario")))
    monkeypatch.setattr(chat, "generate_response", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("LLM non necessario")))

    result = chat.chat("Quanto costa 001-A?", knowledge_id="kb-1")

    assert result["answer"] == "Il prezzo verificato è 12,50 EUR [1]"
    assert result["sources"][0]["verified_data"] is True
    assert result["structured_intent"] == "lookup"
