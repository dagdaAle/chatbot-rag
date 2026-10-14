"""Inspect real outgoing transcripts and tool effects over a scripted model."""
from copy import deepcopy
import json
from types import SimpleNamespace as NS

import pytest

from app.config import settings
from app.core import agentic, chat, privacy
from test_privacy import wire

KB = '00000000-0000-0000-0000-000000000001'


def source(document='doc1', text='Mario Rossi: mario.rossi@example.it. Atto 123/2026.', index=0):
    return dict(document_id=document, text=text, filename='RISERVATO_Mario_Rossi.pdf',
                chunk_index=index, score=.8, section_path=['Articolo 1'], section_refs=['s1'])


def response(content='', calls=None, reasoning='', finish=None, tokens=100):
    return NS(usage=NS(prompt_tokens=200, completion_tokens=tokens), choices=[NS(
        finish_reason=finish or ('tool_calls' if calls else 'stop'),
        message=NS(content=content, tool_calls=calls, reasoning_content=reasoning))])


def call(name, args, id='call_1'):
    return NS(id=id, type='function', function=NS(name=name, arguments=json.dumps(args, ensure_ascii=False)))


@pytest.fixture
def agent(wire, monkeypatch):
    script, queries, options = [], [], []
    monkeypatch.setattr(settings, 'agentic_rag_enabled', True)
    monkeypatch.setattr(settings, 'agentic_reasoning_effort', 'none')
    monkeypatch.setattr(settings, 'agentic_max_steps', 3)
    monkeypatch.setattr(settings, 'agentic_max_tool_calls', 6)
    monkeypatch.setattr(settings, 'agentic_max_output_tokens', 12000)
    monkeypatch.setattr(settings, 'agentic_max_input_bytes', 250000)
    monkeypatch.setattr(agentic, 'published_document_ids', lambda kb: {'doc1', 'doc2'})
    monkeypatch.setattr(agentic, 'get_knowledge', lambda kb: {'id': KB})

    def retrieve(query, **kwargs):
        queries.append((query, kwargs))
        return [source()] if len(queries) == 1 else [source('doc2', 'Lucia Bianchi: eccezione al requisito.', 1)]

    def create(**kwargs):
        wire.payloads.append(deepcopy(kwargs))
        assert script, 'unexpected model call'
        item = script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item(kwargs) if callable(item) else item

    def with_options(**kwargs):
        options.append(kwargs)
        return NS(chat=NS(completions=NS(create=create)))

    monkeypatch.setattr(chat, '_get_deepseek_client', lambda: NS(with_options=with_options))
    monkeypatch.setattr(chat, 'retrieve_context', retrieve)
    monkeypatch.setattr(agentic, 'get_client', lambda: None)
    monkeypatch.setattr(agentic, 'get_collection_name', lambda kb: 'collection')
    monkeypatch.setattr(agentic, 'expand_hierarchical_contexts', lambda *args, **kwargs: [
        {**source(text='Mario Rossi: sezione completa, inclusa eccezione.'), 'section_complete': True, 'context_scope': 'section'}])
    return NS(wire=wire, script=script, queries=queries, options=options)


def run():
    return agentic.research('Quali regole valgono per Mario Rossi?', [], KB,
                            top_k=6, score_threshold=.3, model='deepseek-flash')


