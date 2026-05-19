"""Chat RAG con OpenAI o Ollama."""
import json
import os
from pathlib import Path
import numpy as np
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
- Fornisci risposte accurate e ben documentate

## Regole FONDAMENTALI per le risposte

### 1. Usa SOLO le informazioni dal contesto fornito
- Non inventare MAI informazioni, date, numeri o riferimenti
- Se il contesto contiene l'informazione, citala VERBATIM (parola per parola)
- Se non trovi l'informazione nel contesto, dichiaralo esplicitamente

### 2. Citazioni precise e complete
- Indica SEMPRE il documento specifico: "Secondo [Nome Documento], ..."
- Cita le informazioni LETTERALMENTE usando virgolette per i passaggi diretti
- Se un'informazione è presente in più documenti, combinali per dare il quadro completo
- Combina informazioni da più chunk dello stesso argomento per fornire contesto completo

### 3. Gestione di informazioni frammentate
- Quando ricevi più chunk correlati, uniscili per fornire una risposta coerente
- Non ripetere la stessa informazione se presente in più chunk
- Integra dettagli complementari da diversi chunk per completezza

### 4. Mantieni il contesto della conversazione
- Quando l'utente chiede "dimmi di più", "spiega meglio", "perché?", riferisciti alla risposta precedente
- Espandi e approfondisci l'argomento discusso usando informazioni aggiuntive dai documenti
- Se l'utente usa pronomi come "questo", "quello", capisci a cosa si riferisce dal contesto

### 5. Se l'informazione non è disponibile
- Rispondi chiaramente: "Non ho trovato questa informazione specifica nei documenti disponibili."
- Proponi di riformulare la domanda o suggerisci argomenti correlati presenti nei documenti

### 6. Precisione assoluta con dati specifici
- Date, numeri, importi, nomi, riferimenti devono essere riportati ESATTAMENTE come nei documenti
- Non approssimare mai i dati numerici
- Indica sempre la fonte del dato specifico

### 7. Trasparenza nelle fonti
- Quando usi informazioni da più documenti, elenca chiaramente tutte le fonti
- Se un'informazione è incerta o parziale nei documenti, specificalo

## Formato delle risposte
- Inizia con l'informazione principale citando la fonte
- Organizza le informazioni in modo logico e leggibile
- Usa elenchi puntati per informazioni multiple o complesse
- Evidenzia le informazioni chiave
- Termina indicando se servono chiarimenti aggiuntivi
- Rispondi SEMPRE in italiano

## Esempio di risposta ben strutturata:
"Secondo [Nome Documento], '[citazione verbatim]'. Questo viene confermato anche in [Altro Documento] che specifica '[altra citazione]'.

Le informazioni principali sono:
• [punto 1 con fonte]
• [punto 2 con fonte]

Posso fornire ulteriori dettagli su qualsiasi aspetto specifico di questa informazione."""


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


def _calculate_mmr(
    query_vector: list[float],
    candidate_vectors: list[list[float]],
    candidate_scores: list[float],
    selected_indices: list[int],
    lambda_param: float = 0.7,
) -> int:
    """Calcola il prossimo documento da selezionare usando Maximum Marginal Relevance.

    Args:
        query_vector: vettore della query
        candidate_vectors: vettori dei documenti candidati
        candidate_scores: score di similarità con la query
        selected_indices: indici dei documenti già selezionati
        lambda_param: parametro di bilanciamento tra relevance e diversity (0.7 = più relevance)

    Returns:
        Indice del documento da selezionare
    """
    if not candidate_vectors:
        return -1

    query_vec = np.array(query_vector)
    best_score = -1
    best_idx = -1

    for i, (doc_vec, relevance_score) in enumerate(zip(candidate_vectors, candidate_scores)):
        if i in selected_indices:
            continue

        doc_vec = np.array(doc_vec)

        # Calcola similarità con documenti già selezionati
        max_similarity = 0
        if selected_indices:
            similarities = []
            for j in selected_indices:
                selected_vec = np.array(candidate_vectors[j])
                # Cosine similarity
                dot_product = np.dot(doc_vec, selected_vec)
                norm_doc = np.linalg.norm(doc_vec)
                norm_selected = np.linalg.norm(selected_vec)
                if norm_doc > 0 and norm_selected > 0:
                    sim = dot_product / (norm_doc * norm_selected)
                    similarities.append(sim)
            max_similarity = max(similarities) if similarities else 0

        # Formula MMR: λ * relevance - (1-λ) * max_similarity
        mmr_score = lambda_param * relevance_score - (1 - lambda_param) * max_similarity

        if mmr_score > best_score:
            best_score = mmr_score
            best_idx = i

    return best_idx


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
    top_k: int = 12,
    knowledge_id: str | None = None,
    score_threshold: float = 0.3,
    use_mmr: bool = True,
) -> list[dict]:
    """Cerca i chunk più rilevanti in Qdrant con MMR e score filtering.

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

    # Recupera più risultati per permettere MMR e filtering
    search_limit = max(top_k * 2, 24)  # Almeno il doppio per avere scelta
    results = client.search(
        collection_name=collection_name,
        query_vector=query_vector,
        limit=search_limit,
        with_payload=True,
        with_vectors=use_mmr,  # Serve per MMR
    )

    # Filtra per score_threshold
    filtered_results = [hit for hit in results if hit.score >= score_threshold]

    if not filtered_results:
        # Se nessun risultato supera la soglia, prendi i migliori comunque
        filtered_results = results[:top_k] if results else []

    # Applica MMR se richiesto e abbiamo abbastanza risultati
    if use_mmr and len(filtered_results) > top_k:
        try:
            # Estrai vettori e score
            vectors = []
            scores = []
            for hit in filtered_results:
                if hit.vector:
                    vectors.append(hit.vector)
                    scores.append(hit.score)

            if vectors:
                # Applica MMR
                selected_indices = []
                for _ in range(min(top_k, len(vectors))):
                    next_idx = _calculate_mmr(query_vector, vectors, scores, selected_indices)
                    if next_idx >= 0:
                        selected_indices.append(next_idx)

                # Riordina i risultati secondo MMR
                filtered_results = [filtered_results[i] for i in selected_indices]
        except Exception:
            # Fallback a selezione normale in caso di errore MMR
            filtered_results = filtered_results[:top_k]
    else:
        # Prendi semplicemente i top_k
        filtered_results = filtered_results[:top_k]

    contexts = []
    for hit in filtered_results:
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
    top_k: int = 12,
    conversation_history: list[dict] | None = None,
    knowledge_id: str | None = None,
    score_threshold: float = 0.3,
) -> dict:
    """Pipeline RAG completa: retrieve + generate con supporto cronologia e knowledge."""
    # Recupera il contesto dalla knowledge specifica
    contexts = retrieve_context(question, top_k=top_k, knowledge_id=knowledge_id, score_threshold=score_threshold)

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
