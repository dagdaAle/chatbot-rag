"""Text-only OpenAI egress boundary. No unprotected fallback and no content logs."""
from __future__ import annotations

from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import dataclass
import hmac
import json
import logging
import os
import re
import time
import uuid
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

TOKEN = re.compile(r"<PII_[0-9a-f]{32}_[A-Z_]+_[1-9][0-9]*>")
FRAGMENT = re.compile(r"PII_", re.I)
NAME = re.compile(r"[a-zA-Z0-9_-]{1,128}\Z")
# Public protocol constant from the pinned Open WebUI v0.12.5 builtin tools.
# GLiNER can classify this literal as a username. Exempt only the function-name
# slot, never message text, argument values, JSON keys or arbitrary identifiers.
PUBLIC_TOOL_NAMES = frozenset({"ask_user"})
# Public calendar schema property names in the same pinned release. These are
# labels, not their values; all location/rrule text values still get protected.
PUBLIC_STRUCTURAL_KEYS = frozenset({"location", "rrule"})
GUIDANCE = "I valori tra parentesi angolari che iniziano con PII sono segnaposto protetti: copiali esattamente e integralmente, senza inventarli o modificarli."
log = logging.getLogger("intecha.gateway")


class GatewayError(Exception):
    def __init__(self, status=503, message="Protezione o modello non disponibile. Riprova."):
        self.status, self.message = status, message


@dataclass(frozen=True)
class Settings:
    gateway_key: str
    anonymizer_token: str
    provider_key: str
    anonymizer_url: str = "http://anonymizer:8000"
    provider_url: str = "https://api.deepseek.com"
    models: tuple[str, ...] = ("deepseek-flash",)
    max_chars: int = 180000
    max_bytes: int = 1500000
    max_response_bytes: int = 1500000
    timeout: float = 180

    @classmethod
    def from_env(cls):
        return cls(
            gateway_key=os.environ.get("GATEWAY_API_KEY", ""),
            anonymizer_token=os.environ.get("ANONYMIZER_TOKEN", ""),
            provider_key=os.environ.get("DEEPSEEK_API_KEY", ""),
            anonymizer_url=os.environ.get("ANONYMIZER_URL", "http://anonymizer:8000"),
            models=tuple(x.strip() for x in os.environ.get("GATEWAY_MODELS", "deepseek-flash").split(",") if x.strip()),
        )

    def validate(self):
        if not all((self.gateway_key, self.anonymizer_token, self.provider_key, self.models)):
            raise RuntimeError("Credenziali gateway obbligatorie")
        # This service intentionally has no user-selectable upstream URL.
        if self.provider_url != "https://api.deepseek.com":
            raise RuntimeError("Provider non consentito")
        u = urlsplit(self.anonymizer_url)
        if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password or u.query or u.fragment:
            raise RuntimeError("URL Anonymizer non valido")


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def walk_strings(value, fields):
    """All free-text leaf values, including tool schema descriptions/enums."""
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, str):
                if item:
                    fields.append((value, key))
            else:
                walk_strings(item, fields)
    elif isinstance(value, list):
        for key, item in enumerate(value):
            if isinstance(item, str):
                if item:
                    fields.append((value, key))
            else:
                walk_strings(item, fields)


def arguments(value):
    if not isinstance(value, str):
        raise GatewayError(400, "Argomenti strumento non validi.")
    try:
        parsed = json.loads(value)
    except (ValueError, RecursionError):
        raise GatewayError(400, "Argomenti strumento non validi.") from None
    if not isinstance(parsed, dict):
        raise GatewayError(400, "Argomenti strumento non validi.")
    return parsed


