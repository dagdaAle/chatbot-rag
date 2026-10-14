"""Nomi, organizzazioni, luoghi e indirizzi con GLiNER (zero-shot, su GPU).

Finestre sovrapposte, limitate dai tokenizzatori del modello, con offset
riportati sul testo originale.
"""
import logging

from presidio_analyzer import EntityRecognizer, RecognizerResult

log = logging.getLogger(__name__)

# Etichetta in linguaggio naturale passata al modello → entità Presidio.
LABELS = {
    "person": "PERSONA",
    "organization": "ORGANIZZAZIONE",
    "address": "INDIRIZZO",
    "location": "LUOGO",
    "date of birth": "DATA_NASCITA",
}

class GlinerRecognizer(EntityRecognizer):
    def __init__(self, model_name: str, device: str, threshold: float = 0.5) -> None:
        self.model_name = model_name
        self.device = device
        self.threshold = threshold
        self.model = None
        super().__init__(
            supported_entities=list(LABELS.values()),
            supported_language="it",
            name="GlinerRecognizer",
        )

    def load(self) -> None:
        if self.model is not None:
            return
        from gliner import GLiNER

        log.info("Carico %s su %s", self.model_name, self.device)
        self.model = GLiNER.from_pretrained(self.model_name).to(self.device)
        self.model.eval()

    def _model_windows(self, text):
        # GLiNER truncates by word count and transformer subword tokens. Use
        # both actual tokenizers, with overlap, instead of estimating characters.
        words = list(self.model.data_processor.words_splitter(text))
        if not words:
            if text:
                yield 0, text
            return
        tokenizer = self.model.data_processor.transformer_tokenizer
        max_words = min(256, int(self.model.config.max_len))
        start = 0
        while start < len(words):
            end = min(start + max_words, len(words))
            offset = words[start][1]
            chunk = text[offset:words[end - 1][2]]
            # Leave ample capacity for label prompts and special tokens.
            while len(tokenizer.encode(chunk, add_special_tokens=False)) > 320 and end > start + 1:
                end = start + max(1, (end - start) // 2)
                chunk = text[offset:words[end - 1][2]]
            if len(tokenizer.encode(chunk, add_special_tokens=False)) > 320:
                raise ValueError("An individual token exceeds the recognition window")
            yield offset, chunk
            if end == len(words):
                break
            start = max(start + 1, end - min(40, (end - start) // 4))

    def analyze(self, text, entities, nlp_artifacts=None):
        wanted = {lbl: ent for lbl, ent in LABELS.items() if ent in entities}
        if not wanted:
            return []
        if self.model is None:
            raise RuntimeError("GLiNER not loaded")

        results = []
        for offset, chunk in self._model_windows(text):
            spans = self.model.predict_entities(
                chunk, list(wanted), threshold=self.threshold, flat_ner=True,
            )
            for span in spans:
                results.append(RecognizerResult(
                    entity_type=wanted[span["label"]],
                    start=offset + span["start"],
                    end=offset + span["end"],
                    score=float(span["score"]),
                ))
        return results
