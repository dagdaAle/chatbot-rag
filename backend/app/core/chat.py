"""Chat RAG con OpenAI o Ollama."""
import json
import os
from pathlib import Path
from app.config import DATA_DIR
import numpy as np
from app.core.storage import write_json
from openai import OpenAI

from app.config import settings, runtime_config
from app.core.embeddings import get_query_embedding
from app.core.hierarchical import expand_hierarchical_contexts
from app.core.qdrant_client import COLLECTION_NAME, collection_supports_hybrid, get_client
from app.core.lexical import LEXICAL_VECTOR_NAME, sparse_text_vector
from app.core.price_lists import query_price_lists
from app.core.documents import published_document_ids
from app.core.knowledge import get_collection_name, get_knowledge
from app.core.ollama_client import generate_chat_response as ollama_generate_chat_response
from app.core.privacy import protected_request, PrivacyError

_openai_client: OpenAI | None = None
_deepseek_client: OpenAI | None = None

def _get_deepseek_client() -> OpenAI:
    global _deepseek_client
    if _deepseek_client is None:
        if not settings.deepseek_api_key:
            raise RuntimeError("DEEPSEEK_API_KEY non configurata")
        _deepseek_client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url, timeout=120)
    return _deepseek_client

# Path per salvare il prompt di sistema
PROMPT_FILE = DATA_DIR / "system_prompt.json"

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
        write_json(PROMPT_FILE, {"prompt": prompt})
        return True
    except Exception:
        return False


def retrieve_context(
    query: str,
    top_k: int = 12,
    knowledge_id: str | None = None,
    score_threshold: float = 0.3,
    use_mmr: bool = True,
    lexical_query: str | None = None,
    document_ids: set[str] | None = None,
    expand_sections: bool = True,
) -> list[dict]:
    """Cerca chunk con fusione semantica/lessicale e diversificazione MMR.

    Se knowledge_id è fornito cerca nella collezione della knowledge,
    altrimenti usa la collezione legacy.
    """
    from qdrant_client import models
    if knowledge_id and document_ids is None:
        document_ids = published_document_ids(knowledge_id)
    if document_ids is not None and not document_ids:
        return []
    published_filter = models.Filter(must=[models.FieldCondition(
        key="document_id", match=models.MatchAny(any=sorted(document_ids)),
    )]) if document_ids is not None else None
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

    # Recupera più risultati per permettere fusione e MMR.
    search_limit = max(top_k * 2, 24)  # Almeno il doppio per avere scelta
    try:
        hybrid_enabled = collection_supports_hybrid(client, collection_name)
    except (AttributeError, ValueError):
        hybrid_enabled = False

    if hybrid_enabled:
        sparse_query = sparse_text_vector(lexical_query or query)
        prefetch = [models.Prefetch(
            query=query_vector,
            limit=search_limit,
            score_threshold=score_threshold,
            filter=published_filter,
        )]
        if sparse_query.indices:
            prefetch.append(models.Prefetch(
                query=sparse_query,
                using=LEXICAL_VECTOR_NAME,
                limit=search_limit,
                filter=published_filter,
            ))
        if len(prefetch) == 1:
            response = client.query_points(
                collection_name=collection_name,
                query=query_vector,
                query_filter=published_filter,
                limit=search_limit,
                score_threshold=score_threshold,
                with_payload=True,
                with_vectors=use_mmr,
            )
        else:
            response = client.query_points(
                collection_name=collection_name,
                prefetch=prefetch,
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                query_filter=published_filter,
                limit=search_limit,
                with_payload=True,
                with_vectors=use_mmr,
            )
        filtered_results = response.points
        retrieval_method = "hybrid_rrf"
    else:
        # Compatibilità di sola lettura durante la migrazione degli indici esistenti.
        results = client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            query_filter=published_filter,
            limit=search_limit,
            with_payload=True,
            with_vectors=use_mmr,
        )
        filtered_results = [hit for hit in results if hit.score >= score_threshold]
        retrieval_method = "semantic_legacy"

    if not filtered_results:
        return []

    # Applica MMR se richiesto e abbiamo abbastanza risultati
    if use_mmr and len(filtered_results) > top_k:
        try:
            candidates = []
            for hit in filtered_results:
                vector = hit.vector
                if isinstance(vector, dict):
                    vector = vector.get("")
                if vector:
                    candidates.append((hit, vector))

            if candidates:
                vectors = [vector for _, vector in candidates]
                scores = [hit.score for hit, _ in candidates]
                # Applica MMR
                selected_indices = []
                for _ in range(min(top_k, len(vectors))):
                    next_idx = _calculate_mmr(query_vector, vectors, scores, selected_indices)
                    if next_idx >= 0:
                        selected_indices.append(next_idx)

                # Riordina i risultati secondo MMR
                filtered_results = [candidates[i][0] for i in selected_indices]
            else:
                filtered_results = filtered_results[:top_k]
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
            "section_path": payload.get("section_path", []),
            "section_refs": payload.get("section_refs", []),
            "source_regions": payload.get("source_regions", []),
            "content_kind": payload.get("content_kind", "text"),
            "score": hit.score,
            "retrieval_method": retrieval_method,
        })
    if not expand_sections:
        return contexts
    return expand_hierarchical_contexts(
        client,
        collection_name,
        contexts,
        section_char_limit=settings.retrieval_section_max_chars,
        total_char_limit=settings.retrieval_total_max_chars,
        neighbor_chunks=settings.retrieval_neighbor_chunks,
    )


