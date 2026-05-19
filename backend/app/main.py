"""Entry point FastAPI."""
import logging
logging.getLogger("pypdf").setLevel(logging.ERROR)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.api import health, documents, chat, prompt, models, knowledge, conversations

app = FastAPI(
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

app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(knowledge.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(prompt.router)
app.include_router(models.router)


# ── Frontend statico (SPA) ────────────────────────────────────────────
# In modalità single-instance, il backend serve anche il frontend compilato.
# Le route API hanno la precedenza, tutto il resto va all'SPA.
# Il path /app/static è popolato nella build Docker multi-stage.
import os

_static_dir = "/app/static"
if os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="frontend")
