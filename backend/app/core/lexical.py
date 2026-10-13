"""Sparse lexical vectors for hybrid Qdrant retrieval.

The encoder is deliberately local and deterministic: it hashes normalized terms
into Qdrant sparse dimensions. Qdrant applies corpus IDF at query time.
"""
from __future__ import annotations

from collections import Counter
from hashlib import blake2b
import math
import re
import unicodedata

from qdrant_client import models

LEXICAL_VECTOR_NAME = "lexical"
LEXICAL_INDEX_VERSION = 1

_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
_COMPOUND_IDENTIFIER_RE = re.compile(
    r"(?<!\w)(?=[A-Za-z0-9./_-]*\d)[A-Za-z0-9]+(?:[./_-][A-Za-z0-9]+)+(?!\w)"
)


def _normalized(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def _dimension(token: str) -> int:
    # Qdrant sparse dimensions are unsigned integers. A stable 32-bit hash keeps
    # the vocabulary independent from processes, hosts and Python versions.
    return int.from_bytes(blake2b(token.encode("utf-8"), digest_size=4).digest(), "big")


def lexical_terms(text: str) -> list[tuple[str, float]]:
    """Return normalized words plus strongly weighted complete identifiers."""
    normalized = _normalized(text)
    terms = [(f"word:{word}", 1.0) for word in _WORD_RE.findall(normalized)]

    # Keep references such as 123/2024, A-17/2025 and CUP/CIG-like compact codes
    # as one feature in addition to their component words and numbers.
    for match in _COMPOUND_IDENTIFIER_RE.finditer(normalized):
        compact = "".join(_WORD_RE.findall(match.group(0)))
        if compact:
            terms.append((f"identifier:{compact}", 3.0))
    return terms


def sparse_text_vector(text: str) -> models.SparseVector:
    """Encode text as a sorted sparse vector suitable for Qdrant IDF scoring."""
    weighted_counts: Counter[int] = Counter()
    for term, weight in lexical_terms(text):
        weighted_counts[_dimension(term)] += weight

    indices = sorted(weighted_counts)
    values = [1.0 + math.log(weighted_counts[index]) for index in indices]
    return models.SparseVector(indices=indices, values=values)


def hybrid_vector(dense: list[float], text: str) -> dict[str, object]:
    vector: dict[str, object] = {"": dense}
    sparse = sparse_text_vector(text)
    if sparse.indices:
        vector[LEXICAL_VECTOR_NAME] = sparse
    return vector
