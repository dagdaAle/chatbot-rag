"""Client Anthropic Claude per chat RAG."""
from anthropic import Anthropic
from app.config import settings


_client: Anthropic | None = None


def get_anthropic_client() -> Anthropic:
    """Restituisce il client Anthropic (singleton)."""
    global _client
    if _client is None:
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY non configurata")
        _client = Anthropic(api_key=settings.anthropic_api_key)
    return _client


def generate_chat_response(
    messages: list[dict],
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 1500,
    temperature: float = 0.3,
) -> str:
    """Genera una risposta usando Claude di Anthropic.

    Args:
        messages: Lista messaggi formato OpenAI (system, user, assistant)
        model: Modello Claude da usare
        max_tokens: Token massimi per la risposta
        temperature: Creatività della risposta (0.0 = deterministico, 1.0 = creativo)

    Returns:
        Testo della risposta generata
    """
    client = get_anthropic_client()

    # Claude ha un formato leggermente diverso da OpenAI:
    # - Il system prompt va separato
    # - I messaggi devono alternare user/assistant
    system_prompt = ""
    claude_messages = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "system":
            system_prompt = content
        elif role in ("user", "assistant"):
            claude_messages.append({"role": role, "content": content})

    # Assicurati che l'ultimo messaggio sia dell'utente
    # Se no, Claude potrebbe dare errore
    if claude_messages and claude_messages[-1]["role"] != "user":
        # Rimuovi l'ultimo messaggio assistant se presente
        while claude_messages and claude_messages[-1]["role"] == "assistant":
            claude_messages.pop()

    if not claude_messages:
        raise ValueError("Nessun messaggio user valido trovato")

    # Crea la richiesta a Claude
    request_kwargs = {
        "model": model,
        "messages": claude_messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    if system_prompt:
        request_kwargs["system"] = system_prompt

    response = client.messages.create(**request_kwargs)

    # Estrai il testo dalla risposta
    if response.content:
        # Claude restituisce una lista di content blocks
        text_blocks = [block.text for block in response.content if hasattr(block, 'text')]
        return "".join(text_blocks)

    return ""