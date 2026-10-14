"""Run with candidate backend and isolated GPU Anonymizer; synthetic data only.

Uses real DeepSeek tool calls and checks every outbound transcript before sending.
Retrieval is simulated, so no production database, index or user JWT is needed.
"""
from copy import deepcopy
import json
import time

import requests

from app.config import settings
from app.core import agentic, chat, privacy

KB = '00000000-0000-0000-0000-000000000001'
ORIGINALS = ['Mario Rossi', 'mario.rossi@example.it', 'RSSMRA80A01H501U', 'RISERVATO_Mario_Rossi.pdf']
ANCHOR = dict(document_id='synthetic-document', filename=ORIGINALS[3], score=.9,
              chunk_index=0, section_path=['Articolo 2'], section_refs=['section-2'],
              text='Articolo 2. Il referente è Mario Rossi, email mario.rossi@example.it, CF RSSMRA80A01H501U. '
                   'Questo frammento introduce la procedura dell’atto 123/2026 ma NON contiene termini o eccezioni: '
                   'occorre leggere la sezione completa con read_section.')
SECTION = {**ANCHOR, 'context_scope': 'section', 'section_complete': True,
           'text': ANCHOR['text'] + '\nLa scadenza ordinaria è 15 giorni. '
                   'Eccezione: in caso di integrazione documentale la scadenza è 30 giorni.'}

settings.agentic_rag_enabled = True
settings.agentic_max_steps = 3
settings.agentic_max_tool_calls = 6
settings.agentic_timeout_seconds = 120
settings.agentic_max_output_tokens = 12000
settings.agentic_reasoning_effort = 'low'
agentic.published_document_ids = lambda kb: {'synthetic-document'}
agentic.get_knowledge = lambda kb: {'id': KB}
chat.retrieve_context = lambda *args, **kwargs: [deepcopy(ANCHOR)]
agentic.get_client = lambda: None
agentic.get_collection_name = lambda kb: 'synthetic'
agentic.expand_hierarchical_contexts = lambda *args, **kwargs: [deepcopy(SECTION)]
agentic.list_price_versions = lambda *args, **kwargs: []
agentic.rest = lambda *args, **kwargs: [dict(document_id='synthetic-document', filename=ORIGINALS[3])]
agentic.query_price_lists = lambda *args, **kwargs: None

real_client = chat._get_deepseek_client()
sent = []


class CheckedClient:
    def with_options(self, **options):
        configured = real_client.with_options(**options)
        from types import SimpleNamespace
        def create(**kwargs):
            payload = json.dumps(kwargs['messages'], ensure_ascii=False)
            assert not any(original.casefold() in payload.casefold() for original in ORIGINALS), 'Original detected before model call'
            assert '123/2026' in payload
            sent.append(True)
            return configured.chat.completions.create(**kwargs)
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


chat._get_deepseek_client = lambda: CheckedClient()
created_maps = []
original_call = privacy.ProtectedRequest.call


def track(self, method, path, body=None):
    if path == '/v1/protect':
        created_maps.append(self.mapping_id)
    return original_call(self, method, path, body)


privacy.ProtectedRequest.call = track
started = time.perf_counter()
result = agentic.research(
    'Per Mario Rossi trova la scadenza ordinaria e l’eccezione. Leggi tutta la sezione '
    'prima di rispondere. Riporta nome, email, entrambi i termini e cita la fonte completa.',
    [], KB, top_k=4, score_threshold=.3, model=settings.deepseek_chat_model)
assert result['research']['tool_calls'] >= 1 and len(sent) >= 2, 'No real tool loop'
assert result['research']['stop_reason'] == 'completed', result['research']
assert 'Mario Rossi' in result['answer'] and 'mario.rossi@example.it' in result['answer']
assert '15' in result['answer'] and '30' in result['answer']
assert '[Fonte 2]' in result['answer'] and not privacy.TOKEN_RE.search(result['answer'])
assert result['sources'][1]['section_complete'] is True
assert len(created_maps) == 1
headers = {'X-Anonymizer-Token': settings.anonymizer_token}
missing = requests.post(settings.anonymizer_url + '/v1/restore', headers=headers,
                        json={'mapping_id': created_maps[0], 'text': 'test', 'allowed_tokens': []}, timeout=5)
assert missing.status_code == 404, 'Temporary map was not deleted'
health = requests.get(settings.anonymizer_url + '/health', timeout=5).json()
assert health['device'] == 'cuda' and health['recognizers_complete']
print(json.dumps({'real_tool_loop': True, 'outgoing_originals_blocked': True,
                  'restored_answer': True, 'section_citation': True, 'temporary_map_deleted': True,
                  'reasoning_effort': settings.agentic_reasoning_effort, **result['research'],
                  'seconds': round(time.perf_counter() - started, 3), 'gpu_health': health}, indent=2))
