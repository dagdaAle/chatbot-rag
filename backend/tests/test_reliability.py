import os
import tempfile
os.environ['DATA_DIR'] = tempfile.mkdtemp()
os.environ['QDRANT_LOCAL_PATH'] = tempfile.mkdtemp()
import pytest
from app.core.documents import chunk_text_with_pages
from app.core.qdrant_client import get_client, ensure_collection_for_kb
from app.core import chat
from app.config import runtime_config
from app.core.knowledge import create_knowledge, list_knowledges
from fastapi.testclient import TestClient
from app.main import app


def test_chunking_progress_and_final_chunk():
    text = 'Titolo\n\n' + 'testo lungo ' * 300
    chunks = chunk_text_with_pages([text])
    assert 1 < len(chunks) < 10
    assert chunks[0]['text'].startswith('Titolo')
    assert chunks[-1]['text'].endswith('testo lungo')
    assert len(chunk_text_with_pages(['Testo breve.'])) == 1


def test_page_offsets_preserved():
    chunks = chunk_text_with_pages(['   Prima pagina', 'Seconda pagina'])
    assert chunks[0]['page_start'] == 1
    assert chunks[0]['page_end'] == 2


def test_no_destructive_dimension_change():
    from qdrant_client.models import PointStruct
    client = get_client()
    ensure_collection_for_kb(client, 'test')
    client.upsert('test', [PointStruct(id=1, vector=[1.0] * 1536, payload={})])
    original = runtime_config.embedding_model
    try:
        runtime_config.embedding_model = 'nomic-embed-text'
        with pytest.raises(ValueError):
            ensure_collection_for_kb(client, 'test', recreate_if_wrong_size=True)
        assert client.get_collection('test').points_count == 1
    finally:
        runtime_config.embedding_model = original


def test_embedding_change_refused_even_same_dimensions():
    with TestClient(app) as client:
        response = client.put('/api/settings/models/embedding', json={'provider':'ollama','model_id':'other-model'})
        assert response.status_code == 409


def test_threshold_is_respected(monkeypatch):
    from types import SimpleNamespace
    class FakeClient:
        def get_collections(self): return SimpleNamespace(collections=[SimpleNamespace(name='documents')])
        def search(self, **kwargs): return [SimpleNamespace(score=0.1)]
    monkeypatch.setattr(chat, 'get_client', lambda: FakeClient())
    monkeypatch.setattr(chat, 'get_query_embedding', lambda text: [1.0])
    assert chat.retrieve_context('unrelated', score_threshold=0.3) == []


def test_follow_up_uses_history_and_sources_keep_kb(monkeypatch):
    captured = {}
    def retrieve(query, **kwargs):
        captured['query'] = query
        return [dict(filename='a.pdf', text='scadenza', document_id='d', chunk_index=0, score=.8)]
    monkeypatch.setattr(chat, 'retrieve_context', retrieve)
    monkeypatch.setattr(chat, 'generate_response', lambda *args: 'risposta')
    result = chat.chat('E le scadenze?', knowledge_id='kb', conversation_history=[{'role':'user','content':'Bando Verona'}])
    assert 'Bando Verona' in captured['query']
    assert result['sources'][0]['knowledge_id'] == 'kb'


def test_concurrent_knowledge_updates():
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(lambda n: create_knowledge(f'kb-{n}').id, range(8)))
    assert set(ids).issubset({kb.id for kb in list_knowledges()})


def test_spa_deep_links_and_unknown_api(tmp_path):
    from fastapi import FastAPI
    from app.main import SPAStaticFiles
    (tmp_path / 'index.html').write_text('<html>app</html>')
    test_app = FastAPI()
    test_app.mount('/', SPAStaticFiles(directory=tmp_path, html=True))
    with TestClient(test_app) as client:
        assert client.get('/c/test').status_code == 200
        assert client.get('/pdf-viewer').status_code == 200
        assert client.get('/api/unknown').status_code == 404


def test_runtime_configuration_survives_restart():
    from app.config import RuntimeConfig
    original = runtime_config.chat_model
    try:
        runtime_config.chat_model = 'configured-model'
        runtime_config.save()
        assert RuntimeConfig().chat_model == 'configured-model'
    finally:
        runtime_config.chat_model = original
        runtime_config.save()