def test_search_refinement_roundtrip_and_stable_sources(agent):
    def refine(kwargs):
        token = privacy.TOKEN_RE.findall(kwargs['messages'][-1]['content'])[0]
        return response(calls=[call('search_documents', {'query': f'eccezioni per {token}'})])
    def final(kwargs):
        text = kwargs['messages'][-1]['content']
        token = next(t for t in privacy.TOKEN_RE.findall(text) if 'PERSONA_2' in t)
        return response(f'{token}: eccezione [Fonte 2]. Requisito [Fonte 1].')
    agent.script.extend([refine, final])
    result = run()
    assert result['answer'].startswith('Lucia Bianchi')
    assert result['research'] == dict(model_calls=2, tool_calls=1, stop_reason='completed')
    assert [item['document_id'] for item in result['sources']] == ['doc1', 'doc2']
    assert 'Mario Rossi' in agent.queries[1][0]  # restored only for local retrieval
    assert agent.queries[1][1]['document_ids'] == {'doc1', 'doc2'}
    sent = str(agent.wire.payloads)
    for secret in ['Mario Rossi', 'Lucia Bianchi', 'mario.rossi@example.it', 'RISERVATO_Mario_Rossi.pdf']:
        assert secret not in sent
    assert '123/2026' in sent
    assert not agent.wire.vaults
    mids = {body['mapping_id'] for _, url, body in agent.wire.calls if '/protect' in url}
    assert len(mids) == 1
    assert any(url.endswith('/v1/protect/extend') for _, url, _ in agent.wire.calls)
    assert agent.options[0]['max_retries'] == 0
    assert all(0 < opt['timeout'] <= settings.agentic_timeout_seconds for opt in agent.options)


def test_read_full_section_and_keep_original_reference(agent):
    agent.script.extend([response(calls=[call('read_section', {'source_id': 1})]),
                         response('Sezione completa [Fonte 2].')])
    result = run()
    assert len(result['sources']) == 2
    assert not result['sources'][0].get('section_complete')
    assert result['sources'][1]['section_complete'] is True


def test_unauthorized_retrieval_never_reaches_provider(agent, monkeypatch):
    monkeypatch.setattr(chat, 'retrieve_context', lambda *args, **kwargs: [source('other-tenant', 'TOP SECRET')])
    agent.script.append(response('Risposta inventata senza prove.'))
    result = run()
    assert result['sources'] == [] and result['answer'] == agentic.NO_EVIDENCE
    assert 'TOP SECRET' not in str(agent.wire.payloads)


def test_unknown_tool_blocks_execution_and_cleans_up(agent):
    agent.script.append(response(calls=[call('run_sql', {'sql': 'select * from secrets'})]))
    with pytest.raises(agentic.AgentError, match='strumento non valido'):
        run()
    assert len(agent.queries) == 1 and not agent.wire.vaults


@pytest.mark.parametrize('args', [
    {'query': 'test', 'knowledge_id': 'other'}, {'query': 'test', 'top_k': 100},
    {'query': 'test', 'top_k': True}, {'query': ''}, {'query': 'test', 'document_ref': 'D999'},
])
def test_invalid_tool_arguments_have_no_search_effect(agent, args):
    agent.script.extend([response(calls=[call('search_documents', args)]), response('Prova [Fonte 1].')])
    result = run()
    assert len(agent.queries) == 1 and result['research']['tool_calls'] == 1
    assert 'error' in agent.wire.payloads[-1]['messages'][-1]['content']


def test_duplicate_queries_do_not_repeat_retrieval(agent):
    agent.script.extend([response(calls=[call('search_documents', {'query': 'eccezioni'})]),
                         response(calls=[call('search_documents', {'query': 'eccezioni'}, 'call_2')]),
                         response('Eccezione [Fonte 2].')])
    run()
    assert len(agent.queries) == 2
    assert 'già eseguita' in agent.wire.payloads[-1]['messages'][-1]['content']


def test_max_rounds_force_final_without_tools(agent, monkeypatch):
    monkeypatch.setattr(settings, 'agentic_max_steps', 1)
    agent.script.extend([response(calls=[call('search_documents', {'query': 'eccezioni'})]),
                         response('Prova [Fonte 1].')])
    result = run()
    assert agent.wire.payloads[-1]['tool_choice'] == 'none'
    assert result['research']['stop_reason'] == 'step_limit'
    assert 'potrebbero non essere esaustive' in result['answer']


