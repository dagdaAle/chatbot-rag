import os
import tempfile
os.environ['EMBEDDING_PROVIDER'] = 'openai'
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
    from app.auth import current_user, User
    async def admin():
        yield User('00000000-0000-0000-0000-000000000001', 'test', True)
    app.dependency_overrides[current_user] = admin
    with TestClient(app) as client:
        response = client.put('/api/settings/models/embedding', json={'provider':'ollama','model_id':'other-model'})
        assert response.status_code == 409
    app.dependency_overrides.clear()


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
    monkeypatch.setattr(chat, 'generate_response', lambda *args, **kwargs: 'risposta')
    result = chat.chat('E le scadenze?', knowledge_id='kb', conversation_history=[{'role':'user','content':'Bando Verona'}])
    assert 'Bando Verona' in captured['query']
    assert result['sources'][0]['knowledge_id'] == 'kb'


def test_concurrent_json_writes_are_atomic(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from app.core.storage import write_json
    import json
    target = tmp_path / 'prompt.json'
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda n: write_json(target, {'value': 'x' * 1000, 'n': n}), range(8)))
    assert json.loads(target.read_text())['value'] == 'x' * 1000
    assert not list(tmp_path.glob('.pending-*'))


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


def test_deepseek_uses_dedicated_client(monkeypatch):
    from types import SimpleNamespace
    captured = {}
    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='ok'))],usage=None)
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(chat, '_get_deepseek_client', lambda: fake)
    monkeypatch.setattr(chat, '_get_openai_client', lambda: pytest.fail('OpenAI must not be called'))
    monkeypatch.setattr(runtime_config, 'chat_provider', 'deepseek')
    monkeypatch.setattr(runtime_config, 'chat_model', 'deepseek-flash')
    assert chat.generate_response('test', [{'filename':'a.pdf','text':'test'}]) == 'ok'
    assert captured['model'] == 'deepseek-flash'
    assert captured['extra_body']['thinking']['type'] == 'disabled'


def test_ollama_embeddings_work_without_openai_key(monkeypatch):
    from app.core import embeddings
    from app.config import settings
    monkeypatch.setattr(settings, 'openai_api_key', '')
    monkeypatch.setattr(runtime_config, 'embedding_provider', 'ollama')
    monkeypatch.setattr(runtime_config, 'embedding_model', 'nomic-embed-text')
    monkeypatch.setattr(embeddings, 'ollama_generate_embedding', lambda text, model, **kwargs: [0.5] * 768)
    assert len(embeddings.get_query_embedding('test')) == 768


def test_bge_model_is_embedding_not_chat(monkeypatch):
    from app.api import models
    monkeypatch.setattr(models, '_fetch_ollama_models', lambda: [models.ModelInfo(id='bge-m3:latest',name='bge-m3',provider='ollama')])
    from app.core import supabase
    monkeypatch.setattr(supabase, 'rest', lambda *args, **kwargs: [])
    assert not any(m.id == 'bge-m3:latest' for m in models.list_chat_models().models)
    assert any(m.id == 'bge-m3:latest' for m in models.list_embedding_models().models)
