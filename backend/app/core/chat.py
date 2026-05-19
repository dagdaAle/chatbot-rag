"""Chat RAG con OpenAI o Ollama."""
import json
import os
from pathlib import Path
from openai import OpenAI

from app.config import settings, runtime_config
from app.core.embeddings import get_query_embedding
from app.core.qdrant_client import COLLECTION_NAME, get_client
from app.core.knowledge import get_collection_name, get_knowledge
from app.core.ollama_client import generate_chat_response as ollama_generate_chat_response

_openai_client: OpenAI | None = None

# Path per salvare il prompt di sistema
PROMPT_FILE = Path(__file__).parent.parent.parent / "data" / "system_prompt.json"

# Prompt di default per il chatbot RAG
DEFAULT_SYSTEM_PROMPT = """Sei un assistente AI progettato per rispondere a domande basate sui documenti caricati nel sistema.

## Il tuo ruolo
- Sei un assistente cordiale, professionale e competente
- Aiuti a interpretare e comprendere i documenti presenti nel database
- Fornisci risposte chiare e comprensibili

## Regole FONDAMENTALI per le risposte

### 1. Usa SOLO le informazioni dal contesto fornito
- Non inventare MAI informazioni, date, numeri o riferimenti
- Se il contesto contiene l'informazione, citala fedelmente
- Se non trovi l'informazione nel contesto, dichiaralo esplicitamente

### 2. Cita sempre la fonte
- Indica il documento da cui proviene l'informazione

### 3. Mantieni il contesto della conversazione
- Quando l'utente chiede "dimmi di più", "spiega meglio", "perché?", "e poi?", riferisciti alla risposta precedente
- Espandi e approfondisci l'argomento discusso, non cambiare tema
- Se l'utente usa pronomi come "questo", "quello", "lo stesso", capisci a cosa si riferisce dal contesto della conversazione

### 4. Se l'informazione non è disponibile
- Rispondi: "Non ho trovato questa informazione specifica nei documenti disponibili."
- Proponi di riformulare la domanda

### 5. Precisione con dati specifici
- Date, numeri, importi, riferimenti devono essere riportati ESATTAMENTE come nei documenti

### 6. Semplifica il linguaggio tecnico
- Spiega i termini tecnici tra parentesi quando necessario
- Rendi accessibile il contenuto senza perdere la precisione

## Formato delle risposte
- Usa un linguaggio chiaro e professionale
- Per risposte lunghe, usa elenchi puntati o numerati
- Evidenzia le informazioni chiave
- Concludi con un'offerta di ulteriore assistenza quando appropriato
- Rispondi SEMPRE in italiano"""


def _get_openai_client() -> OpenAI:
    """Restituisce il client OpenAI (singleton)."""
    global _openai_client
    if _openai_client is None:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY non configurata")
        kwargs = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        _openai_client = OpenAI(**kwargs)
    return _openai_client


def get_system_prompt() -> str:
    """Carica il prompt di sistema dal file o usa il default."""
    try:
        if PROMPT_FILE.exists():
            with open(PROMPT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("prompt", DEFAULT_SYSTEM_PROMPT)
    except Exception:
        pass
    return DEFAULT_SYSTEM_PROMPT


def save_system_prompt(prompt: str) -> bool:
    """Salva il prompt di sistema su file."""
    try:
        PROMPT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PROMPT_FILE, "w", encoding="utf-8") as f:
            json.dump({"prompt": prompt}, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def retrieve_context(
    query: str,
    top_k: int = 5,
    knowledge_id: str | None = None,
) -> list[dict]:
    """Cerca i chunk più rilevanti in Qdrant.

    Se knowledge_id è fornito cerca nella collezione della knowledge,
    altrimenti usa la collezione legacy.
    """
    query_vector = get_query_embedding(query)
    client = get_client()

    # Determina la collezione
    if knowledge_id:
        collection_name = get_collection_name(knowledge_id)
    else:
        collection_name = COLLECTION_NAME

    # Verifica che la collezione esista
    collections = client.get_collections().collections
    if not any(c.name == collection_name for c in collections):
        return []

    results = client.search(
        collection_name=collection_name,
        query_vector=query_vector,
        limit=top_k,
        with_payload=True,
    )

    contexts = []
    for hit in results:
        payload = hit.payload or {}
        contexts.append({
            "text": payload.get("text", ""),
            "filename": payload.get("filename", ""),
            "document_id": payload.get("document_id", ""),
            "chunk_index": payload.get("chunk_index", 0),
            "page_start": payload.get("page_start", 1),
            "page_end": payload.get("page_end", 1),
            "score": hit.score,
        })
    return contexts


def generate_response(
    question: str,
    contexts: list[dict],
    conversation_history: list[dict] | None = None,
) -> str:
    """Genera una risposta usando OpenAI o Ollama con il contesto recuperato e la cronologia."""
    if not contexts:
        return "Non ci sono documenti caricati nel sistema. Carica dei documenti PDF per poter rispondere alle tue domande."

    # Costruisci il contesto formattato dai documenti
    context_parts = []
    for i, ctx in enumerate(contexts, 1):
        context_parts.append(f"[Documento: {ctx['filename']}]\n{ctx['text']}")

    context_text = "\n\n---\n\n".join(context_parts)

    # Carica il prompt di sistema
    system_prompt = get_system_prompt()

    # Costruisci i messaggi
    messages = [{"role": "system", "content": system_prompt}]

    # Aggiungi la cronologia della conversazione (se presente)
    if conversation_history:
        for msg in conversation_history:
            role = "user" if msg.get("role") == "user" else "assistant"
            content = msg.get("content", "")
            if content:
                messages.append({"role": role, "content": content})

    # Costruisci il messaggio utente corrente con il contesto
    user_message = f"""Contesto dai documenti:

{context_text}

---

Domanda dell'utente: {question}"""

    messages.append({"role": "user", "content": user_message})

    # Genera la risposta con il provider della CHAT
    if runtime_config.chat_provider == "ollama":
        return ollama_generate_chat_response(messages, model=runtime_config.chat_model)

    # Usa OpenAI
    client = _get_openai_client()
    response = client.chat.completions.create(
        model=runtime_config.chat_model,
        messages=messages,
        temperature=0.3,
        max_tokens=1500,
    )

    return response.choices[0].message.content or ""


def chat(
    question: str,
    top_k: int = 5,
    conversation_history: list[dict] | None = None,
    knowledge_id: str | None = None,
) -> dict:
    """Pipeline RAG completa: retrieve + generate con supporto cronologia e knowledge."""
    # Recupera il contesto dalla knowledge specifica
    contexts = retrieve_context(question, top_k=top_k, knowledge_id=knowledge_id)

    # Genera la risposta
    answer = generate_response(question, contexts, conversation_history)

    # Prepara le fonti con testo completo per il frontend
    sources = []
    for ctx in contexts:
        sources.append({
            "filename": ctx["filename"],
            "score": round(ctx["score"], 3),
            "text": ctx["text"],
            "chunk_index": ctx["chunk_index"],
            "document_id": ctx["document_id"],
            "page_start": ctx.get("page_start", 1),
            "page_end": ctx.get("page_end", 1),
        })

    return {
        "answer": answer,
        "sources": sources,
        "contexts_used": len(contexts),
    }
