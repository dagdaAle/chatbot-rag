import json
from copy import deepcopy

import httpx
import pytest
from fastapi.testclient import TestClient

from gateway.main import Settings, create_app


class Services:
    def __init__(self):
        self.calls=[]
        self.maps={}
        self.provider_payloads=[]
        self.protect_failure=False
        self.incomplete=False
        self.restore_failure=False
        self.delete_failure=False
        self.provider_status=200
        self.answer=None
        self.recognized=['Mario Rossi', 'mario@example.it', 'Via "Roma" 4']

    def handle(self, request):
        self.calls.append((request.method,request.url.host,request.url.path))
        data=json.loads(request.content) if request.content else {}
        if request.url.host=='anonymizer':
            assert request.headers['x-anonymizer-token']=='anon-secret'
            assert 'authorization' not in request.headers
            if request.url.path in ('/v1/protect','/v1/protect/extend'):
                if self.protect_failure:return httpx.Response(503,json={'detail':'sensitive upstream body'})
                mid=data['mapping_id']
                if request.url.path=='/v1/protect':
                    assert mid not in self.maps
                    self.maps[mid]={}
                else:assert mid in self.maps
                mapping=self.maps[mid]
                texts=[]
                for text in data['texts']:
                    for original in self.recognized:
                        if original in text:
                            token=next((t for t,v in mapping.items() if v==original),None)
                            if token is None:
                                token=f'<PII_{mid.replace("-", "")}_PERSONA_{len(mapping)+1}>'
                                mapping[token]=original
                            text=text.replace(original,token)
                    texts.append(text)
                tokens=[t for t in mapping if any(t in text for text in texts)]
                return httpx.Response(200,json={'protocol_version':1,'mapping_id':mid,'recognizers_complete':not self.incomplete,'texts':texts,'tokens':tokens})
            if request.url.path=='/v1/restore':
                if self.restore_failure:return httpx.Response(503,json={'secret':'not-for-client'})
                text=data['text']; replaced=0
                for token,original in self.maps[data['mapping_id']].items():
                    assert token in data['allowed_tokens']
                    replaced+=text.count(token);text=text.replace(token,original)
                return httpx.Response(200,json={'protocol_version':1,'mapping_id':data['mapping_id'],'text':text,'replaced':replaced})
            if request.method=='DELETE':
                self.maps.pop(request.url.path.rsplit('/',1)[1],None)
                return httpx.Response(503 if self.delete_failure else 200,json={'deleted':True})
        assert request.url.host=='api.deepseek.com'
        assert request.url.path=='/chat/completions'
        assert request.headers['authorization']=='Bearer provider-secret'
        assert 'x-anonymizer-token' not in request.headers
        self.provider_payloads.append(data)
        assert data['stream'] is False
        if self.provider_status!=200:
            return httpx.Response(self.provider_status,json={'error':'secret provider failure Mario Rossi'})
        if self.answer is not None:
            answer=self.answer(data)
        else:
            answer={'role':'assistant','content':data['messages'][-1]['content']}
        return httpx.Response(200,json={'choices':[{'message':answer,'finish_reason':'tool_calls' if answer.get('tool_calls') else 'stop'}],
                                       'usage':{'prompt_tokens':42,'completion_tokens':10,'total_tokens':52}})


@pytest.fixture
def setup():
    services=Services()
    settings=Settings('gateway-secret','anon-secret','provider-secret')
    with TestClient(create_app(settings,httpx.MockTransport(services.handle))) as client:
        yield client,services


def post(client,body=None):
    return client.post('/v1/chat/completions',json=body or {'model':'deepseek-flash','messages':[{'role':'user','content':'Mario Rossi mario@example.it'}]},
                       headers={'Authorization':'Bearer gateway-secret'})


def test_auth_and_model_list(setup):
    client,s=setup
    assert client.get('/v1/models').status_code==401
    assert client.get('/v1/models',headers={'Authorization':'Bearer gateway-secret'}).json()['data'][0]['id']=='deepseek-flash'
    assert client.post('/v1/chat/completions',json={}).status_code==401
    assert not s.provider_payloads


