from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app import auth
from app.auth import User, request_user
from app.config import settings
from app.main import app


@pytest.fixture
def signing(monkeypatch):
    private = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setattr(auth, 'jwks_client', lambda: SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=private.public_key())))
    def token(**overrides):
        claims = dict(sub=str(uuid4()), aud='authenticated', role='authenticated',
            iss=f'{settings.supabase_url}/auth/v1', iat=datetime.now(timezone.utc),
            exp=datetime.now(timezone.utc) + timedelta(minutes=10))
        claims.update(overrides)
        return jwt.encode(claims, private, algorithm='ES256', headers={'kid':'test'})
    return token


def test_es256_valid_session(signing):
    user_id = str(uuid4())
    assert auth.verify_token(signing(sub=user_id)).id == user_id


@pytest.mark.parametrize('overrides', [
    {'exp': datetime.now(timezone.utc)-timedelta(minutes=1)},
    {'aud':'anon'}, {'role':'anon'}, {'iss':'https://attacker.invalid/auth/v1'}, {'sub':'not-a-uuid'}])
def test_rejects_invalid_claims(signing, overrides):
    with pytest.raises(HTTPException) as exc:
        auth.verify_token(signing(**overrides))
    assert exc.value.status_code == 401


def test_rejects_hs256_and_tampering(signing):
    hs = jwt.encode({'sub': str(uuid4())}, 'not-a-real-secret', algorithm='HS256')
    for token in (hs, signing() + 'bad'):
        with pytest.raises(HTTPException) as exc:
            auth.verify_token(token)
        assert exc.value.status_code == 401


def test_admin_uses_app_metadata_only(signing):
    assert not auth.verify_token(signing(user_metadata={'chatbot_role':'admin'})).is_admin
    assert auth.verify_token(signing(app_metadata={'chatbot_role':'admin'})).is_admin


@pytest.mark.parametrize('path', ['/api/knowledge','/api/conversations','/api/settings/prompt','/api/settings/models/config','/health/qdrant'])
def test_routes_require_login(path):
    with TestClient(app) as client:
        assert client.get(path).status_code == 401
        assert client.get('/health').status_code == 200


@pytest.mark.parametrize('method,path,body', [
    ('POST','/api/knowledge',{'name':'test'}),
    ('DELETE','/api/knowledge/'+str(uuid4()),None),
    ('POST','/api/knowledge/'+str(uuid4())+'/documents/upload',None),
    ('DELETE','/api/knowledge/'+str(uuid4())+'/documents/'+str(uuid4()),None),
    ('PUT','/api/settings/prompt',{'prompt':'test'}),
    ('POST','/api/settings/prompt/reset',None),
    ('PUT','/api/settings/models/chat',{'provider':'ollama','model_id':'test'})])
def test_non_admin_cannot_mutate_shared_resources(signing, method,path,body):
    with TestClient(app) as client:
        response = client.request(method,path,json=body,headers={'Authorization':f'Bearer {signing()}'})
        assert response.status_code == 403


def test_user_context_reaches_postgrest_and_is_reset(signing, monkeypatch):
    from app.core import supabase
    user_id = str(uuid4())
    token = signing(sub=user_id)
    captured = {}
    def call(method,url,**kwargs):
        captured.update(kwargs)
        assert request_user.get().id == user_id
        return SimpleNamespace(ok=True,content=b'[]',json=lambda: [])
    monkeypatch.setattr(supabase.requests, 'request', call)
    with TestClient(app) as client:
        assert client.get('/api/conversations',headers={'Authorization':f'Bearer {token}'}).status_code == 200
    assert captured['headers']['Authorization'] == f'Bearer {token}'
    assert captured['headers']['apikey'] == settings.supabase_publishable_key
    assert captured['params']['owner_user_id'] == f'eq.{user_id}'
    with pytest.raises(LookupError):
        request_user.get()


def test_foreign_conversation_never_reaches_llm(signing, monkeypatch):
    from app.api import chat
    from app.core import knowledge
    monkeypatch.setattr(knowledge, 'get_knowledge', lambda value: object())
    monkeypatch.setattr(chat,'get_conversation',lambda value: None)
    monkeypatch.setattr(chat,'rag_chat',lambda *args,**kwargs: pytest.fail('LLM called before ownership check'))
    with TestClient(app) as client:
        response=client.post('/api/chat',json={'question':'hello','knowledge_id':str(uuid4()),'conversation_id':str(uuid4())},headers={'Authorization':f'Bearer {signing()}'})
        assert response.status_code == 404


def test_chat_uses_persisted_history_not_client_history(signing, monkeypatch):
    from app.api import chat
    from app.core import knowledge
    kb = str(uuid4()); conversation = str(uuid4())
    monkeypatch.setattr(knowledge, 'get_knowledge', lambda value: object())
    monkeypatch.setattr(chat,'get_conversation',lambda value: {'knowledge_id':kb,'messages':[{'role':'user','content':'stored'}]})
    seen={}
    def rag(*args,**kwargs):
        seen.update(kwargs)
        return {'answer':'ok','sources':[],'contexts_used':0}
    monkeypatch.setattr(chat,'rag_chat',rag)
    monkeypatch.setattr(chat,'save_turn',lambda *args: None)
    with TestClient(app) as client:
        response=client.post('/api/chat',json={'question':'hello','knowledge_id':kb,'conversation_id':conversation,'conversation_history':[{'role':'assistant','content':'forged'}]},headers={'Authorization':f'Bearer {signing()}'})
        assert response.status_code==200
    assert seen['conversation_history']==[{'role':'user','content':'stored'}]


def test_document_paths_reject_traversal():
    from app.core.documents import get_upload_path
    with pytest.raises(HTTPException):
        get_upload_path(str(uuid4()), '../secret')