def test_max_tools_does_not_execute_oversized_batch(agent, monkeypatch):
    monkeypatch.setattr(settings, 'agentic_max_tool_calls', 1)
    agent.script.append(response(calls=[call('search_documents', {'query': 'a'}),
                                       call('search_documents', {'query': 'b'}, 'call_2')]))
    result = run()
    assert len(agent.queries) == 1 and result['answer'] == agentic.LIMIT_ANSWER


@pytest.mark.parametrize('bad', ['Senza citazioni.', 'Documento [Fonte 99].', 'Documento [Fonte 0].'])
def test_invalid_citations_are_repaired_before_answer(agent, bad):
    agent.script.extend([response(bad), response('Risposta corretta [Fonte 1].')])
    result = run()
    assert result['answer'] == 'Risposta corretta [Fonte 1].'
    assert result['research']['model_calls'] == 2


def test_repeated_invalid_citations_never_publish_model_answer(agent):
    agent.script.extend([response('Inventata [Fonte 999].') for _ in range(4)])
    result = run()
    assert result['research']['stop_reason'] == 'invalid_citations'
    assert 'Inventata' not in result['answer']


def test_output_and_input_budgets_stop_further_calls(agent, monkeypatch):
    monkeypatch.setattr(settings, 'agentic_max_output_tokens', 1000)
    agent.script.append(response(calls=[call('search_documents', {'query': 'eccezioni'})], tokens=1000))
    result = run()
    assert result['research']['model_calls'] == 1 and result['answer'] == agentic.LIMIT_ANSWER
    agent.wire.payloads.clear()
    monkeypatch.setattr(settings, 'agentic_max_input_bytes', 1)
    result = run()
    assert not agent.wire.payloads and result['research']['stop_reason'] == 'budget_limit'


def test_truncated_answer_is_not_published(agent):
    agent.script.append(response('Parziale [Fonte 1].', finish='length'))
    assert run()['answer'] == agentic.LIMIT_ANSWER


def test_provider_failure_is_safe_and_deletes_map(agent):
    agent.script.append(RuntimeError('PRIVATE PROMPT/API KEY'))
    with pytest.raises(agentic.AgentError) as error:
        run()
    assert 'PRIVATE' not in str(error.value) and not agent.wire.vaults


def test_later_privacy_failure_prevents_second_provider_call(agent):
    agent.script.append(response(calls=[call('search_documents', {'query': 'eccezioni'})]))
    original = privacy.ProtectedRequest.protect_texts
    def protect(self, texts):
        if self.created:
            raise privacy.PrivacyError('Protezione non disponibile')
        return original(self, texts)
    from unittest.mock import patch
    with patch.object(privacy.ProtectedRequest, 'protect_texts', protect), pytest.raises(privacy.PrivacyError):
        run()
    assert len(agent.wire.payloads) == 1 and not agent.wire.vaults


def test_invented_query_token_is_rejected_before_internal_search(agent):
    agent.script.append(response(calls=[call('search_documents', {'query': '<PII_' + 'f' * 32 + '_PERSONA_1>'})]))
    with pytest.raises(privacy.PrivacyError):
        run()
    assert len(agent.queries) == 1 and not agent.wire.vaults


def test_reasoning_is_retained_protected_and_not_returned(agent, monkeypatch):
    monkeypatch.setattr(settings, 'agentic_reasoning_effort', 'low')
    agent.script.extend([response(calls=[call('read_section', {'source_id': 1})], reasoning='Cerco eccezioni per Mario Rossi.'),
                         response('Prova [Fonte 2].', reasoning='Ragionamento privato.')])
    result = run()
    assistant = next(m for m in agent.wire.payloads[1]['messages'] if m['role'] == 'assistant')
    assert 'Mario Rossi' not in assistant['reasoning_content'] and '<PII_' in assistant['reasoning_content']
    assert agent.wire.payloads[0]['extra_body']['thinking']['type'] == 'enabled'
    assert 'Ragionamento privato' not in str(result)


