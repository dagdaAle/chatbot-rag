"""Entry point FastAPI."""
import logging
logging.getLogger("pypdf").setLevel(logging.ERROR)
from fastapi import FastAPI, Depends
from app.auth import current_user
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.api import health, documents, chat, prompt, models, knowledge, conversations, admin

from contextlib import asynccontextmanager
from app.core.qdrant_client import get_client

@asynccontextmanager
async def lifespan(app):
    get_client()
    yield
    if get_client.cache_info().currsize:
        get_client().close()
        get_client.cache_clear()

app = FastAPI(
    lifespan=lifespan,
    title="Chatbot RAG API",
    description="API RAG per documenti - Qdrant + FastAPI",
    version="0.1.0",
)

origins = [o.strip() for o in settings.cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin.router, dependencies=[Depends(current_user)])
app.include_router(admin.account_router, dependencies=[Depends(current_user)])

app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(knowledge.router, dependencies=[Depends(current_user)])
app.include_router(documents.router, dependencies=[Depends(current_user)])
app.include_router(chat.router, dependencies=[Depends(current_user)])
app.include_router(conversations.router, dependencies=[Depends(current_user)])
app.include_router(prompt.router, dependencies=[Depends(current_user)])
app.include_router(models.router, dependencies=[Depends(current_user)])


# ── Frontend statico (SPA) ────────────────────────────────────────────
# In modalità single-instance, il backend serve anche il frontend compilato.
# Le route API hanno la precedenza, tutto il resto va all'SPA.
# Il path /app/static è popolato nella build Docker multi-stage.
import os
from starlette.exceptions import HTTPException as StarletteHTTPException

class SPAStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            response = await super().get_response(path, scope)
            if response.status_code != 404:
                return response
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
        if path.startswith("c/") or path in ("knowledge", "settings", "pdf-viewer", "admin", "account"):
            return await super().get_response("index.html", scope)
        raise StarletteHTTPException(status_code=404)

_static_dir = "/app/static"
if os.path.isdir(_static_dir):
    app.mount("/", SPAStaticFiles(directory=_static_dir, html=True), name="frontend")
