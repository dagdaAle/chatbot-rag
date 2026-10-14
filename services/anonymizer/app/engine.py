"""Analisi (Presidio + regole italiane + GLiNER) e sostituzione."""
import re
from dataclasses import dataclass

from presidio_analyzer import AnalyzerEngine, RecognizerRegistry, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider

from app.recognizers.gliner_ner import LABELS, GlinerRecognizer
from app.recognizers.italian import build_italian_recognizers
from app.vault import Vault, normalize

PATTERN_ENTITIES = [
    "CODICE_FISCALE", "PARTITA_IVA", "IBAN", "EMAIL", "TELEFONO", "TARGA",
]
ALL_ENTITIES = PATTERN_ENTITIES + list(LABELS.values())

# Legacy tokens require their delimiters too. New tokens have a request namespace.
_TOKEN_RE = re.compile(r"<(?:PII_[0-9a-f]{32}_)?(?:" + "|".join(ALL_ENTITIES) + r")_[1-9][0-9]*>")


@dataclass
class Found:
    entity_type: str
    start: int
    end: int
    score: float
    replacement: str


def _drop_overlaps(results: list[RecognizerResult]) -> list[RecognizerResult]:
    """Tra entità sovrapposte tiene la più affidabile (a pari score, la più lunga)."""
    kept: list[RecognizerResult] = []
    for r in sorted(results, key=lambda r: (-r.score, -(r.end - r.start))):
        if all(r.end <= k.start or r.start >= k.end for k in kept):
            kept.append(r)
    return sorted(kept, key=lambda r: r.start)


class Anonymizer:
    def __init__(self, vault: Vault, gliner: GlinerRecognizer | None, spacy_model: str) -> None:
        self.vault = vault
        registry = RecognizerRegistry(supported_languages=["it"])
        for rec in build_italian_recognizers():
            registry.add_recognizer(rec)
        if gliner is not None:
            registry.add_recognizer(gliner)
        # spaCy serve solo per tokenizzazione e lemmi (contesto delle regole):
        # il suo NER non è registrato, i nomi li trova GLiNER.
        nlp_engine = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "it", "model_name": spacy_model}],
            "ner_model_configuration": {"labels_to_ignore": ["PER", "LOC", "ORG", "MISC"]},
        }).create_engine()
        self.available = [
            e for e in ALL_ENTITIES
            if gliner is not None or e in PATTERN_ENTITIES
        ]
        self.analyzer = AnalyzerEngine(
            registry=registry, nlp_engine=nlp_engine, supported_languages=["it"],
        )

    def analyze(
        self, text: str, entities: list[str] | None, threshold: float,
    ) -> list[RecognizerResult]:
        results = self.analyzer.analyze(
            text=text, language="it", entities=entities or self.available,
            score_threshold=threshold,
        )
        return _drop_overlaps(results)

    def anonymize(
        self,
        text: str,
        mode: str,
        mapping_id: str | None,
        entities: list[str] | None = None,
        threshold: float = 0.5,
    ) -> tuple[str, str | None, list[Found]]:
        results = self.analyze(text, entities, threshold)
        if mode == "pseudo":
            mapping_id = self.vault.ensure_mapping(mapping_id)

        found: list[Found] = []
        out: list[str] = []
        cursor = 0
        for r in results:
            value = text[r.start:r.end]
            if mode == "pseudo":
                repl = self.vault.token_for(mapping_id, r.entity_type, value)
            else:
                repl = f"<{r.entity_type}>"
            out.append(text[cursor:r.start])
            out.append(repl)
            cursor = r.end
            found.append(Found(r.entity_type, r.start, r.end, round(r.score, 3), repl))
        out.append(text[cursor:])
        return "".join(out), (mapping_id if mode == "pseudo" else None), found

    def protect_batch(self, texts: list[str], mapping_id: str, threshold: float) -> tuple[list[str], list[str]]:
        # Analyze all fields before replacement, so a name recognized only in a
        # later source is also replaced in an earlier question/history message.
        # Preserve already emitted placeholders across agent research steps.
        # Equal-length masking keeps detector offsets aligned with the source.
        analyses = [self.analyze(_TOKEN_RE.sub(lambda m: " " * len(m.group()), text), None, threshold)
                    for text in texts]
        for text, results in zip(texts, analyses):
            for result in results:
                self.vault.token_for(mapping_id, result.entity_type, text[result.start:result.end])
        table = self.vault.lookup(mapping_id)
        if not table:
            return list(texts), []
        values = {}
        for token, value in table.items():
            values.setdefault(normalize(value), token)
        patterns = []
        for value in sorted(values, key=len, reverse=True):
            pattern = r"\s+".join(re.escape(part) for part in value.split())
            patterns.append((r"(?<!\w)" if value[0].isalnum() else "") + pattern + (r"(?!\w)" if value[-1].isalnum() else ""))
        matcher = re.compile("|".join(patterns), re.IGNORECASE)
        emitted = set(_TOKEN_RE.findall("\n".join(texts)))
        protected = []
        for text, detected in zip(texts, analyses):
            token_spans = [(match.start(), match.end()) for match in _TOKEN_RE.finditer(text)]
            # Known exact occurrences win over shorter overlapping detections.
            replacements = [
                (match.start(), match.end(), values[normalize(match.group())])
                for match in matcher.finditer(text)
                if all(match.end() <= start or match.start() >= end for start, end in token_spans)
            ]
            for result in detected:
                if all(result.end <= start or result.start >= end for start, end, _ in replacements):
                    replacements.append((result.start, result.end, self.vault.token_for(
                        mapping_id, result.entity_type, text[result.start:result.end])))
            out, cursor = [], 0
            for start, end, token in sorted(replacements):
                out.extend((text[cursor:start], token))
                cursor = end
                emitted.add(token)
            out.append(text[cursor:])
            protected.append("".join(out))
        return protected, sorted(emitted)

    def deanonymize(self, text: str, mapping_id: str, allowed_tokens: set[str] | None = None) -> tuple[str, int]:
        table = self.vault.lookup(mapping_id)
        replaced = 0

        def sub(m: re.Match) -> str:
            nonlocal replaced
            token = m.group(0)
            value = table.get(token) if allowed_tokens is None or token in allowed_tokens else None
            if value is None:
                return m.group(0)
            replaced += 1
            return value

        return _TOKEN_RE.sub(sub, text), replaced
