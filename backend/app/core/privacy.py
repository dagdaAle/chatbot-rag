"""Mandatory egress boundary for external chat. Never logs original content."""
from contextlib import contextmanager
from copy import deepcopy
import json
import logging
import re
import uuid

import requests

from app.config import settings

log = logging.getLogger(__name__)
TOKEN_RE = re.compile(r"<PII_[0-9a-f]{32}_[A-Z_]+_[1-9][0-9]*>")
TOKEN_FRAGMENT_RE = re.compile(r"PII_[0-9a-f]{8,}", re.IGNORECASE)
PRIVACY_INSTRUCTION = (
    "\nI segnaposto <PII_...> rappresentano valori protetti. Copiali esattamente, "
    "incluse le parentesi, senza modificarli, espanderli o inventarne altri. "
    "Cita i documenti con i riferimenti [Fonte N] forniti nel contesto."
)


class PrivacyError(RuntimeError):
    """Safe public error: must not contain upstream response bodies or secrets."""


def require_local_embeddings(provider: str) -> None:
    if provider != "ollama":
        raise PrivacyError("Gli embedding devono essere elaborati dal servizio locale.")


class ProtectedRequest:
    def __init__(self, session: requests.Session, mapping_id: str):
        self.session = session
        self.mapping_id = mapping_id
        self.tokens: set[str] = set()
        self.messages: list[dict] = []
        self.created = False

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        try:
            response = self.session.request(
                method, settings.anonymizer_url.rstrip("/") + path,
                json=body, timeout=(settings.anonymizer_connect_timeout, settings.anonymizer_read_timeout),
                allow_redirects=False,
            )
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError("Unexpected status")
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError("Unexpected response")
            return result
        except (requests.RequestException, ValueError, TypeError):
            raise PrivacyError("Servizio di protezione dei dati non disponibile. Riprova più tardi.") from None

    def protect(self, messages: list[dict]) -> None:
        texts = [message["content"] for message in messages]
        protected = self.protect_texts(texts)
        self.messages = [dict(message, content=text) for message, text in zip(messages, protected)]
        self.messages[0]["content"] += PRIVACY_INSTRUCTION

    def validate_tokens(self, text: str) -> None:
        mentioned = set(TOKEN_RE.findall(text))
        if not mentioned <= self.tokens or TOKEN_FRAGMENT_RE.search(TOKEN_RE.sub("", text)):
            raise PrivacyError("La risposta contiene riferimenti protetti non validi. Riprova.")

    def protect_texts(self, texts: list[str]) -> list[str]:
        if not texts or len(texts) > 64 or sum(map(len, texts)) > settings.anonymizer_max_chars:
            raise PrivacyError("La richiesta supera il limite del servizio di protezione dei dati.")
        for text in texts:
            self.validate_tokens(text)
        path = "/v1/protect/extend" if self.created else "/v1/protect"
        result = self.call("POST", path, {"mapping_id": self.mapping_id, "texts": texts})
        protected = result.get("texts")
        tokens = result.get("tokens")
        prefix = f"<PII_{uuid.UUID(self.mapping_id).hex}_"
        if (
            result.get("protocol_version") != 1 or result.get("mapping_id") != self.mapping_id
            or result.get("recognizers_complete") is not True
            or not isinstance(protected, list) or len(protected) != len(texts)
            or not all(isinstance(text, str) for text in protected)
            or not isinstance(tokens, list) or len(tokens) > 10000
            or not all(isinstance(token, str) and TOKEN_RE.fullmatch(token) and token.startswith(prefix) for token in tokens)
        ):
            raise PrivacyError("Risultato del servizio di protezione non valido. Invio annullato.")
        emitted_tokens = set(tokens)
        emitted = set(TOKEN_RE.findall("\n".join(protected)))
        if emitted != emitted_tokens:
            raise PrivacyError("Risultato del servizio di protezione non valido. Invio annullato.")
        if sum(map(len, protected)) > settings.anonymizer_max_chars:
            raise PrivacyError("Il testo protetto supera il limite della richiesta. Riduci il contesto.")
        self.tokens.update(emitted_tokens)
        if len(self.tokens) > 10000:
            raise PrivacyError("La ricerca supera il limite del servizio di protezione dei dati.")
        self.created = True
        return protected

    def protect_messages(self, messages: list[dict]) -> list[dict]:
        """Protect every free-text field in an agent transcript, preserving tool IDs."""
        output = deepcopy(messages)
        fields = []
        for message in output:
            for key in ("content", "reasoning_content"):
                if isinstance(message.get(key), str) and message[key]:
                    fields.append((message, key))
            for call in message.get("tool_calls") or []:
                try:
                    call["function"]["arguments"] = json.dumps(
                        json.loads(call["function"]["arguments"]), ensure_ascii=False)
                except (ValueError, TypeError):
                    pass  # Invalid arguments are still protected; tool validation rejects them.
                fields.append((call["function"], "arguments"))
        values = self.protect_texts([item[key] for item, key in fields])
        for (item, key), value in zip(fields, values):
            item[key] = value
        return output

    def restore(self, text: str) -> str:
        # Reject invented/cross-request tokens before sending them to the vault.
        self.validate_tokens(text)
        result = self.call("POST", "/v1/restore", {
            "mapping_id": self.mapping_id, "text": text, "allowed_tokens": sorted(self.tokens),
        })
        restored = result.get("text")
        if (
            result.get("protocol_version") != 1 or result.get("mapping_id") != self.mapping_id
            or not isinstance(restored, str) or TOKEN_FRAGMENT_RE.search(restored)
            or result.get("replaced") != len(TOKEN_RE.findall(text))
        ):
            raise PrivacyError("Non è stato possibile ripristinare la risposta protetta. Riprova.")
        return restored


@contextmanager
def protected_session():
    if not settings.anonymizer_token:
        raise PrivacyError("Servizio di protezione dei dati non configurato.")
    # One HTTP session per request: no cookies, proxies, redirects or shared map.
    with requests.Session() as session:
        session.trust_env = False
        session.headers["X-Anonymizer-Token"] = settings.anonymizer_token
        request = ProtectedRequest(session, str(uuid.uuid4()))
        try:
            yield request
        finally:
            try:
                request.call("DELETE", f"/mappings/{request.mapping_id}")
            except PrivacyError:
                # The service TTL handles crashes/timeouts; never log identifiers/content.
                log.warning("Privacy mapping cleanup deferred to service expiry")


@contextmanager
def protected_request(messages: list[dict]):
    with protected_session() as request:
        request.protect(messages)
        yield request
