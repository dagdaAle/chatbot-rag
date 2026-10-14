"""Privacy contract: inspect actual provider payloads, not just helper results."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
import re
from types import SimpleNamespace
import uuid

import pytest
import requests

from app.config import settings, runtime_config
from app.core import chat, privacy, embeddings


@pytest.fixture
def wire(monkeypatch):
    calls, vaults, provider_payloads = [], {}, []
    faults = {}
    names = ['Mario Rossi', 'Lucia Bianchi', 'mario.rossi@example.it', 'RSSMRA80A01H501U']

    def request(self, method, url, json=None, **kwargs):
        assert self.headers['X-Anonymizer-Token'] == 'test-only'
        assert kwargs['allow_redirects'] is False
        assert self.trust_env is False
        calls.append((method, url, json))
        mid = json.get('mapping_id') if json else url.rsplit('/', 1)[-1]
        if url.endswith('/v1/protect') or url.endswith('/v1/protect/extend'):
            if faults.get('timeout'):
                raise requests.Timeout('do not expose source text')
            table = dict(vaults.get(mid, {}))
            texts = list(json['texts'])
            for i, value in enumerate(names):
                token = f'<PII_{uuid.UUID(mid).hex}_PERSONA_{i + 1}>'
                if any(value in text for text in texts):
                    table[token] = value
                    texts = [text.replace(value, token) for text in texts]
            vaults[mid] = table
            result = dict(protocol_version=1, mapping_id=mid, recognizers_complete=True,
                          texts=texts, tokens=sorted(set(privacy.TOKEN_RE.findall('\n'.join(texts)))))
            result.update(faults.get('result', {}))
        elif url.endswith('/v1/restore'):
            text = json['text']
            replaced = len(privacy.TOKEN_RE.findall(text))
            for token, value in vaults[mid].items():
                text = text.replace(token, value)
            result = dict(protocol_version=1, mapping_id=mid, text=text, replaced=replaced)
            if faults.get('restore'):
                result['replaced'] = -1
        else:
            vaults.pop(mid, None)
            result = {'deleted': mid}
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None, json=lambda: result)

    def create(**kwargs):
        provider_payloads.append(kwargs)
        if faults.get('provider'):
            raise RuntimeError('private prompt or secret upstream error')
        text = kwargs['messages'][-1]['content']
        token = privacy.TOKEN_RE.findall(text)[0] if privacy.TOKEN_RE.search(text) else ''
        if faults.get('invent'):
            token = f'<PII_{uuid.uuid4().hex}_PERSONA_1>'
        if faults.get('malformed'):
            token = token[1:-1].lower()
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=f'{token}: [Fonte 1]'))], usage=None)

    monkeypatch.setattr(settings, 'anonymizer_token', 'test-only')
    monkeypatch.setattr(requests.Session, 'request', request)
    monkeypatch.setattr(chat, '_get_deepseek_client', lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    monkeypatch.setattr(chat, '_get_openai_client', lambda: pytest.fail('wrong provider'))
    from app.core import usage
    monkeypatch.setattr(usage, 'measure', lambda *args: nullcontext(SimpleNamespace(update=lambda **kwargs: None)))
    return SimpleNamespace(calls=calls, vaults=vaults, payloads=provider_payloads, faults=faults)


def generate(name='Mario Rossi', history=None):
    return chat.generate_response(f'Qual è il recapito di {name}?', [
        dict(filename='RISERVATO_Mario_Rossi.pdf', section_path=[name],
             text=f'{name}: mario.rossi@example.it, CF RSSMRA80A01H501U. Atto 123/2026: 12,50 EUR.')],
        conversation_history=history, provider='deepseek', model='deepseek-flash')


def test_all_outgoing_fields_and_restore(wire, monkeypatch):
    monkeypatch.setattr(chat, 'get_system_prompt', lambda: 'Il referente è Mario Rossi.')
    answer = generate(history=[dict(role='user', content='Mario Rossi'), dict(role='assistant', content='RSSMRA80A01H501U')])
    assert 'Mario Rossi' in answer and '[Fonte 1]' in answer
    sent = str(wire.payloads[0]['messages'])
    for original in ['Mario Rossi', 'mario.rossi@example.it', 'RSSMRA80A01H501U', 'RISERVATO_Mario_Rossi.pdf']:
        assert original not in sent
    assert '123/2026' in sent and '12,50 EUR' in sent
    assert wire.payloads[0]['extra_body'] == {'thinking': {'type': 'disabled'}}
    assert not wire.vaults
    assert wire.calls[-1][0] == 'DELETE'


@pytest.mark.parametrize('result', [
    {'texts': []}, {'texts': [None]}, {'recognizers_complete': False}, {'protocol_version': 9},
    {'mapping_id': 'other'}, {'tokens': ['<PERSONA_1>']}, {'tokens': []},
])
def test_invalid_protection_never_calls_provider(wire, result):
    wire.faults['result'] = result
    with pytest.raises(privacy.PrivacyError):
        generate()
    assert not wire.payloads and not wire.vaults


def test_timeout_never_calls_provider(wire):
    wire.faults['timeout'] = True
    with pytest.raises(privacy.PrivacyError, match='non disponibile'):
        generate()
    assert not wire.payloads
    assert wire.calls[-1][0] == 'DELETE'


@pytest.mark.parametrize('fault', ['provider', 'restore', 'invent', 'malformed'])
def test_failed_output_is_not_saved_and_map_is_deleted(wire, fault):
    wire.faults[fault] = True
    with pytest.raises(privacy.PrivacyError) as error:
        generate()
    assert 'secret' not in str(error.value)
    assert not wire.vaults


def test_no_token_never_calls_any_service(wire, monkeypatch):
    monkeypatch.setattr(settings, 'anonymizer_token', '')
    with pytest.raises(privacy.PrivacyError):
        generate()
    assert not wire.calls and not wire.payloads


def test_batch_limit_before_transmission(wire, monkeypatch):
    monkeypatch.setattr(settings, 'anonymizer_max_chars', 10)
    with pytest.raises(privacy.PrivacyError):
        generate()
    assert not wire.payloads
    assert not any(url.endswith('/v1/protect') for _, url, _ in wire.calls)


def test_parallel_requests_have_separate_maps(wire):
    with ThreadPoolExecutor(max_workers=2) as pool:
        answers = list(pool.map(generate, ['Mario Rossi', 'Lucia Bianchi']))
    assert answers == ['Mario Rossi: [Fonte 1]', 'Lucia Bianchi: [Fonte 1]']
    mids = [body['mapping_id'] for _, url, body in wire.calls if url.endswith('/v1/protect')]
    assert len(set(mids)) == 2 and not wire.vaults


def test_ollama_chat_stays_local(wire, monkeypatch):
    monkeypatch.setattr(chat, 'ollama_generate_chat_response', lambda *args, **kwargs: 'locale')
    assert chat.generate_response('test', [dict(filename='a', text='b')], provider='ollama') == 'locale'
    assert not wire.calls and not wire.payloads


@pytest.mark.parametrize('batch', [False, True])
def test_remote_embeddings_are_blocked_before_client(wire, monkeypatch, batch):
    monkeypatch.setattr(runtime_config, 'embedding_provider', 'openai')
    monkeypatch.setattr(embeddings, '_get_openai_client', lambda: pytest.fail('unprotected embedding egress'))
    with pytest.raises(privacy.PrivacyError):
        embeddings.get_embeddings_batch(['Mario Rossi']) if batch else embeddings.get_query_embedding('Mario Rossi')