def generate_response(
    question: str,
    contexts: list[dict],
    conversation_history: list[dict] | None = None,
    provider: str | None = None, model: str | None = None,
) -> str:
    """Genera una risposta usando OpenAI o Ollama con il contesto recuperato e la cronologia."""
    if not contexts:
        return "Non ho trovato passaggi sufficientemente pertinenti nei documenti disponibili. Prova a riformulare la domanda."
    provider = provider or runtime_config.chat_provider
    model = model or runtime_config.chat_model

    # Costruisci il contesto formattato dai documenti
    context_parts = []
    for i, ctx in enumerate(contexts, 1):
        # Filenames can contain personal data; citations use local source numbers.
        header = f"Documento: {ctx['filename']}" if provider == "ollama" else f"Fonte {i}"
        if ctx.get("section_path"):
            header += f" | Sezione: {' > '.join(ctx['section_path'])}"
        if ctx.get("context_scope") == "section":
            header += " | sezione completa" if ctx.get("section_complete") else " | estratto esteso della sezione"
        elif ctx.get("context_scope") == "neighbors":
            header += " | passaggio con contesto adiacente"
        context_parts.append(f"[{header}]\n{ctx['text']}")

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

    from app.core.usage import measure
    with measure(provider, model, 'chat') as usage:
        if provider == 'ollama':
            return ollama_generate_chat_response(messages, model=model, usage=usage)
        client = _get_deepseek_client() if provider == 'deepseek' else _get_openai_client()
        options = {'extra_body': {'thinking': {'type': 'disabled'}}} if provider == 'deepseek' else {}
        with protected_request(messages) as protected:
            try:
                response = client.chat.completions.create(**options, model=model, messages=protected.messages, temperature=0.3, max_tokens=1500)
            except Exception:
                # SDK errors can echo request data or headers in their bodies.
                raise PrivacyError("Il modello esterno non è disponibile. Riprova più tardi.") from None
            if response.usage:
                usage.update(input_tokens=response.usage.prompt_tokens, output_tokens=response.usage.completion_tokens)
            return protected.restore(response.choices[0].message.content or '')


def chat(
    question: str,
    top_k: int = 12,
    conversation_history: list[dict] | None = None,
    knowledge_id: str | None = None,
    score_threshold: float = 0.3,
    provider: str | None = None, model: str | None = None,
) -> dict:
    """Pipeline RAG completa: retrieve + generate con supporto cronologia e knowledge."""
    # Recupera il contesto dalla knowledge specifica
    history = []
    budget = 16000
    for message in reversed(conversation_history or []):
        content = message.get("content", "")
        if len(content) > budget:
            break
        history.insert(0, message)
        budget -= len(content)
        if len(history) >= 12:
            break
    previous_questions = [m["content"] for m in history if m.get("role") == "user"][-2:]
    retrieval_query = "\n".join(previous_questions + [question])
    document_ids = published_document_ids(knowledge_id) if knowledge_id else None
    structured = query_price_lists(
        "\n".join(previous_questions + [question]),
        knowledge_id,
        current_question=question,
        document_ids=document_ids,
    ) if knowledge_id else None
    if structured:
        contexts = structured["sources"]
        answer = structured["answer"]
    else:
        active_provider = provider or runtime_config.chat_provider
        if settings.agentic_rag_enabled and active_provider == "deepseek" and knowledge_id:
            from app.core.agentic import research
            result = research(question, history, knowledge_id, top_k=top_k,
                              score_threshold=score_threshold,
                              model=model or runtime_config.chat_model)
            return result
        contexts = retrieve_context(
            retrieval_query,
            top_k=top_k,
            knowledge_id=knowledge_id,
            score_threshold=score_threshold,
            lexical_query=question,
            document_ids=document_ids,
        )
        answer = generate_response(question, contexts, history, provider=provider, model=model)

    # Prepara le fonti con testo completo per il frontend
    sources = []
    for ctx in contexts:
        sources.append({
            "knowledge_id": knowledge_id,
            "filename": ctx["filename"],
            "score": round(ctx["score"], 3),
            "text": ctx["text"],
            "chunk_index": ctx["chunk_index"],
            "document_id": ctx["document_id"],
            "page_start": ctx.get("page_start", 1),
            "page_end": ctx.get("page_end", 1),
            "section_path": ctx.get("section_path", []),
            "section_refs": ctx.get("section_refs", []),
            "source_regions": ctx.get("source_regions", []),
            "content_kind": ctx.get("content_kind", "text"),
            "retrieval_method": ctx.get("retrieval_method", "semantic_legacy"),
            "context_scope": ctx.get("context_scope", "chunk"),
            "section_complete": ctx.get("section_complete", False),
            "expanded_chunks": ctx.get("expanded_chunks", 1),
            "verified_data": ctx.get("verified_data", False),
            "version_label": ctx.get("version_label"),
            "series_key": ctx.get("series_key"),
            "price_value": ctx.get("price_value"),
            "price_column": ctx.get("price_column"),
            "raw_cells": ctx.get("raw_cells"),
        })

    return {
        "answer": answer,
        "sources": sources,
        "contexts_used": len(contexts),
        "structured_intent": structured.get("intent") if structured else None,
        "structured_rows_matched": structured.get("rows_matched") if structured else None,
    }