def test_reasoning_is_preserved_during_citation_repair(agent, monkeypatch):
    monkeypatch.setattr(settings, 'agentic_reasoning_effort', 'low')
    agent.script.extend([response('Senza citazioni.', reasoning='Ragionamento da mantenere.'),
                         response('Prova [Fonte 1].')])
    run()
    assistant = next(m for m in agent.wire.payloads[1]['messages'] if m['role'] == 'assistant')
    assert assistant['reasoning_content'] == 'Ragionamento da mantenere.'


def test_expired_deadline_does_not_execute_proposed_tools(agent, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(agentic, 'monotonic', lambda: clock[0])
    def expire(kwargs):
        clock[0] = settings.agentic_timeout_seconds + 1
        return response(calls=[call('search_documents', {'query': 'eccezioni'})])
    agent.script.append(expire)
    result = run()
    assert len(agent.queries) == 1 and result['research']['tool_calls'] == 0
    assert result['answer'] == agentic.LIMIT_ANSWER and not agent.wire.vaults


def test_protection_canonicalizes_json_escapes_before_detection(agent):
    with privacy.protected_session() as protected:
        messages = protected.protect_messages([
            {'role': 'system', 'content': 'Assistente'},
            {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'call_1', 'type': 'function',
                'function': {'name': 'search_documents', 'arguments': '{"query":"\\u004dario Rossi"}'}}]}])
        arguments = messages[1]['tool_calls'][0]['function']['arguments']
        assert 'Mario Rossi' not in arguments and '<PII_' in arguments
        assert messages[1]['tool_calls'][0]['id'] == 'call_1'
        assert protected.restore(json.loads(arguments)['query']) == 'Mario Rossi'


def test_evidence_budget_marks_partial_section_and_keeps_stable_identity(monkeypatch):
    monkeypatch.setattr(settings, 'retrieval_total_max_chars', 5)
    evidence = agentic.Evidence()
    item = {**source(text='abcdefgh'), 'section_complete': True}
    assert evidence.add(item, {'doc1'}) == 1
    assert evidence.add(item, {'doc1'}) == 1
    assert evidence.add(source('doc2'), {'doc1', 'doc2'}) is None
    assert evidence.sources[0]['text'] == 'abcde'
    assert evidence.sources[0]['section_complete'] is False
    assert evidence.payload([1])['evidence_limit_reached'] is True


def test_scope_revocation_stops_original_disclosure(agent, monkeypatch):
    def revoke(kwargs):
        monkeypatch.setattr(agentic, 'published_document_ids', lambda kb: set())
        return response('Prova [Fonte 1].')
    agent.script.append(revoke)
    with pytest.raises(agentic.AgentError, match='cambiati'):
        run()
    assert not agent.wire.vaults


def test_revocation_during_initial_retrieval_prevents_provider_call(agent, monkeypatch):
    def revoke(*args, **kwargs):
        monkeypatch.setattr(agentic, 'published_document_ids', lambda kb: set())
        return [source()]
    monkeypatch.setattr(chat, 'retrieve_context', revoke)
    with pytest.raises(agentic.AgentError, match='cambiati'):
        run()
    assert not agent.wire.payloads and not agent.wire.vaults


def test_revoked_empty_knowledge_does_not_send_history(agent, monkeypatch):
    monkeypatch.setattr(chat, 'retrieve_context', lambda *args, **kwargs: [])
    monkeypatch.setattr(agentic, 'get_knowledge', lambda kb: None)
    with pytest.raises(agentic.AgentError, match='non è più disponibile'):
        run()
    assert not agent.wire.payloads