def test_text_protected_and_response_restored_and_map_deleted(setup):
    client,s=setup
    response=post(client)
    assert response.status_code==200,response.text
    assert response.json()['choices'][0]['message']['content']=='Mario Rossi mario@example.it'
    wire=json.dumps(s.provider_payloads)
    assert 'Mario Rossi' not in wire and 'mario@example.it' not in wire
    assert 'PII_' in wire
    assert not s.maps
    assert response.json()['usage']['total_tokens']==52


@pytest.mark.parametrize('failure',['protect_failure','incomplete'])
def test_no_upstream_when_protection_unavailable(setup,failure):
    client,s=setup;setattr(s,failure,True)
    response=post(client)
    assert response.status_code==503
    assert not s.provider_payloads and not s.maps
    assert 'sensitive' not in response.text


def test_restore_failure_returns_no_partial_output(setup):
    client,s=setup;s.restore_failure=True
    response=post(client,{'model':'deepseek-flash','stream':True,'messages':[{'role':'user','content':'Mario Rossi'}]})
    assert response.status_code==503
    assert 'Mario' not in response.text and 'PII_' not in response.text
    assert not s.maps


def test_stream_compatible_without_partial_placeholders(setup):
    client,s=setup
    response=post(client,{'model':'deepseek-flash','stream':True,'messages':[{'role':'user','content':'Mario Rossi'}]})
    assert response.status_code==200
    assert response.headers['content-type'].startswith('text/event-stream')
    events=[line[6:] for line in response.text.splitlines() if line.startswith('data: ')]
    assert events[-1]=='[DONE]'
    assert json.loads(events[0])['choices'][0]['delta']['content']=='Mario Rossi'
    assert json.loads(events[-2])['usage']['prompt_tokens']==42
    assert 'PII_' not in response.text and not s.maps


def test_tool_arguments_quotes_and_reasoning_restored(setup):
    client,s=setup
    tool={'type':'function','function':{'name':'search_documents','description':'Trova Mario Rossi',
                                      'parameters':{'type':'object','properties':{'query':{'type':'string','description':'Mario Rossi'}}}}}
    def answer(data):
        token=next(t for m in s.maps.values() for t,v in m.items() if v=='Via "Roma" 4')
        return {'role':'assistant','content':None,'reasoning_content':token,
                'tool_calls':[{'id':'call_abc','type':'function','function':{'name':'search_documents','arguments':json.dumps({'query':token})}}]}
    s.answer=answer
    response=post(client,{'model':'deepseek-flash','messages':[{'role':'user','content':'Via "Roma" 4 Mario Rossi'}],'tools':[tool],'stream':True})
    assert response.status_code==200,response.text
    event=json.loads(response.text.splitlines()[0][6:])['choices'][0]['delta']
    assert event['reasoning_content']=='Via "Roma" 4'
    assert json.loads(event['tool_calls'][0]['function']['arguments'])['query']=='Via "Roma" 4'
    assert event['tool_calls'][0]['index']==0
    assert 'Mario Rossi' not in json.dumps(s.provider_payloads)
    assert 'Roma' not in json.dumps(s.provider_payloads)


def test_every_call_in_agent_loop_is_reprotected(setup):
    client,s=setup
    tool={'type':'function','function':{'name':'search','parameters':{'type':'object'}}}
    for i in range(2):
        body={'model':'deepseek-flash','tools':[tool],'messages':[
            {'role':'user','content':'Mario Rossi'},
            {'role':'assistant','content':None,'reasoning_content':'Mario Rossi',
             'tool_calls':[{'id':'call_a','type':'function','function':{'name':'search','arguments':json.dumps({'query':'Mario Rossi'})}}]},
            {'role':'tool','tool_call_id':'call_a','content':'mario@example.it Mario Rossi'}]}
        assert post(client,body).status_code==200
    mids=[path for method,host,path in s.calls if path=='/v1/protect']
    assert len(mids)==2 and len(s.provider_payloads)==2 and not s.maps
    assert 'Mario Rossi' not in json.dumps(s.provider_payloads)
    assert 'mario@example.it' not in json.dumps(s.provider_payloads)


