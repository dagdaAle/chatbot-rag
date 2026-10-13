"""Internal authenticated PII service; v1 chat API fails closed without GLiNER."""
import asyncio
from contextlib import asynccontextmanager, suppress
import logging
import os
from pathlib import Path
import secrets
import sqlite3
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, model_validator

from app.engine import ALL_ENTITIES, Anonymizer, _TOKEN_RE
from app.recognizers.gliner_ner import GlinerRecognizer
from app.vault import Vault

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("anonymizer")
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
TOKEN = os.getenv("ANONYMIZER_TOKEN", "")
GLINER_MODEL = os.getenv("GLINER_MODEL", "urchade/gliner_multi_pii-v1")
GLINER_THRESHOLD = float(os.getenv("GLINER_THRESHOLD", "0.5"))
SPACY_MODEL = os.getenv("SPACY_MODEL", "it_core_news_sm")
DISABLE_GLINER = os.getenv("DISABLE_GLINER") == "1"
MAPPING_TTL_SECONDS = int(os.getenv("MAPPING_TTL_SECONDS", "900"))
MAX_PENDING = 4
state: dict = {}


def _device() -> str:
    wanted = os.getenv("DEVICE", "auto")
    if wanted != "auto":
        return wanted
    import torch
    return "cuda" if torch.cuda.is_available() else "cpu"


async def _expiry_loop():
    while True:
        await asyncio.sleep(60)
        try:
            await run_in_threadpool(state["engine"].vault.expire)
        except Exception:
            log.error("Temporary mapping cleanup failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    key = os.getenv("ANONYMIZER_KEY")
    if not key or not TOKEN:
        raise RuntimeError("ANONYMIZER_KEY e ANONYMIZER_TOKEN sono obbligatori")
    if not 300 <= MAPPING_TTL_SECONDS <= 3600 or not 0 < GLINER_THRESHOLD <= 1:
        raise RuntimeError("Configurazione protezione non valida")
    gliner = None
    state["device"] = "off"
    if not DISABLE_GLINER:
        state["device"] = _device()
        gliner = GlinerRecognizer(GLINER_MODEL, state["device"], GLINER_THRESHOLD)
        gliner.load()
    state["engine"] = Anonymizer(Vault(DATA_DIR / "vault.db", key), gliner, SPACY_MODEL)
    state["complete"] = gliner is not None and gliner.model is not None
    state["semaphore"] = asyncio.Semaphore(1)
    state["pending"] = 0
    state["engine"].vault.expire()
    task = asyncio.create_task(_expiry_loop())
    log.info("Pronto (GLiNER: %s)", state["device"])
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        state["engine"].vault.close()
        state.clear()


app = FastAPI(title="Anonymizer", lifespan=lifespan)


def check_token(x_anonymizer_token: str = Header(default="")) -> None:
    if not TOKEN or not secrets.compare_digest(x_anonymizer_token, TOKEN):
        raise HTTPException(401, "Token non valido")


Mode = Literal["pseudo", "redact"]
Text = Annotated[str, Field(max_length=200_000)]


class AnonymizeIn(BaseModel):
    text: Text
    mode: Mode = "pseudo"
    mapping_id: str | None = Field(default=None, max_length=100)
    entities: list[str] | None = Field(default=None, max_length=len(ALL_ENTITIES))
    threshold: float = Field(0.5, ge=0, le=1)


class BatchIn(BaseModel):
    texts: list[Text] = Field(min_length=1, max_length=64)
    mode: Mode = "pseudo"
    mapping_id: str | None = Field(default=None, max_length=100)
    entities: list[str] | None = Field(default=None, max_length=len(ALL_ENTITIES))
    threshold: float = Field(0.5, ge=0, le=1)

    @model_validator(mode="after")
    def total_size(self):
        if sum(map(len, self.texts)) > 200_000:
            raise ValueError("Batch troppo grande")
        return self


class ProtectIn(BaseModel):
    mapping_id: UUID
    texts: list[Text] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def total_size(self):
        if sum(map(len, self.texts)) > 200_000:
            raise ValueError("Batch troppo grande")
        return self


class RestoreIn(BaseModel):
    mapping_id: UUID
    text: Text
    allowed_tokens: list[Annotated[str, Field(max_length=100)]] = Field(max_length=10000)


class EntityOut(BaseModel):
    entity_type: str
    start: int
    end: int
    score: float
    replacement: str


class AnonymizeOut(BaseModel):
    text: str
    mapping_id: str | None
    entities: list[EntityOut]


class DeanonymizeIn(BaseModel):
    text: Text
    mapping_id: str = Field(max_length=100)


def _validate_entities(entities: list[str] | None) -> None:
    if set(entities or []) - set(ALL_ENTITIES):
        raise HTTPException(422, "Entità sconosciute")


async def _limited(function, *args):
    # One inference at a time; do not admit an unbounded GPU queue.
    if state["pending"] >= MAX_PENDING:
        raise HTTPException(503, "Servizio occupato")
    state["pending"] += 1
    try:
        async with state["semaphore"]:
            try:
                return await run_in_threadpool(function, *args)
            except HTTPException:
                raise
            except Exception:
                # No exception repr: it can include source text from recognizers.
                raise HTTPException(503, "Protezione non disponibile") from None
    finally:
        state["pending"] -= 1


def _run(text: str, body) -> AnonymizeOut:
    out, mapping_id, found = state["engine"].anonymize(text, body.mode, body.mapping_id, body.entities, body.threshold)
    return AnonymizeOut(text=out, mapping_id=mapping_id, entities=[EntityOut(**f.__dict__) for f in found])


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "device": state.get("device", "off"), "gliner": GLINER_MODEL,
            "protocol_version": 1, "recognizers_complete": state.get("complete", False)}


