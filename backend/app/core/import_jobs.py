"""Persistent import worker: one leased job at a time, safe across restarts."""
from __future__ import annotations

import logging
import socket
import threading
import traceback
import uuid
from dataclasses import dataclass

from fastapi import HTTPException
from qdrant_client import models
from qdrant_client.models import PointStruct

from app.auth import User, request_user
from app.config import settings
from app.core.admin import privileged
from app.core.documents import (
    delete_import_pdf,
    delete_pdf_from_disk,
    get_import_path,
    process_pdf_to_points,
    save_document_structure,
    save_pdf_to_disk,
)
from app.core.knowledge import get_collection_name
from app.core.qdrant_client import ensure_collection_for_kb, get_client
from app.core.price_lists import delete_price_document, index_price_document
from app.core.usage import operation_context

logger = logging.getLogger(__name__)


class LostLease(RuntimeError):
    pass


def worker_identity() -> str:
    return f"{socket.gethostname()}-{uuid.uuid4().hex[:12]}"


def _rpc(name: str, body: dict):
    return privileged("POST", f"/rest/v1/rpc/{name}", body=body)


def claim_job(worker: str) -> dict | None:
    rows = _rpc("chatbot_claim_import_job", {
        "p_worker": worker, "p_lease_seconds": settings.import_worker_lease_seconds,
    })
    return rows[0] if rows else None


@dataclass
class JobState:
    stage: str = "extracting"
    progress: int = 5
    extractor: str | None = None
    extractor_version: str | None = None
    chunks_count: int | None = None


def update_job(job_id: str, worker: str, state: JobState, *, status="running",
               error_code=None, error_message=None) -> None:
    changed = _rpc("chatbot_update_import_job", {
        "p_job": job_id, "p_worker": worker, "p_status": status,
        "p_stage": state.stage, "p_progress": state.progress,
        "p_extractor": state.extractor, "p_extractor_version": state.extractor_version,
        "p_chunks_count": state.chunks_count, "p_error_code": error_code,
        "p_error_message": error_message,
        "p_lease_seconds": settings.import_worker_lease_seconds,
    })
    if changed is not True:
        raise LostLease(f"Lease persa per il job {job_id}")


class LeaseHeartbeat:
    def __init__(self, job_id: str, worker: str, state: JobState):
        self.job_id, self.worker, self.state = job_id, worker, state
        self.stop_event = threading.Event()
        self.lost_event = threading.Event()
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._run, name=f"lease-{job_id}", daemon=True)

    def start(self):
        self.thread.start()
        return self

    def set(self, *, stage, progress, structure=None, chunks_count=None):
        self.assert_owned()
        with self.lock:
            self.state.stage, self.state.progress = stage, progress
            if structure:
                self.state.extractor = structure.get("extractor")
                self.state.extractor_version = structure.get("extractor_version")
            if chunks_count is not None:
                self.state.chunks_count = chunks_count
            update_job(self.job_id, self.worker, self.state)

    def assert_owned(self):
        if self.lost_event.is_set():
            raise LostLease(f"Lease persa per il job {self.job_id}")

    def _run(self):
        interval = max(20, settings.import_worker_lease_seconds // 3)
        while not self.stop_event.wait(interval):
            try:
                with self.lock:
                    update_job(self.job_id, self.worker, self.state)
            except LostLease:
                self.lost_event.set()
                logger.warning("Lease del job %s assegnata a un altro worker", self.job_id)
                return
            except Exception:
                logger.exception("Impossibile rinnovare la lease del job %s", self.job_id)

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=2)


def _delete_vectors(client, collection_name: str, document_id: str) -> None:
    if not any(c.name == collection_name for c in client.get_collections().collections):
        return
    client.delete(
        collection_name=collection_name,
        points_selector=models.FilterSelector(filter=models.Filter(must=[
            models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id)),
        ])),
        wait=True,
    )


def _cleanup_partial(job: dict, client, collection_name: str) -> None:
    first_error = None
    for cleanup in (
        lambda: privileged("DELETE", "/rest/v1/documents", params={
            "document_id": f"eq.{job['document_id']}", "knowledge_id": f"eq.{job['knowledge_id']}",
        }),
        lambda: _delete_vectors(client, collection_name, job["document_id"]),
        lambda: delete_price_document(job["document_id"]),
        lambda: delete_pdf_from_disk(job["knowledge_id"], job["document_id"]),
    ):
        try:
            cleanup()
        except Exception as exc:
            first_error = first_error or exc
    if first_error:
        raise first_error


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, HTTPException) and isinstance(exc.detail, str):
        return exc.detail[:500]
    if isinstance(exc, ValueError):
        return str(exc)[:500]
    if isinstance(exc, FileNotFoundError):
        return "Il PDF in attesa non è disponibile sul volume persistente."
    return "Errore interno durante l’importazione. Consulta i log del worker."