@pytest.mark.parametrize('change',[
    {'model':'unknown'}, {'metadata':{'name':'Mario Rossi'}}, {'extra_body':{'name':'Mario Rossi'}},
    {'messages':[{'role':'user','content':[{'type':'image_url','image_url':{'url':'https://secret.example'}}]}]},
    {'messages':[{'role':'user','content':'hi','unknown':'Mario Rossi'}]},
    {'messages':[{'role':'user','content':[{'type':'input_audio','input_audio':{'data':'abc'}}]}]},
    {'stream':'true'}, {'n':2}, {'thinking':{'anything':'Mario Rossi'}},
    {'tools':[{'type':'web_search'}]}, {'tool_choice':{'type':'function','function':{'name':'missing'}}},
])
def test_unsupported_payload_fails_before_any_egress(setup,change):
    client,s=setup
    body={'model':'deepseek-flash','messages':[{'role':'user','content':'Mario Rossi'}]};body.update(change)
    response=post(client,body)
    assert response.status_code in (400,413),response.text
    assert not s.provider_payloads and not s.maps


def test_identity_not_forwarded(setup):
    client,s=setup
    assert post(client,{'model':'deepseek-flash','user':'mario@example.it','messages':[{'role':'user','content':'ciao'}]}).status_code==200
    assert 'user' not in s.provider_payloads[0]


@pytest.mark.parametrize('status',[301,401,429,500])
def test_provider_errors_sanitized_no_redirect(setup,status):
    client,s=setup;s.provider_status=status
    response=post(client)
    assert response.status_code==502
    assert 'Mario' not in response.text and 'secret' not in response.text and not s.maps
    assert len(s.provider_payloads)==1


@pytest.mark.parametrize('content',['<PII_'+'a'*32+'_PERSONA_1>','<PII_...>','PII_broken'])
def test_foreign_and_malformed_tokens_rejected(setup,content):
    client,s=setup
    s.answer=lambda data:{'content':content}
    assert post(client).status_code==502
    assert not s.maps


def test_large_request_rejected(setup):
    client,s=setup
    response=post(client,{'model':'deepseek-flash','messages':[{'role':'user','content':'a'*180001}]})
    assert response.status_code==413 and not s.provider_payloads


def test_many_tool_fields_use_extension(setup):
    client,s=setup
    tools=[{'type':'function','function':{'name':f'tool_{i}','description':'Mario Rossi',
             'parameters':{'type':'object','properties':{'x':{'type':'string','description':'mario@example.it'}}}}} for i in range(25)]
    assert post(client,{'model':'deepseek-flash','tools':tools,'messages':[{'role':'user','content':'Mario Rossi'}]}).status_code==200
    assert any(path=='/v1/protect/extend' for _,_,path in s.calls)
    assert 'Mario Rossi' not in json.dumps(s.provider_payloads)


def test_no_raw_proxy_routes(setup):
    client,s=setup
    for route in ['/v1/embeddings','/v1/responses','/v1/audio/transcriptions','/v1/images/generations','/anything']:
        assert client.post(route,headers={'Authorization':'Bearer gateway-secret'},json={}).status_code==404
    assert not s.provider_payloads


def test_unissued_tool_name_rejected(setup):
    client,s=setup
    s.answer=lambda data:{'content':None,'tool_calls':[{'id':'call_a','type':'function','function':{'name':'run_shell','arguments':'{}'}}]}
    assert post(client).status_code==502 and not s.maps


def test_personal_data_in_schema_keys_never_egresses(setup):
    client,s=setup
    tools=[{'type':'function','function':{'name':'search','parameters':{'type':'object','properties':{'mario@example.it':{'type':'string'}}}}}]
    response=post(client,{'model':'deepseek-flash','tools':tools,'messages':[{'role':'user','content':'ciao'}]})
    assert response.status_code==400 and not s.provider_payloads and not s.maps