@app.get("/entities", dependencies=[Depends(check_token)])
def entities() -> list[str]:
    return ALL_ENTITIES


@app.post("/v1/protect", dependencies=[Depends(check_token)])
async def protect(body: ProtectIn) -> dict:
    if not state.get("complete"):
        raise HTTPException(503, "Riconoscitori completi non disponibili")
    mapping_id = str(body.mapping_id)

    def run():
        vault = state["engine"].vault
        try:
            vault.create_temporary(mapping_id, MAPPING_TTL_SECONDS)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Mappatura già utilizzata") from None
        try:
            texts, tokens = state["engine"].protect_batch(body.texts, mapping_id, GLINER_THRESHOLD)
            return {"protocol_version": 1, "mapping_id": mapping_id, "texts": texts,
                    "tokens": tokens, "recognizers_complete": True}
        except Exception:
            vault.delete(mapping_id)
            raise

    return await _limited(run)


@app.post("/v1/restore", dependencies=[Depends(check_token)])
def restore(body: RestoreIn) -> dict:
    mapping_id = str(body.mapping_id)
    engine = state["engine"]
    if not engine.vault.exists(mapping_id) or not engine.vault.is_temporary(mapping_id):
        raise HTTPException(404, "Mappatura temporanea inesistente o scaduta")
    allowed = set(body.allowed_tokens)
    table = engine.vault.lookup(mapping_id)
    if not allowed <= table.keys() or not set(_TOKEN_RE.findall(body.text)) <= allowed:
        raise HTTPException(422, "Segnaposto non consentito")
    text, replaced = engine.deanonymize(body.text, mapping_id, allowed)
    return {"protocol_version": 1, "mapping_id": mapping_id, "text": text, "replaced": replaced}


@app.post("/anonymize", response_model=AnonymizeOut, dependencies=[Depends(check_token)])
async def anonymize(body: AnonymizeIn) -> AnonymizeOut:
    _validate_entities(body.entities)
    return await _limited(_run, body.text, body)


@app.post("/anonymize/batch", response_model=list[AnonymizeOut], dependencies=[Depends(check_token)])
async def anonymize_batch(body: BatchIn) -> list[AnonymizeOut]:
    _validate_entities(body.entities)

    def run_all():
        results, mapping_id = [], body.mapping_id
        for text in body.texts:
            res = _run(text, body.model_copy(update={"mapping_id": mapping_id}))
            mapping_id = res.mapping_id or mapping_id
            results.append(res)
        return results

    return await _limited(run_all)


@app.post("/deanonymize", dependencies=[Depends(check_token)])
def deanonymize(body: DeanonymizeIn) -> dict:
    if not state["engine"].vault.exists(body.mapping_id):
        raise HTTPException(404, "Mappatura inesistente")
    text, replaced = state["engine"].deanonymize(body.text, body.mapping_id)
    return {"text": text, "replaced": replaced}


@app.delete("/mappings/{mapping_id}", dependencies=[Depends(check_token)])
def delete_mapping(mapping_id: str) -> dict:
    if not state["engine"].vault.delete(mapping_id):
        raise HTTPException(404, "Mappatura inesistente")
    return {"deleted": mapping_id}