def process_job(job: dict, worker: str) -> None:
    job_id, kb_id, document_id = job["id"], job["knowledge_id"], job["document_id"]
    state = JobState()
    heartbeat = LeaseHeartbeat(job_id, worker, state).start()
    client = None
    collection_name = get_collection_name(kb_id)
    user_marker = request_user.set(User(job["created_by"], "worker", False)) if job.get("created_by") else None
    usage_marker = operation_context.set({"knowledge_id": kb_id})
    try:
        client = get_client()
        import_path = get_import_path(kb_id, job_id)
        content = import_path.read_bytes()
        if len(content) != job["size_bytes"]:
            raise ValueError("Il PDF in attesa è incompleto o è stato modificato.")
        ensure_collection_for_kb(client, collection_name)
        heartbeat.set(stage=state.stage, progress=state.progress)
        _cleanup_partial(job, client, collection_name)

        def progress(stage, value, structure=None, chunks_count=None):
            heartbeat.set(stage=stage, progress=value, structure=structure, chunks_count=chunks_count)

        generated_id, points, structure = process_pdf_to_points(
            content, job["filename"], progress=progress, document_id=document_id,
        )
        if not points:
            raise ValueError("Nessun testo estraibile trovato nel PDF.")
        points = [(pid, vec, {**payload, "document_id": document_id}) for pid, vec, payload in points]
        if generated_id != document_id:
            raise RuntimeError("Identificativo documento incoerente")

        heartbeat.set(stage="indexing", progress=82, structure=structure, chunks_count=len(points))
        heartbeat.assert_owned()
        save_pdf_to_disk(content, kb_id, document_id)
        save_document_structure(structure, kb_id, document_id)
        index_price_document(structure, kb_id, document_id, job["filename"])
        for start in range(0, len(points), 100):
            heartbeat.assert_owned()
            batch = [PointStruct(id=pid, vector=vec, payload=payload) for pid, vec, payload in points[start:start + 100]]
            client.upsert(collection_name=collection_name, points=batch, wait=True)

        heartbeat.set(stage="publishing", progress=95, structure=structure, chunks_count=len(points))
        heartbeat.assert_owned()
        privileged("POST", "/rest/v1/documents", body={
            "document_id": document_id, "knowledge_id": kb_id, "filename": job["filename"],
            "chunks_count": len(points), "size_bytes": len(content),
        })
        heartbeat.stop()
        state.stage, state.progress = "completed", 100
        state.extractor, state.extractor_version = structure["extractor"], structure["extractor_version"]
        state.chunks_count = len(points)
        update_job(job_id, worker, state, status="succeeded")
        try:
            delete_import_pdf(kb_id, job_id)
        except OSError:
            logger.exception("Job %s completato, ma il PDF temporaneo non è stato rimosso", job_id)
    except LostLease:
        logger.warning("Worker %s ha perso la lease del job %s", worker, job_id)
        raise
    except Exception as exc:
        logger.error("Import job %s failed:\n%s", job_id, traceback.format_exc())
        try:
            if client is not None:
                # Revalidate ownership with the database before deleting artifacts;
                # another worker may have reclaimed the job during a long failure.
                heartbeat.set(stage=state.stage, progress=state.progress)
                _cleanup_partial(job, client, collection_name)
        except LostLease:
            logger.warning("Pulizia saltata per il job %s: lease già riassegnata", job_id)
            raise
        except Exception:
            logger.exception("Pulizia del job %s non riuscita", job_id)
        heartbeat.stop()
        state.stage, state.progress = "failed", 100
        try:
            update_job(job_id, worker, state, status="failed",
                       error_code=type(exc).__name__, error_message=_safe_error(exc))
        except LostLease:
            logger.warning("Impossibile marcare fallito il job %s: lease già riassegnata", job_id)
        raise
    finally:
        heartbeat.stop()
        operation_context.reset(usage_marker)
        if user_marker is not None:
            request_user.reset(user_marker)


def run_worker(*, once=False, stop_event: threading.Event | None = None) -> None:
    if not settings.supabase_admin_key:
        raise RuntimeError("SUPABASE_ADMIN_KEY è obbligatoria per il worker di importazione")
    if __import__("os").getenv("QDRANT_LOCAL_PATH"):
        raise RuntimeError("Il worker separato richiede Qdrant server; QDRANT_LOCAL_PATH embedded non è multiprocesso")
    worker = worker_identity()
    stop_event = stop_event or threading.Event()
    logger.info("Import worker avviato: %s", worker)
    while not stop_event.is_set():
        try:
            job = claim_job(worker)
            if job:
                try:
                    process_job(job, worker)
                except Exception:
                    pass
            elif once:
                return
            else:
                stop_event.wait(settings.import_worker_poll_seconds)
        except Exception:
            logger.exception("Errore nel ciclo del worker")
            if once:
                raise
            stop_event.wait(min(30, settings.import_worker_poll_seconds * 2))
        if once:
            return
