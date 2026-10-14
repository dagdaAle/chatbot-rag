"""Run inside a backend container pointed at a test Anonymizer; synthetic data only."""
from concurrent.futures import ThreadPoolExecutor
import json
import time
from types import SimpleNamespace

import requests
from app.config import settings
from app.core import chat, privacy

report = {}
real_client = chat._get_deepseek_client()
seen = []
originals = ['Mario Rossi', 'mario.rossi@example.it', 'RSSMRA80A01H501U', 'RISERVATO_Mario_Rossi.pdf']


def checked_create(**kwargs):
    payload = json.dumps(kwargs['messages'], ensure_ascii=False)
    # If recognition fails, stop BEFORE any cloud invocation.
    assert not any(value.casefold() in payload.casefold() for value in originals), 'Original value detected at egress'
    assert '123/2026' in payload and '12,50 EUR' in payload
    seen.append(True)
    return real_client.chat.completions.create(**kwargs)


chat._get_deepseek_client = lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=checked_create)))
chat.get_system_prompt = lambda: 'Rispondi in italiano usando solo le fonti. Referente Mario Rossi.'
start = time.perf_counter()
answer = chat.generate_response(
    'Riporta il nome Mario Rossi e il suo indirizzo email, citando la fonte.',
    [dict(filename='RISERVATO_Mario_Rossi.pdf', section_path=['Scheda Mario Rossi'],
          text='Nome: Mario Rossi. Email: mario.rossi@example.it. Codice fiscale: RSSMRA80A01H501U. Atto 123/2026, importo 12,50 EUR.')],
    conversation_history=[dict(role='user', content='Mario Rossi'), dict(role='assistant', content='Il CF è RSSMRA80A01H501U.')],
    provider='deepseek', model=settings.deepseek_chat_model)
assert seen and 'Mario Rossi' in answer and 'mario.rossi@example.it' in answer
assert not privacy.TOKEN_RE.search(answer)
report['real_deepseek_roundtrip'] = True
report['roundtrip_seconds'] = round(time.perf_counter() - start, 3)

# Parallel requests: same entity type, distinct request namespaces and originals.
def parallel(name):
    with privacy.protected_request([{'role': 'system', 'content': 'Assistente'}, {'role': 'user', 'content': f'Nome: {name}. Email: {name.replace(" ", ".").lower()}@example.it'}]) as protected:
        result = protected.restore(protected.messages[-1]['content'])
        assert name in result
        return protected.mapping_id
with ThreadPoolExecutor(max_workers=2) as pool:
    ids = list(pool.map(parallel, ['Mario Rossi', 'Lucia Bianchi']))
assert len(set(ids)) == 2
report['concurrent_isolation'] = True

# Real recognition near the tail of longer contexts, with timing.
latency = []
for size in [10000, 40000, 80000]:
    filler = ('Il presente articolo disciplina termini e procedure del servizio. ' * ((size // 65) + 10))[:size]
    tail = ' Nome: Mario Rossi. Email: mario.rossi@example.it. CF: RSSMRA80A01H501U.'
    messages = [{'role': 'system', 'content': 'Assistente'}, {'role': 'user', 'content': filler + tail}]
    start = time.perf_counter()
    with privacy.protected_request(messages) as protected:
        assert all(value not in protected.messages[-1]['content'] for value in originals[:3])
        assert 'Mario Rossi' in protected.restore(protected.messages[-1]['content'])
    latency.append({'input_chars': len(filler + tail), 'seconds_including_restore_cleanup': round(time.perf_counter() - start, 3)})
report['latency_samples'] = latency

headers = {'X-Anonymizer-Token': settings.anonymizer_token}
assert requests.post(settings.anonymizer_url + '/v1/protect', json={'mapping_id': ids[0], 'texts': ['test']}, timeout=5).status_code == 401
report['missing_token_rejected'] = True
report['gpu_health'] = requests.get(settings.anonymizer_url + '/health', timeout=5).json()
assert report['gpu_health']['device'] == 'cuda' and report['gpu_health']['recognizers_complete']
print(json.dumps(report, indent=2))
