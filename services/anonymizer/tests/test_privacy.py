"""Security contract and lifecycle tests, independent of the GPU model download."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import re
import sqlite3
from types import SimpleNamespace
from uuid import uuid4

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from presidio_analyzer import RecognizerResult
import pytest

from app import main
from app.engine import Anonymizer
from app.recognizers.gliner_ner import GlinerRecognizer
from app.vault import Vault


@pytest.fixture
def engine(tmp_path):
    service = Anonymizer(Vault(tmp_path / 'vault.db', Fernet.generate_key().decode()), None, 'it_core_news_sm')
    yield service
    service.vault.close()


@pytest.fixture
def api(engine, monkeypatch):
    monkeypatch.setattr(main, 'TOKEN', 'test-only')
    main.state.update(engine=engine, complete=True, pending=0, semaphore=asyncio.Semaphore(1))
    # No lifespan: unit tests inject a CPU engine; test incomplete readiness separately.
    client = TestClient(main.app)
    client.headers['X-Anonymizer-Token'] = 'test-only'
    yield client
    client.close()
    main.state.clear()


def test_lowercase_fixed_formats(engine):
    for value, label in [('rssmra80a01h501u', 'CODICE_FISCALE'), ('it60x0542811101000000123456', 'IBAN')]:
        out, _, found = engine.anonymize(f'Codice fiscale o IBAN: {value}', 'redact', None)
        assert value not in out and label in [item.entity_type for item in found]


def test_later_detection_propagates_to_earlier_field(engine, monkeypatch):
    def analyze(text, *args):
        if text.startswith('Documento'):
            start = text.index('Mario Rossi')
            return [RecognizerResult('PERSONA', start, start + len('Mario Rossi'), .9)]
        return []
    monkeypatch.setattr(engine, 'analyze', analyze)
    mid = str(uuid4())
    engine.vault.create_temporary(mid, 900)
    texts, tokens = engine.protect_batch(['Dov’è Mario Rossi?', 'Documento: Mario Rossi'], mid, .5)
    assert all('Mario Rossi' not in text for text in texts)
    assert len(tokens) == 1 and all(tokens[0] in text for text in texts)
    assert texts[0].endswith('?')


def test_exact_propagation_does_not_merge_different_people(engine, monkeypatch):
    text = 'Mario Rossi e Maria Rossi e Rossi'
    monkeypatch.setattr(engine, 'analyze', lambda *args: [RecognizerResult('PERSONA', 0, 11, .9)])
    mid = str(uuid4())
    engine.vault.create_temporary(mid, 900)
    protected, _ = engine.protect_batch([text], mid, .5)
    assert 'Mario Rossi' not in protected[0]
    assert 'Maria Rossi e Rossi' in protected[0]


def test_namespaced_tokens_roundtrip_and_no_loose_restore(api):
    mid = str(uuid4())
    response = api.post('/v1/protect', json={'mapping_id': mid, 'texts': ['a@example.it', 'a@example.it']})
    assert response.status_code == 200
    result = response.json()
    token, = result['tokens']
    assert token == f'<PII_{mid.replace("-", "")}_EMAIL_1>'
    assert result['texts'] == [token, token]
    restored = api.post('/v1/restore', json={'mapping_id': mid, 'text': token, 'allowed_tokens': [token]})
    assert restored.json()['text'] == 'a@example.it' and restored.json()['replaced'] == 1
    loose = api.post('/v1/restore', json={'mapping_id': mid, 'text': token[1:-1], 'allowed_tokens': [token]})
    assert loose.json()['text'] == token[1:-1] and loose.json()['replaced'] == 0
    assert api.delete(f'/mappings/{mid}').status_code == 200
    assert api.post('/v1/restore', json={'mapping_id': mid, 'text': token, 'allowed_tokens': [token]}).status_code == 404


def test_cross_map_and_unemitted_tokens_rejected(api):
    first, second = str(uuid4()), str(uuid4())
    a = api.post('/v1/protect', json={'mapping_id': first, 'texts': ['a@example.it']}).json()['tokens'][0]
    b = api.post('/v1/protect', json={'mapping_id': second, 'texts': ['b@example.it']}).json()['tokens'][0]
    assert a != b
    assert api.post('/v1/restore', json={'mapping_id': first, 'text': b, 'allowed_tokens': [a]}).status_code == 422
    assert api.post('/v1/restore', json={'mapping_id': first, 'text': a, 'allowed_tokens': []}).status_code == 422
    assert api.post('/v1/protect', json={'mapping_id': first, 'texts': ['c@example.it']}).status_code == 409


def test_missing_token_and_incomplete_recognizers(api):
    body = {'mapping_id': str(uuid4()), 'texts': ['a@example.it']}
    assert api.post('/v1/protect', json=body, headers={'X-Anonymizer-Token': ''}).status_code == 401
    main.state['complete'] = False
    assert api.post('/v1/protect', json=body).status_code == 503


def test_agent_extension_preserves_old_tokens_and_restores_both_steps(api):
    mid = str(uuid4())
    first = api.post('/v1/protect', json={'mapping_id': mid, 'texts': ['a@example.it']}).json()
    old, = first['tokens']
    result = api.post('/v1/protect/extend', json={'mapping_id': mid, 'texts': [
        f'Prima fonte: {old}', 'Seconda fonte: b@example.it; contatto a@example.it']})
    assert result.status_code == 200
    output = result.json()
    assert len(output['tokens']) == 2 and old in output['tokens']
    assert output['texts'][0] == f'Prima fonte: {old}'
    assert 'b@example.it' not in output['texts'][1] and old in output['texts'][1]
    restored = api.post('/v1/restore', json={'mapping_id': mid, 'text': ' '.join(output['texts']),
                                          'allowed_tokens': output['tokens']})
    assert restored.status_code == 200 and 'a@example.it' in restored.json()['text']
    assert 'b@example.it' in restored.json()['text']


def test_extension_reuses_known_names_across_steps(engine, monkeypatch):
    def analyze(text, *args):
        if text.startswith('Documento') and 'Mario Rossi' in text:
            start = text.index('Mario Rossi')
            return [RecognizerResult('PERSONA', start, start + 11, .9)]
        return []
    monkeypatch.setattr(engine, 'analyze', analyze)
    mid = str(uuid4())
    engine.vault.create_temporary(mid, 900)
    first, tokens = engine.protect_batch(['Documento Mario Rossi'], mid, .5)
    second, emitted = engine.protect_batch([first[0], 'Domanda su Mario Rossi'], mid, .5)
    assert second[0] == first[0] and tokens == emitted
    assert 'Mario Rossi' not in second[1]


def test_extension_rejects_foreign_expired_persistent_and_missing_maps(api, engine):
    mid = str(uuid4())
    body = {'mapping_id': mid, 'texts': ['a@example.it']}
    assert api.post('/v1/protect/extend', json=body).status_code == 404
    engine.vault.ensure_mapping(mid)
    assert api.post('/v1/protect/extend', json=body).status_code == 404
    engine.vault.delete(mid)
    engine.vault.create_temporary(mid, -1)
    assert api.post('/v1/protect/extend', json=body).status_code == 404
    engine.vault.delete(mid)
    api.post('/v1/protect', json=body)
    foreign = f'<PII_{uuid4().hex}_EMAIL_1>'
    assert api.post('/v1/protect/extend', json={**body, 'texts': [foreign]}).status_code == 422
    assert api.post('/v1/protect/extend', json=body, headers={'X-Anonymizer-Token': ''}).status_code == 401
    main.state['complete'] = False
    assert api.post('/v1/protect/extend', json=body).status_code == 503


def test_extension_failure_deletes_map(api, engine, monkeypatch):
    mid = str(uuid4())
    api.post('/v1/protect', json={'mapping_id': mid, 'texts': ['a@example.it']})
    def fail(*args):
        raise RuntimeError('PRIVATE')
    monkeypatch.setattr(engine, 'protect_batch', fail)
    result = api.post('/v1/protect/extend', json={'mapping_id': mid, 'texts': ['b@example.it']})
    assert result.status_code == 503 and 'PRIVATE' not in result.text
    assert not engine.vault.exists(mid)


def test_limits_and_queue_admission(api):
    assert api.post('/v1/protect', json={'mapping_id': str(uuid4()), 'texts': ['a' * 100001] * 2}).status_code == 422
    assert api.post('/v1/protect', json={'mapping_id': str(uuid4()), 'texts': ['a'] * 65}).status_code == 422
    main.state['pending'] = main.MAX_PENDING
    assert api.post('/v1/protect', json={'mapping_id': str(uuid4()), 'texts': ['a']}).status_code == 503


def test_failure_deletes_partial_map(api, engine, monkeypatch):
    def fail(*args):
        raise RuntimeError('PRIVATE ORIGINAL TEXT')
    monkeypatch.setattr(engine, 'protect_batch', fail)
    mid = str(uuid4())
    response = api.post('/v1/protect', json={'mapping_id': mid, 'texts': ['a@example.it']})
    assert response.status_code == 503
    assert 'PRIVATE' not in response.text
    assert not engine.vault.exists(mid)


def test_expiry_preserves_legacy_and_migrates_old_schema(tmp_path):
    path = tmp_path / 'old.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE mappings (id TEXT PRIMARY KEY, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
        db.execute("INSERT INTO mappings(id) VALUES ('legacy')")
    vault = Vault(path, Fernet.generate_key().decode())
    mid = str(uuid4())
    vault.create_temporary(mid, -1)
    vault.token_for(mid, 'EMAIL', 'a@example.it')
    assert not vault.exists(mid)
    assert vault.expire() == 1 and not vault.lookup(mid)
    assert vault.exists('legacy')
    vault.close()


def test_parallel_vaults_do_not_share_values(engine):
    def run(value):
        mid = str(uuid4())
        engine.vault.create_temporary(mid, 900)
        token = engine.vault.token_for(mid, 'PERSONA', value)
        return token, engine.deanonymize(token, mid)[0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ['Mario Rossi', 'Lucia Bianchi']))
    assert results[0][0] != results[1][0]
    assert [value for _, value in results] == ['Mario Rossi', 'Lucia Bianchi']


def test_token_aware_windows_cover_dense_tail(monkeypatch):
    monkeypatch.setattr(GlinerRecognizer, 'load', lambda self: None)
    recognizer = GlinerRecognizer('fake', 'cpu')
    splitter = lambda text: ((m.group(), m.start(), m.end()) for m in re.finditer(r'\S+', text))
    tokenizer = SimpleNamespace(encode=lambda text, **kwargs: [0] * (len(text.split()) * 8))
    recognizer.model = SimpleNamespace(config=SimpleNamespace(max_len=384), data_processor=SimpleNamespace(
        words_splitter=splitter, transformer_tokenizer=tokenizer))
    text = ' '.join(f'codice{i}' for i in range(700)) + ' Mario Rossi'
    windows = list(recognizer._model_windows(text))
    assert len(windows) > 2 and windows[-1][1].endswith('Mario Rossi')
    assert all(len(tokenizer.encode(chunk)) <= 320 for _, chunk in windows)
    covered = set()
    for offset, chunk in windows:
        covered.update(range(offset, offset + len(chunk)))
    assert all(index in covered for index, char in enumerate(text) if not char.isspace())


def test_startup_requires_token(monkeypatch):
    monkeypatch.setattr(main, 'TOKEN', '')
    monkeypatch.setenv('ANONYMIZER_KEY', Fernet.generate_key().decode())
    with pytest.raises(RuntimeError, match='obbligatori'):
        with TestClient(main.app):
            pass


def test_disabled_gliner_is_not_ready_for_chat(monkeypatch, tmp_path):
    monkeypatch.setattr(main, 'TOKEN', 'test-only')
    monkeypatch.setenv('ANONYMIZER_KEY', Fernet.generate_key().decode())
    monkeypatch.setattr(main, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(main, 'DISABLE_GLINER', True)
    with TestClient(main.app) as client:
        assert client.get('/health').json()['recognizers_complete'] is False
        assert client.post('/v1/protect', headers={'X-Anonymizer-Token': 'test-only'},
                           json={'mapping_id': str(uuid4()), 'texts': ['Mario Rossi']}).status_code == 503
