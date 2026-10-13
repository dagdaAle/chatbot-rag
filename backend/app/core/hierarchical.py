"""Expand retrieved anchors to their structural section or local neighborhood."""
from __future__ import annotations

import logging

from qdrant_client import models

logger = logging.getLogger(__name__)


def _scroll_document(client, collection_name: str, document_id: str) -> list[dict]:
    chunks: list[dict] = []
    offset = None
    while True:
        records, offset = client.scroll(
            collection_name=collection_name,
            scroll_filter=models.Filter(must=[
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchValue(value=document_id),
                )
            ]),
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        chunks.extend(dict(record.payload or {}) for record in records)
        if offset is None:
            return chunks


def _centered_chunks(chunks: list[dict], anchor_index: int, char_limit: int) -> tuple[list[dict], bool]:
    ordered = sorted(chunks, key=lambda chunk: int(chunk.get("chunk_index", 0)))
    if not ordered:
        return [], False
    total = sum(len(str(chunk.get("text", ""))) + 2 for chunk in ordered)
    if total <= char_limit:
        return ordered, True

    anchor_position = min(
        range(len(ordered)),
        key=lambda position: abs(int(ordered[position].get("chunk_index", 0)) - anchor_index),
    )
    left = right = anchor_position
    used = len(str(ordered[anchor_position].get("text", "")))
    blocked_left = blocked_right = False
    while not (blocked_left and blocked_right):
        candidates = []
        if left > 0 and not blocked_left:
            candidates.append(left - 1)
        else:
            blocked_left = True
        if right + 1 < len(ordered) and not blocked_right:
            candidates.append(right + 1)
        else:
            blocked_right = True
        if not candidates:
            break
        position = min(candidates, key=lambda item: (abs(item - anchor_position), item))
        size = len(str(ordered[position].get("text", ""))) + 2
        if used + size <= char_limit:
            used += size
            if position < anchor_position:
                left = position
            else:
                right = position
        elif position < anchor_position:
            blocked_left = True
        else:
            blocked_right = True
    return ordered[left:right + 1], left == 0 and right == len(ordered) - 1


def _without_repeated_heading(text: str, section_path: list[str]) -> str:
    heading = " > ".join(section_path)
    if heading and text.startswith(heading):
        return text[len(heading):].lstrip()
    return text


def _append_without_overlap(current: str, addition: str) -> str:
    if not current:
        return addition
    max_overlap = min(400, len(current), len(addition))
    for size in range(max_overlap, 39, -1):
        if current[-size:] == addition[:size]:
            return current + addition[size:]
    return current + "\n\n" + addition


def _combine(anchor: dict, chunks: list[dict], *, scope: str, complete: bool) -> dict:
    section_path = list(anchor.get("section_path") or [])
    text = ""
    regions = []
    pages = []
    kinds = set()
    for position, chunk in enumerate(chunks):
        part = str(chunk.get("text", ""))
        if position and section_path:
            part = _without_repeated_heading(part, section_path)
        text = _append_without_overlap(text, part)
        regions.extend(chunk.get("source_regions") or [])
        pages.extend([chunk.get("page_start"), chunk.get("page_end")])
        kinds.add(chunk.get("content_kind", "text"))
    valid_pages = [int(page) for page in pages if page is not None]
    return {
        **anchor,
        "text": text,
        "chunk_index": min(int(chunk.get("chunk_index", 0)) for chunk in chunks),
        "page_start": min(valid_pages) if valid_pages else anchor.get("page_start", 1),
        "page_end": max(valid_pages) if valid_pages else anchor.get("page_end", 1),
        "source_regions": regions,
        "content_kind": next(iter(kinds)) if len(kinds) == 1 else "mixed",
        "context_scope": scope,
        "section_complete": complete,
        "expanded_chunks": len(chunks),
    }


def expand_hierarchical_contexts(
    client,
    collection_name: str,
    anchors: list[dict],
    *,
    section_char_limit: int,
    total_char_limit: int,
    neighbor_chunks: int,
) -> list[dict]:
    """Expand ranked anchors while preserving their order and a global budget."""
    document_cache: dict[str, list[dict]] = {}
    expanded: list[dict] = []
    seen_scopes: set[tuple] = set()
    used = 0

    for anchor in anchors:
        document_id = str(anchor.get("document_id", ""))
        section_path = list(anchor.get("section_path") or [])
        section_refs = list(anchor.get("section_refs") or [])
        anchor_index = int(anchor.get("chunk_index", 0))
        if not document_id:
            candidate = {**anchor, "context_scope": "chunk", "section_complete": False, "expanded_chunks": 1}
        else:
            if document_id not in document_cache:
                try:
                    document_cache[document_id] = _scroll_document(client, collection_name, document_id)
                except Exception:
                    logger.exception("Impossibile espandere il documento %s", document_id)
                    document_cache[document_id] = []
            document_chunks = document_cache[document_id]

            if section_refs or section_path:
                section_identity = tuple(section_refs) if section_refs else tuple(section_path)
                scope_key = (document_id, "section", section_identity)
                relevant = [
                    chunk for chunk in document_chunks
                    if (
                        list(chunk.get("section_refs") or []) == section_refs
                        if section_refs else
                        list(chunk.get("section_path") or []) == section_path
                    )
                ]
                scope = "section"
            else:
                relevant = [
                    chunk for chunk in document_chunks
                    if abs(int(chunk.get("chunk_index", 0)) - anchor_index) <= neighbor_chunks
                ]
                scope_key = (
                    document_id,
                    "neighbors",
                    tuple(sorted(int(chunk.get("chunk_index", 0)) for chunk in relevant)),
                )
                scope = "neighbors"

            if scope_key in seen_scopes:
                continue
            seen_scopes.add(scope_key)
            remaining = total_char_limit - used
            if remaining <= 0:
                break
            chosen, complete = _centered_chunks(
                relevant,
                anchor_index,
                min(section_char_limit, remaining),
            )
            candidate = (
                _combine(anchor, chosen, scope=scope, complete=complete and scope == "section")
                if chosen else
                {**anchor, "context_scope": "chunk", "section_complete": False, "expanded_chunks": 1}
            )

        size = len(str(candidate.get("text", "")))
        if expanded and used + size > total_char_limit:
            continue
        expanded.append(candidate)
        used += size
        if used >= total_char_limit:
            break
    return expanded
