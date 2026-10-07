"""Authorization and accounting regressions; no calls to live services."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
from contextlib import contextmanager
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from app import auth
from app.auth import User, request_user
from app.core import supabase, admin, usage
from app.config import settings

@pytest.fixture
def client(monkeypatch):
    user=User(str(uuid4()),'test-token',True,issued_at=int(datetime.now(timezone.utc).timestamp()))
    state={'profile':{'id':user.id,'email':'test@example.test','active':True,'role':'admin','must_change_password':False,'session_valid_after':'1970-01-01T00:00:00+00:00'}, 'calls':[]}
    monkeypatch.setattr(auth,'verify_token',lambda token:user)
    def rest(method,resource,**kwargs):
        state['calls'].append((method,resource,kwargs))
        if resource=='app_profiles': return [state['profile']]
        if resource=='rpc/chatbot_kb_access': return False
        if resource=='app_models': return [{'key':'ollama:allowed','provider':'ollama','model_id':'allowed','enabled':True}]
        return []
    monkeypatch.setattr(supabase,'rest',rest)
    monkeypatch.setattr('app.api.admin.rest',rest)
    with TestClient(app,headers={'Authorization':'Bearer test-token'}) as test_client:
        yield test_client,state

@pytest.mark.parametrize('role',['user','manager'])
@pytest.mark.parametrize('path',['/api/admin/users','/api/admin/knowledge','/api/admin/models','/api/admin/usage','/api/admin/audit'])
def test_live_role_overrules_admin_jwt(client,role,path):
    test_client,state=client;state['profile']['role']=role
    assert test_client.get(path).status_code==403

def test_suspended_account_and_revoked_session(client):
    test_client,state=client
    state['profile']['active']=False
    assert test_client.get('/api/knowledge').status_code==403
    state['profile']['active']=True;state['profile']['session_valid_after']='2099-01-01T00:00:00+00:00'
    assert test_client.get('/api/account/me').status_code==401

def test_forced_password_blocks_chat_and_admin_but_allows_profile(client):
    test_client,state=client;state['profile']['must_change_password']=True
    assert test_client.get('/api/account/me').status_code==200
    assert test_client.get('/api/admin/users').status_code==403
    assert test_client.post('/api/chat',json={'question':'test','knowledge_id':str(uuid4())}).status_code==403

def test_missing_service_credential_fails_closed(monkeypatch):
    monkeypatch.setattr(settings,'supabase_admin_key','')
    with pytest.raises(HTTPException) as exc: admin.privileged('POST','/auth/v1/admin/users',body={})
    assert exc.value.status_code==503

def test_forbidden_model_never_calls_provider_or_reserves(client,monkeypatch):
    from app.api import chat
    from app.core import knowledge
    test_client,state=client
    monkeypatch.setattr(knowledge,'get_knowledge',lambda value:object())
    monkeypatch.setattr(chat,'rag_chat',lambda *args,**kwargs:pytest.fail('forbidden provider called'))
    monkeypatch.setattr(admin,'privileged',lambda *args,**kwargs:pytest.fail('forbidden request reserved'))
    response=test_client.post('/api/chat',json={'question':'test','knowledge_id':str(uuid4()),'model_key':'ollama:forbidden'})
    assert response.status_code==403

def test_quota_denial_precedes_embedding_and_generation(client,monkeypatch):
    from app.api import chat
    from app.core import knowledge
    test_client,state=client
    monkeypatch.setattr(knowledge,'get_knowledge',lambda value:object())
    monkeypatch.setattr(chat,'rag_chat',lambda *args,**kwargs:pytest.fail('provider called past quota'))
    def quota(*args,**kwargs): raise HTTPException(429,'quota')
    monkeypatch.setattr(admin,'privileged',quota)
    assert test_client.post('/api/chat',json={'question':'test','knowledge_id':str(uuid4()),'model_key':'ollama:allowed'}).status_code==429

def test_usage_snapshots_tariff_and_preserves_unknowns(monkeypatch):
    marker=request_user.set(User(str(uuid4()),'test',False));captured=[]
    def privileged(method,path,**kwargs):
        if method=='GET': return [{'input_per_million':2,'output_per_million':4,'currency':'USD'}]
        captured.append(kwargs['body'])
    monkeypatch.setattr(usage,'privileged',privileged)
    try:
        usage.record('openai','test','chat','success',5,100,50)
        usage.record('openai','test','chat','success',5,None,None)
    finally: request_user.reset(marker)
    assert captured[0]['estimated_cost']==pytest.approx(.0004)
    assert captured[0]['input_rate']==2
    assert captured[1]['estimated_cost'] is None
    assert captured[1]['input_tokens'] is None

def test_provider_failure_records_error_not_prompt(monkeypatch):
    events=[];monkeypatch.setattr(usage,'record',lambda *args,**kwargs:events.append((args,kwargs)))
    with pytest.raises(RuntimeError):
        with usage.measure('ollama','test','chat'): raise RuntimeError('private prompt')
    assert events[0][0][3]=='error'
    assert events[0][1]['error_code']=='RuntimeError'
    assert 'private prompt' not in str(events)

def test_admin_passwords_are_never_returned(client,monkeypatch):
    test_client,state=client;calls=[]
    def privileged(method,path,**kwargs):
        calls.append((method,path,kwargs))
        if method=='POST': return {'id':state['profile']['id']}
        if method=='GET': return [state['profile']]
        return {}
    monkeypatch.setattr('app.api.admin.privileged',privileged)
    monkeypatch.setattr('app.api.admin.audit',lambda *args:None)
    monkeypatch.setattr('app.api.admin.user_profile',lambda user_id:state['profile'])
    response=test_client.post('/api/admin/users',json={'email':'new@test.it','password':'temporary-password-123','display_name':'New'})
    assert response.status_code==201
    assert 'temporary-password' not in response.text
    assert calls[0][2]['body']['ban_duration']=='876000h'

def test_personal_usage_remains_rls_scoped(client):
    test_client,state=client;state['profile']['role']='user'
    response=test_client.get('/api/account/usage')
    assert response.status_code==200
    assert response.json()['total_events']==0

def test_password_policy_validated(client):
    test_client,state=client
    assert test_client.post('/api/admin/users',json={'email':'bad','password':'short'}).status_code==422