def test_catalog_and_document_filter_are_bound_to_authorized_kb(agent, monkeypatch):
    rows = [dict(document_id='doc1', filename='Regolamento_Mario_Rossi_2025.pdf', uploaded_at='2026-01-01'),
            dict(document_id='doc2', filename='Regolamento 2026.pdf'),
            dict(document_id='other', filename='Regolamento segreto.pdf')]
    requests = []
    def catalog(method, resource, params):
        requests.append(params)
        return rows
    monkeypatch.setattr(agentic, 'rest', catalog)
    monkeypatch.setattr(agentic, 'list_price_versions', lambda *args: [])
    agent.script.extend([response(calls=[call('find_document_versions', {'query': 'Regolamento'})]),
                         response(calls=[call('search_documents', {'query': 'requisiti', 'document_ref': 'D2'}, 'call_2')]),
                         response('Prova [Fonte 2].')])
    run()
    assert requests[0]['knowledge_id'] == f'eq.{KB}'
    assert agent.queries[-1][1]['document_ids'] == {'doc2'}
    assert 'segreto' not in str(agent.wire.payloads)
    assert 'Regolamento_Mario_Rossi' not in str(agent.wire.payloads)
    catalog_result = json.loads(agent.wire.payloads[1]['messages'][-1]['content'])
    assert catalog_result['documents'][0]['filename_year_hint'] == '2025'


def test_verified_price_result_remaps_citations_without_arithmetic(agent, monkeypatch):
    monkeypatch.setattr(agentic, 'query_price_lists', lambda query, kb, document_ids: {
        'answer': 'RISERVATO_Mario_Rossi.pdf — RISERVATO_Mario_Rossi: 12,50 EUR [1]', 'intent': 'lookup', 'rows_matched': 1,
        'sources': [{**source('doc2', 'Cella prezzo: 12,50 EUR'), 'verified_data': True,
                     'version_label': 'RISERVATO_Mario_Rossi', 'price_value': '12.50'}]})
    agent.script.extend([response(calls=[call('query_price_list', {'query': 'prezzo codice A.123'})]),
                         response('12,50 EUR [Fonte 2].')])
    result = run()
    tool = json.loads(agent.wire.payloads[1]['messages'][-1]['content'])
    assert tool['verified'] is True and tool['answer'].endswith('[Fonte 2]')
    assert result['sources'][1]['price_value'] == '12.50'
    assert 'RISERVATO_Mario_Rossi' not in str(agent.wire.payloads)


def test_no_verified_prices_does_not_invent_a_calculation(agent, monkeypatch):
    monkeypatch.setattr(agentic, 'query_price_lists', lambda *args, **kwargs: None)
    agent.script.extend([response(calls=[call('query_price_list', {'query': 'media prezzi'})]),
                         response('Dati insufficienti per il calcolo [Fonte 1].')])
    run()
    assert json.loads(agent.wire.payloads[1]['messages'][-1]['content'])['verified'] is False


def test_chat_routes_deepseek_to_agent_and_preserves_other_providers(agent, monkeypatch):
    monkeypatch.setattr(chat, 'published_document_ids', lambda kb: {'doc1'})
    monkeypatch.setattr(chat, 'query_price_lists', lambda *args, **kwargs: None)
    agent.script.append(response('Prova [Fonte 1].'))
    assert chat.chat('Domanda', knowledge_id=KB, provider='deepseek', model='deepseek-flash')['research']
    monkeypatch.setattr(chat, 'generate_response', lambda *args, **kwargs: 'Locale')
    assert 'research' not in chat.chat('Domanda', knowledge_id=KB, provider='ollama', model='local')


def test_direct_verified_queries_keep_deterministic_fast_path(agent, monkeypatch):
    monkeypatch.setattr(chat, 'published_document_ids', lambda kb: {'doc1'})
    monkeypatch.setattr(chat, 'query_price_lists', lambda *args, **kwargs: {
        'answer': '12,50 EUR [1]', 'sources': [source()], 'rows_matched': 1, 'intent': 'lookup'})
    result = chat.chat('Prezzo?', knowledge_id=KB, provider='deepseek', model='deepseek-flash')
    assert result['structured_intent'] == 'lookup' and not agent.wire.payloads
