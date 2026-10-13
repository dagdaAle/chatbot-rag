"""Persistent worker success, rollback, lease and retry behavior."""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core import documents, import_jobs


class FakeClient:
    def __init__(self):
        self.points = []
        self.deleted = []

    def get_collections(self):
        return SimpleNamespace(collections=[SimpleNamespace(name="kb_test")])

    def delete(self, **kwargs):
        self.deleted.append(kwargs)

    def upsert(self, **kwargs):
        self.points.extend(kwargs["points"])


def job():
    return {
        "id": str(uuid4()), "document_id": str(uuid4()), "knowledge_id": str(uuid4()),
        "created_by": str(uuid4()), "filename": "regolamento.pdf", "size_bytes": 3,
    }


def setup_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(documents, "IMPORTS_DIR", tmp_path / "imports")
    monkeypatch.setattr(documents, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(documents, "EXTRACTED_DIR", tmp_path / "extracted")
    monkeypatch.setattr(import_jobs, "get_import_path", documents.get_import_path)
    monkeypatch.setattr(import_jobs, "delete_import_pdf", documents.delete_import_pdf)
    monkeypatch.setattr(import_jobs, "delete_pdf_from_disk", documents.delete_pdf_from_disk)
    monkeypatch.setattr(import_jobs, "save_pdf_to_disk", documents.save_pdf_to_disk)
    monkeypatch.setattr(import_jobs, "save_document_structure", documents.save_document_structure)


def test_worker_publishes_only_after_vectors_and_removes_pending(monkeypatch, tmp_path):
    current, client, events = job(), FakeClient(), []
    setup_paths(monkeypatch, tmp_path)
    documents.save_import_pdf(b"PDF", current["knowledge_id"], current["id"])
    monkeypatch.setattr(import_jobs, "get_client", lambda: client)
    monkeypatch.setattr(import_jobs, "get_collection_name", lambda _: "kb_test")
    monkeypatch.setattr(import_jobs, "ensure_collection_for_kb", lambda *args: None)
    monkeypatch.setattr(import_jobs, "process_pdf_to_points", lambda content, filename, progress, document_id: (
        progress("embedding", 55, {"extractor": "docling", "extractor_version": "2"}) or
        progress("indexing", 78, {"extractor": "docling", "extractor_version": "2"}, 1) or
        (document_id, [(str(uuid4()), [.1], {"document_id": document_id, "text": "ok"})],
         {"schema_version": 1, "extractor": "docling", "extractor_version": "2"})
    ))
    def privileged(method, path, **kwargs):
        events.append((method, path, kwargs))
        if "chatbot_update_import_job" in path:
            return True
        return []
    monkeypatch.setattr(import_jobs, "privileged", privileged)

    import_jobs.process_job(current, "worker-1")

    assert len(client.points) == 1
    publish = next(i for i, event in enumerate(events) if event[0:2] == ("POST", "/rest/v1/documents"))
    complete = next(i for i, event in enumerate(events) if event[2].get("body", {}).get("p_status") == "succeeded")
    assert publish < complete
    assert documents.get_upload_path(current["knowledge_id"], current["document_id"]).read_bytes() == b"PDF"
    assert not documents.get_import_path(current["knowledge_id"], current["id"]).exists()


def test_worker_failure_rolls_back_but_retains_pending_for_retry(monkeypatch, tmp_path):
    current, client, updates = job(), FakeClient(), []
    setup_paths(monkeypatch, tmp_path)
    documents.save_import_pdf(b"PDF", current["knowledge_id"], current["id"])
    monkeypatch.setattr(import_jobs, "get_client", lambda: client)
    monkeypatch.setattr(import_jobs, "get_collection_name", lambda _: "kb_test")
    monkeypatch.setattr(import_jobs, "ensure_collection_for_kb", lambda *args: None)
    monkeypatch.setattr(import_jobs, "process_pdf_to_points", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("PDF non valido")))
    def privileged(method, path, **kwargs):
        if "chatbot_update_import_job" in path:
            updates.append(kwargs["body"])
            return True
        return []
    monkeypatch.setattr(import_jobs, "privileged", privileged)

    with pytest.raises(ValueError, match="PDF non valido"):
        import_jobs.process_job(current, "worker-1")

    assert updates[-1]["p_status"] == "failed"
    assert updates[-1]["p_error_message"] == "PDF non valido"
    assert documents.get_import_path(current["knowledge_id"], current["id"]).exists()
    assert not documents.get_upload_path(current["knowledge_id"], current["document_id"]).exists()
    assert client.deleted


def test_lost_lease_is_detected(monkeypatch):
    monkeypatch.setattr(import_jobs, "_rpc", lambda *args, **kwargs: False)
    with pytest.raises(import_jobs.LostLease):
        import_jobs.update_job(str(uuid4()), "old-worker", import_jobs.JobState())


def test_worker_refuses_embedded_qdrant(monkeypatch):
    monkeypatch.setattr(import_jobs.settings, "supabase_admin_key", "configured")
    monkeypatch.setenv("QDRANT_LOCAL_PATH", "/data/qdrant")
    with pytest.raises(RuntimeError, match="Qdrant server"):
        import_jobs.run_worker(once=True)


def test_cleanup_does_not_delete_artifacts_after_losing_lease(monkeypatch, tmp_path):
    current, client = job(), FakeClient()
    setup_paths(monkeypatch, tmp_path)
    documents.save_import_pdf(b"PDF", current["knowledge_id"], current["id"])
    monkeypatch.setattr(import_jobs, "get_client", lambda: client)
    monkeypatch.setattr(import_jobs, "ensure_collection_for_kb", lambda *args: None)
    monkeypatch.setattr(import_jobs, "process_pdf_to_points", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("embedding unavailable")))
    cleanup_calls = []
    monkeypatch.setattr(import_jobs, "_cleanup_partial", lambda *args: cleanup_calls.append(args))
    responses = iter((True, False))
    monkeypatch.setattr(import_jobs, "_rpc", lambda *args, **kwargs: next(responses))
    with pytest.raises(import_jobs.LostLease):
        import_jobs.process_job(current, "old-worker")
    assert len(cleanup_calls) == 1  # Initial cleanup only; no failure-time deletion.
