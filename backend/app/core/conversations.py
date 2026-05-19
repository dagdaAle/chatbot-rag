"""Gestione conversazioni e messaggi con SQLite."""
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, Column, String, DateTime, Text, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session

# Path database SQLite
# Usa DATA_DIR se disponibile (Docker), altrimenti path relativo (sviluppo locale)
DATA_DIR = Path(os.getenv("DATA_DIR", str(Path(__file__).parent.parent.parent / "data")))
DB_PATH = DATA_DIR / "conversations.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Database setup
DATABASE_URL = f"sqlite:///{DB_PATH}"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Conversation(Base):
    """Modello SQLAlchemy per le conversazioni."""
    __tablename__ = "conversations"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    knowledge_id = Column(String, nullable=True)

    # Relazione con messaggi
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.timestamp")


class Message(Base):
    """Modello SQLAlchemy per i messaggi."""
    __tablename__ = "messages"

    id = Column(String, primary_key=True)
    conversation_id = Column(String, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False)  # "user" o "assistant"
    content = Column(Text, nullable=False)
    sources = Column(JSON, nullable=True)  # Lista di fonti (solo per assistant)
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relazione con conversazione
    conversation = relationship("Conversation", back_populates="messages")


def init_db():
    """Inizializza il database creando le tabelle se non esistono."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """Restituisce una sessione database."""
    db = SessionLocal()
    try:
        return db
    finally:
        pass  # La sessione verrà chiusa dal chiamante


# Inizializza database al primo import
init_db()


def list_conversations(limit: int = 100) -> list[dict]:
    """Lista tutte le conversazioni ordinate per updated_at DESC."""
    db = get_db()
    try:
        conversations = db.query(Conversation).order_by(Conversation.updated_at.desc()).limit(limit).all()
        result = []
        for conv in conversations:
            result.append({
                "id": conv.id,
                "title": conv.title,
                "created_at": conv.created_at.isoformat() if conv.created_at else None,
                "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
                "knowledge_id": conv.knowledge_id,
            })
        return result
    finally:
        db.close()


def get_conversation(conversation_id: str) -> Optional[dict]:
    """Recupera una conversazione con tutti i suoi messaggi."""
    db = get_db()
    try:
        conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if not conv:
            return None

        messages = []
        for msg in conv.messages:
            messages.append({
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "sources": msg.sources,
                "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
            })

        return {
            "id": conv.id,
            "title": conv.title,
            "created_at": conv.created_at.isoformat() if conv.created_at else None,
            "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
            "knowledge_id": conv.knowledge_id,
            "messages": messages,
        }
    finally:
        db.close()


def create_conversation(title: str, knowledge_id: Optional[str] = None) -> dict:
    """Crea una nuova conversazione vuota."""
    db = get_db()
    try:
        conv_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        conv = Conversation(
            id=conv_id,
            title=title,
            created_at=now,
            updated_at=now,
            knowledge_id=knowledge_id,
        )

        db.add(conv)
        db.commit()
        db.refresh(conv)

        return {
            "id": conv.id,
            "title": conv.title,
            "created_at": conv.created_at.isoformat() if conv.created_at else None,
            "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
            "knowledge_id": conv.knowledge_id,
        }
    finally:
        db.close()


def delete_conversation(conversation_id: str) -> bool:
    """Elimina una conversazione e tutti i suoi messaggi."""
    db = get_db()
    try:
        conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if not conv:
            return False

        db.delete(conv)
        db.commit()
        return True
    finally:
        db.close()


def add_message(
    conversation_id: str,
    role: str,
    content: str,
    sources: Optional[list[dict]] = None,
) -> dict:
    """Aggiunge un messaggio a una conversazione e aggiorna updated_at."""
    db = get_db()
    try:
        # Verifica che la conversazione esista
        conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if not conv:
            raise ValueError(f"Conversazione {conversation_id} non trovata")

        # Crea il messaggio
        msg_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        msg = Message(
            id=msg_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            sources=sources,
            timestamp=now,
        )

        db.add(msg)

        # Aggiorna updated_at della conversazione
        conv.updated_at = now

        db.commit()
        db.refresh(msg)

        return {
            "id": msg.id,
            "conversation_id": msg.conversation_id,
            "role": msg.role,
            "content": msg.content,
            "sources": msg.sources,
            "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
        }
    finally:
        db.close()


def update_conversation_title(conversation_id: str, title: str) -> bool:
    """Aggiorna il titolo di una conversazione."""
    db = get_db()
    try:
        conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if not conv:
            return False

        conv.title = title
        conv.updated_at = datetime.now(timezone.utc)
        db.commit()
        return True
    finally:
        db.close()