def prepare(body, settings):
    allowed = {"model", "messages", "tools", "tool_choice", "parallel_tool_calls", "temperature",
               "top_p", "max_tokens", "max_completion_tokens", "presence_penalty", "frequency_penalty",
               "seed", "stop", "response_format", "stream", "stream_options", "thinking", "reasoning_effort",
               "logprobs", "top_logprobs", "n", "user"}
    if not isinstance(body, dict) or set(body) - allowed:
        raise GatewayError(400, "Parametro non supportato dal gateway protetto.")
    if body.get("model") not in settings.models:
        raise GatewayError(400, "Modello non consentito.")
    if not isinstance(body.get("stream", False), bool) or body.get("n", 1) != 1:
        raise GatewayError(400, "Configurazione risposta non supportata.")
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages or len(messages) > 256:
        raise GatewayError(400, "Cronologia non valida.")
    output = {key: deepcopy(value) for key, value in body.items() if value is not None}
    # Never forward account identities, provider stream controls, or usage metadata.
    output.pop("user", None)
    output.pop("stream_options", None)
    output["stream"] = False
    output.setdefault("thinking", {"type": "disabled"})
    fields, argument_fields = [], []
    invariant_fields = {}

    def audit_identifier(value, *, tool_name=False):
        if tool_name and value in PUBLIC_TOOL_NAMES:
            return
        if value not in invariant_fields:
            holder = {"value": value}
            invariant_fields[value] = holder
            fields.append((holder, "value"))

    def audit_keys(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key not in PUBLIC_STRUCTURAL_KEYS:
                    audit_identifier(key)
                audit_keys(item)
        elif isinstance(value, list):
            for item in value:
                audit_keys(item)
    def walk_schema_strings(value):
        # JSON Schema `required` entries reference property keys. Audit them as
        # invariants rather than rewriting them independently of those keys.
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "required" and isinstance(item, list) and all(isinstance(x, str) for x in item):
                    for name in item:
                        if name not in PUBLIC_STRUCTURAL_KEYS:
                            audit_identifier(name)
                elif isinstance(item, str):
                    if item:
                        fields.append((value, key))
                else:
                    walk_schema_strings(item)
        elif isinstance(value, list):
            for key, item in enumerate(value):
                if isinstance(item, str):
                    if item:
                        fields.append((value, key))
                else:
                    walk_schema_strings(item)

    for msg in output["messages"]:
        if not isinstance(msg, dict) or set(msg) - {"role", "content", "reasoning_content", "tool_calls", "tool_call_id", "name"}:
            raise GatewayError(400, "Messaggio non supportato.")
        if msg.get("role") not in {"system", "developer", "user", "assistant", "tool"}:
            raise GatewayError(400, "Ruolo non supportato.")
        for key in ("tool_call_id", "name"):
            if key in msg and (not isinstance(msg[key], str) or not NAME.fullmatch(msg[key])):
                raise GatewayError(400, "Identificativo strumento non valido.")
        for key in ("tool_call_id", "name"):
            if key in msg:
                audit_identifier(msg[key])
        content = msg.get("content")
        if isinstance(content, list):
            # OCR/extraction happens locally. Images/audio/URLs never bypass text protection.
            for part in content:
                if not isinstance(part, dict) or set(part) != {"type", "text"} or part["type"] != "text" or not isinstance(part["text"], str):
                    raise GatewayError(400, "Sono supportati solo documenti estratti in testo, senza immagini o audio.")
                if part["text"]:
                    fields.append((part, "text"))
        elif content is not None and not isinstance(content, str):
            raise GatewayError(400, "Contenuto non supportato.")
        elif content:
            fields.append((msg, "content"))
        if "reasoning_content" in msg:
            if not isinstance(msg["reasoning_content"], str):
                raise GatewayError(400, "Ragionamento non supportato.")
            if msg["reasoning_content"]:
                fields.append((msg, "reasoning_content"))
        calls = msg.get("tool_calls") or []
        if not isinstance(calls, list):
            raise GatewayError(400)
        for call in calls:
            if (not isinstance(call, dict) or set(call) - {"id", "type", "function"}
                or call.get("type") != "function" or not NAME.fullmatch(str(call.get("id", "")))):
                raise GatewayError(400, "Chiamata strumento non valida.")
            fn = call.get("function")
            if not isinstance(fn, dict) or set(fn) != {"name", "arguments"} or not NAME.fullmatch(str(fn.get("name", ""))):
                raise GatewayError(400, "Funzione non valida.")
            audit_identifier(call["id"])
            audit_identifier(fn["name"], tool_name=True)
            parsed = arguments(fn["arguments"])
            audit_keys(parsed)
            walk_strings(parsed, fields)
            argument_fields.append((fn, parsed))
    tools = output.get("tools") or []
    if not isinstance(tools, list) or len(tools) > 64:
        raise GatewayError(400, "Troppi strumenti.")
    for tool in tools:
        if not isinstance(tool, dict) or set(tool) != {"type", "function"} or tool["type"] != "function":
            raise GatewayError(400, "Tipo strumento non supportato.")
        fn = tool["function"]
        if not isinstance(fn, dict) or set(fn) - {"name", "description", "parameters", "strict"} or not NAME.fullmatch(str(fn.get("name", ""))):
            raise GatewayError(400, "Definizione strumento non valida.")
        audit_identifier(fn["name"], tool_name=True)
        for key in ("description",):
            if key in fn:
                if not isinstance(fn[key], str):
                    raise GatewayError(400)
                if fn[key]:
                    fields.append((fn, key))
        if "parameters" in fn:
            if not isinstance(fn["parameters"], dict):
                raise GatewayError(400)
            audit_keys(fn["parameters"])
            walk_schema_strings(fn["parameters"])
    choice = output.get("tool_choice")
    if isinstance(choice, dict):
        fn = choice.get("function")
        if set(choice) != {"type", "function"} or choice["type"] != "function" or not isinstance(fn, dict) or set(fn) != {"name"} or fn["name"] not in {t["function"]["name"] for t in tools}:
            raise GatewayError(400, "Selezione strumento non valida.")
    elif choice is not None and choice not in ("auto", "none", "required"):
        raise GatewayError(400)
    for key in ("response_format", "stop"):
        if key in output:
            if isinstance(output[key], str):
                fields.append((output, key))
            else:
                audit_keys(output[key])
                if key == "response_format":
                    walk_schema_strings(output[key])
                else:
                    walk_strings(output[key], fields)
    # Free text is allowed only in the explicitly protected structures above.
    for key, value in output.items():
        if key in {"messages", "tools", "response_format", "stop", "tool_choice", "model"}:
            continue
        if key == "thinking":
            if not isinstance(value, dict) or value not in ({"type": "enabled"}, {"type": "disabled"}):
                raise GatewayError(400)
        elif key == "reasoning_effort":
            if value not in ("none", "low", "medium", "high"):
                raise GatewayError(400)
        elif not isinstance(value, (int, float, bool)):
            raise GatewayError(400, "Parametro non supportato.")
    if not fields or sum(len(item[key]) for item, key in fields) > settings.max_chars:
        raise GatewayError(413, "Contesto troppo grande per la protezione. Riduci i documenti o la cronologia.")
    return output, fields, argument_fields, invariant_fields


class Protection:
    def __init__(self, client, settings):
        self.client, self.settings = client, settings
        self.mapping = str(uuid.uuid4())
        self.tokens = set()
        self.created = False

    async def call(self, method, path, body=None):
        try:
            response = await self.client.request(method, self.settings.anonymizer_url.rstrip("/") + path,
                headers={"X-Anonymizer-Token": self.settings.anonymizer_token}, json=body,
                timeout=120, follow_redirects=False)
            if response.status_code != 200:
                raise GatewayError()
            value = response.json()
            if not isinstance(value, dict):
                raise GatewayError()
            return value
        except (httpx.HTTPError, ValueError, TypeError):
            raise GatewayError() from None

    def validate(self, text):
        if not set(TOKEN.findall(text)) <= self.tokens or FRAGMENT.search(TOKEN.sub("", text)):
            raise GatewayError(502, "Risposta con segnaposto non validi. Riprova.")

    async def protect(self, fields):
        # One mapping for the whole HTTP call; batches support many tool descriptions.
        # A second pass propagates entities discovered in later batches to earlier fields.
        batches = [fields[i:i+64] for i in range(0, len(fields), 64)]
        for _ in range(2 if len(batches) > 1 else 1):
            for batch in batches:
                texts = [container[key] for container, key in batch]
                for text in texts:
                    self.validate(text)
                result = await self.call("POST", "/v1/protect/extend" if self.created else "/v1/protect",
                                         {"mapping_id": self.mapping, "texts": texts})
                protected, tokens = result.get("texts"), result.get("tokens")
                prefix = "<PII_" + uuid.UUID(self.mapping).hex + "_"
                if (result.get("protocol_version") != 1 or result.get("mapping_id") != self.mapping
                    or result.get("recognizers_complete") is not True or not isinstance(protected, list)
                    or len(protected) != len(texts) or not all(isinstance(t, str) for t in protected)
                    or not isinstance(tokens, list) or len(tokens) > 10000
                    or not all(isinstance(t, str) and TOKEN.fullmatch(t) and t.startswith(prefix) for t in tokens)
                    or set(TOKEN.findall("\n".join(protected))) != set(tokens)):
                    raise GatewayError()
                self.tokens.update(tokens)
                self.created = True
                if len(self.tokens) > 10000:
                    raise GatewayError(413)
                for (container, key), text in zip(batch, protected):
                    self.validate(text)
                    container[key] = text
        if sum(len(item[key]) for item, key in fields) > 200000:
            raise GatewayError(413, "Contesto protetto troppo grande.")

    async def restore(self, text):
        self.validate(text)
        if not TOKEN.search(text):
            return text
        result = await self.call("POST", "/v1/restore", {
            "mapping_id": self.mapping, "text": text, "allowed_tokens": sorted(self.tokens)})
        restored = result.get("text")
        if (result.get("protocol_version") != 1 or result.get("mapping_id") != self.mapping
            or not isinstance(restored, str) or FRAGMENT.search(restored)
            or result.get("replaced") != len(TOKEN.findall(text))):
            raise GatewayError()
        return restored

    async def cleanup(self):
        try:
            response = await self.client.delete(self.settings.anonymizer_url.rstrip("/") + "/mappings/" + self.mapping,
                headers={"X-Anonymizer-Token": self.settings.anonymizer_token}, timeout=10, follow_redirects=False)
            if response.status_code not in (200, 404):
                log.warning("Pulizia mappa rinviata al TTL")
        except httpx.HTTPError:
            log.warning("Pulizia mappa rinviata al TTL")


async def restored_completion(raw, protection, model, tool_names):
    try:
        choices = raw["choices"]
        if not isinstance(choices, list) or len(choices) != 1:
            raise GatewayError(502)
        source = choices[0]
        if source.get("finish_reason") not in ("stop", "tool_calls", "length", "content_filter"):
            raise GatewayError(502)
        msg = source["message"]
        result = {"role": "assistant", "content": None}
        for key in ("content", "reasoning_content", "refusal"):
            value = msg.get(key)
            if value is not None:
                if not isinstance(value, str):
                    raise GatewayError(502)
                result[key] = await protection.restore(value)
        calls = msg.get("tool_calls") or []
        if not isinstance(calls, list) or len(calls) > 64:
            raise GatewayError(502)
        if calls:
            result["tool_calls"] = []
            for call in calls:
                fn = call["function"]
                if (call.get("type") != "function" or not NAME.fullmatch(str(call.get("id", "")))
                    or fn["name"] not in tool_names):
                    raise GatewayError(502, "Strumento restituito non consentito.")
                parsed = arguments(fn["arguments"])
                async def restore_tree(value):
                    if isinstance(value, str):
                        return await protection.restore(value)
                    if isinstance(value, list):
                        return [await restore_tree(item) for item in value]
                    if isinstance(value, dict):
                        result = {}
                        for key, item in value.items():
                            restored_key = await protection.restore(key)
                            if restored_key in result:
                                raise GatewayError(502, "Argomenti strumento ambigui.")
                            result[restored_key] = await restore_tree(item)
                        return result
                    return value
                parsed = await restore_tree(parsed)
                result["tool_calls"].append({"id": call["id"], "type": "function",
                    "function": {"name": fn["name"], "arguments": compact(parsed)}})
        answer = {"id": "chatcmpl-" + uuid.uuid4().hex, "object": "chat.completion",
                  "created": int(time.time()), "model": model,
                  "choices": [{"index": 0, "message": result, "finish_reason": source["finish_reason"]}]}
        usage = raw.get("usage")
        if isinstance(usage, dict):
            # Provider details can include nested counters but no arbitrary free text.
            def counters(value):
                return {k: counters(v) if isinstance(v, dict) else v for k,v in value.items()
                        if isinstance(v, dict) or isinstance(v, int) and v >= 0}
            answer["usage"] = counters(usage)
        return answer
    except (KeyError, TypeError, ValueError, RecursionError):
        raise GatewayError(502, "Risposta del modello non valida.") from None


def sse(answer):
    """Emit only after full validation/restoration, never partial PII placeholders."""
    base = {k: answer[k] for k in ("id", "created", "model")}
    base["object"] = "chat.completion.chunk"
    message = deepcopy(answer["choices"][0]["message"])
    if "tool_calls" in message:
        for index, call in enumerate(message["tool_calls"]):
            call["index"] = index
    yield "data: " + compact({**base, "choices": [{"index": 0, "delta": message, "finish_reason": None}]}) + "\n\n"
    final = {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": answer["choices"][0]["finish_reason"]}]}
    if "usage" in answer:
        final["usage"] = answer["usage"]
    yield "data: " + compact(final) + "\n\n"
    yield "data: [DONE]\n\n"


def create_app(settings=None, transport=None):
    settings = settings or Settings.from_env()
    settings.validate()

    @asynccontextmanager
    async def lifespan(app):
        # Never inherit system proxy credentials or follow upstream redirects.
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False, transport=transport) as client:
            app.state.client = client
            yield

    app = FastAPI(title="Intecha Privacy Gateway", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.exception_handler(GatewayError)
    async def gateway_error(request, exc):
        return JSONResponse({"error": {"message": exc.message, "type": "privacy_gateway_error"}}, status_code=exc.status)

    def authenticate(request):
        expected = "Bearer " + settings.gateway_key
        if not hmac.compare_digest(request.headers.get("authorization", "").encode(), expected.encode()):
            raise HTTPException(401, "Accesso non consentito")

    @app.get("/health")
    async def health():
        # Liveness only: readiness/protocol checked by protect on every chat call.
        return {"status": "ok", "protection": "mandatory", "streaming": "buffered", "text_only": True}

    @app.get("/v1/models")
    async def models(request: Request):
        authenticate(request)
        return {"object": "list", "data": [{"id": m, "object": "model", "created": 0, "owned_by": "intecha"} for m in settings.models]}

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        authenticate(request)
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > settings.max_bytes:
                raise GatewayError(413, "Richiesta troppo grande.")
        try:
            body = json.loads(data)
        except (ValueError, RecursionError):
            raise GatewayError(400, "JSON non valido.") from None
        try:
            output, fields, arg_fields, invariant_fields = prepare(body, settings)
        except (TypeError, KeyError, AttributeError, RecursionError):
            raise GatewayError(400, "Struttura della richiesta non valida.") from None
        client = app.state.client
        protection = Protection(client, settings)
        try:
            await protection.protect(fields)
            if any(holder["value"] != key for key, holder in invariant_fields.items()):
                raise GatewayError(400, "Identificativi o chiavi strutturate contengono dati riconosciuti come personali.")
            for fn, parsed in arg_fields:
                fn["arguments"] = compact(parsed)
            output["messages"].insert(0, {"role": "system", "content": GUIDANCE})
            try:
                async with client.stream("POST", settings.provider_url + "/chat/completions",
                    headers={"Authorization": "Bearer " + settings.provider_key}, json=output,
                    timeout=settings.timeout, follow_redirects=False) as response:
                    if response.status_code != 200:
                        raise GatewayError(502, "Il modello non è disponibile. Riprova.")
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > settings.max_response_bytes:
                            raise GatewayError(502, "Risposta del modello troppo grande.")
                    parsed = json.loads(raw)
            except (httpx.HTTPError, ValueError, RecursionError):
                raise GatewayError(502, "Il modello non è disponibile. Riprova.") from None
            answer = await restored_completion(parsed, protection, body["model"],
                {t["function"]["name"] for t in output.get("tools", [])})
        finally:
            await protection.cleanup()
        if body.get("stream"):
            return StreamingResponse(sse(answer), media_type="text/event-stream",
                                     headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
        return JSONResponse(answer, headers={"Cache-Control": "no-store"})

    return app