def test_builtin_ask_user_false_positive_preserves_protocol_and_protects_text(setup):
    client,s=setup
    s.recognized.append('ask_user')
    tool={'type':'function','function':{'name':'ask_user','description':'Use ask_user for questions',
          'parameters':{'type':'object','properties':{'question':{'type':'string'}}}}}
    body={'model':'deepseek-flash','tools':[tool],
          'tool_choice':{'type':'function','function':{'name':'ask_user'}},
          'messages':[{'role':'assistant','content':None,'tool_calls':[{'id':'call_a','type':'function',
                       'function':{'name':'ask_user','arguments':json.dumps({'question':'Mario Rossi ask_user'})}}]},
                      {'role':'tool','tool_call_id':'call_a','content':'Mario Rossi ask_user'},
                      {'role':'user','content':'ciao ask_user'}]}
    response=post(client,body)
    assert response.status_code==200,response.text
    payload=s.provider_payloads[0]
    assert payload['tools'][0]['function']['name']=='ask_user'
    assert payload['messages'][1]['tool_calls'][0]['function']['name']=='ask_user'
    assert payload['tool_choice']['function']['name']=='ask_user'
    assert 'ask_user' not in payload['tools'][0]['function']['description']
    assert 'ask_user' not in payload['messages'][-1]['content']
    assert 'Mario Rossi' not in payload['messages'][1]['tool_calls'][0]['function']['arguments']
    assert response.json()['choices'][0]['message']['content']=='ciao ask_user'
    assert not s.maps


def test_public_tool_name_exemption_does_not_cover_json_keys(setup):
    client,s=setup
    s.recognized.append('ask_user')
    tool={'type':'function','function':{'name':'ask_user','parameters':{
          'type':'object','properties':{'ask_user':{'type':'string'}}}}}
    response=post(client,{'model':'deepseek-flash','tools':[tool],
                         'messages':[{'role':'user','content':'ciao'}]})
    assert response.status_code==400 and not s.provider_payloads and not s.maps


def test_invented_token_in_tool_argument_key_rejected(setup):
    client,s=setup
    tool={'type':'function','function':{'name':'search','parameters':{'type':'object'}}}
    s.answer=lambda data:{'content':None,'tool_calls':[{'id':'call_a','type':'function','function':{'name':'search','arguments':json.dumps({'<PII_...>':'value'})}}]}
    response=post(client,{'model':'deepseek-flash','tools':[tool],'messages':[{'role':'user','content':'ciao'}]})
    assert response.status_code==502 and not s.maps


@pytest.mark.parametrize('key',['location','rrule'])
def test_public_calendar_schema_keys_are_stable_but_values_protected(setup,key):
    client,s=setup
    s.recognized.append(key)
    tool={'type':'function','function':{'name':'calendar_tool','parameters':{
          'type':'object','properties':{key:{'type':'string'}},'required':[key]}}}
    # Required references stay consistent with keys; values still get protected.
    body={'model':'deepseek-flash','tools':[tool],'messages':[
          {'role':'assistant','tool_calls':[{'id':'call_a','type':'function','function':{
           'name':'calendar_tool','arguments':json.dumps({key:'Mario Rossi '+key})}}]},
          {'role':'tool','tool_call_id':'call_a','content':'ciao'},
          {'role':'user','content':'Mario Rossi '+key}]}
    response=post(client,body)
    assert response.status_code==200,response.text
    payload=s.provider_payloads[0]
    assert key in payload['tools'][0]['function']['parameters']['properties']
    assert payload['tools'][0]['function']['parameters']['required']==[key]
    protected=json.loads(payload['messages'][1]['tool_calls'][0]['function']['arguments'])
    assert key in protected and key not in protected[key] and 'Mario Rossi' not in protected[key]
    assert key not in payload['messages'][-1]['content']
    assert not s.maps
