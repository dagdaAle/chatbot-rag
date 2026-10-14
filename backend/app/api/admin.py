from datetime import datetime, timedelta, timezone
from collections import defaultdict
import csv
import io
from typing import Literal
from uuid import UUID
import requests
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, SecretStr
from app.auth import require_admin, request_user
from app.config import settings
from app.core.supabase import rest, identifier
from app.core.admin import privileged, audit, user_profile

router = APIRouter(prefix='/api/admin', dependencies=[Depends(require_admin)], tags=['admin'])
account_router = APIRouter(prefix='/api/account', tags=['account'])

class ProfileUpdate(BaseModel):
    display_name: str = Field(default='', max_length=200)
    role: Literal['admin','member','viewer']
    active: bool
    monthly_requests: int | None = Field(default=None, gt=0)
    requests_per_minute: int = Field(default=20, ge=1, le=600)
    concurrent_requests: int = Field(default=2, ge=1, le=20)

class CreateUser(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    password: SecretStr = Field(min_length=12, max_length=128)
    display_name: str = Field(default='', max_length=200)
    role: Literal['admin','member','viewer'] = 'member'

class PasswordChange(BaseModel):
    current_password: SecretStr = Field(min_length=1, max_length=128)
    password: SecretStr = Field(min_length=12, max_length=128)

class PasswordReset(BaseModel):
    password: SecretStr = Field(min_length=12, max_length=128)

class EmailChange(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')

class Member(BaseModel):
    user_id: UUID

class ModelUpdate(BaseModel):
    provider: Literal['openai','deepseek','ollama']
    kind: Literal['chat','embedding'] = 'chat'
    model_id: str = Field(min_length=1, max_length=200, pattern=r'^[a-zA-Z0-9._:/-]+$')
    name: str = Field(min_length=1, max_length=200)
    enabled: bool = True
    shared: bool = True
    input_per_million: float | None = Field(default=None, ge=0)
    output_per_million: float | None = Field(default=None, ge=0)
    currency: Literal['USD','EUR'] = 'USD'
    members: list[Member] = Field(default_factory=list, max_length=1000)

@account_router.get('/me')
def me():
    return rest('GET', 'app_profiles', params={'id': f'eq.{request_user.get().id}'})[0]

@account_router.put('/password')
def change_password(body: PasswordChange):
    profile = user_profile(request_user.get().id)
    # Reauthenticate before changing a password; never return this session to the browser.
    try:
        response = requests.post(settings.supabase_url.rstrip('/')+'/auth/v1/token?grant_type=password',
            headers={'apikey': settings.supabase_publishable_key}, json={'email':profile['email'],'password':body.current_password.get_secret_value()}, timeout=20)
        if not response.ok:
            raise HTTPException(400,'Password attuale non corretta')
        access_token = response.json()['access_token']
        updated = requests.put(settings.supabase_url.rstrip('/')+'/auth/v1/user',
            headers={'apikey':settings.supabase_publishable_key,'Authorization':f'Bearer {access_token}'},
            json={'password':body.password.get_secret_value()},timeout=20)
        if not updated.ok:
            raise HTTPException(400,'Password non accettata dal servizio di autenticazione')
    except requests.RequestException as exc:
        raise HTTPException(503,'Autenticazione non raggiungibile') from exc
    privileged('PATCH','/rest/v1/app_profiles',params={'id':f'eq.{profile["id"]}'},body={'must_change_password':False})
    audit('password_changed',profile['id'])
    return {'success':True}

@router.get('/users')
def users():
    return rest('GET','app_profiles',params={'order':'created_at.desc'})

@router.post('/users',status_code=201)
def create_user(body: CreateUser):
    # Create blocked first; setup failure never leaves an enabled unconfigured account.
    created = privileged('POST','/auth/v1/admin/users',body={'email':body.email,'password':body.password.get_secret_value(),'email_confirm':True,'ban_duration':'876000h'})
    user_id = created['id']
    try:
        privileged('PATCH','/rest/v1/app_profiles',params={'id':f'eq.{user_id}'},body={'display_name':body.display_name,'role':body.role,'must_change_password':True})
        privileged('PUT',f'/auth/v1/admin/users/{user_id}',body={'ban_duration':'none'})
    except HTTPException:
        # Compensate: never leave a half-configured (banned, unusable) account behind.
        try:
            privileged('DELETE',f'/auth/v1/admin/users/{user_id}')
        except HTTPException:
            pass
        raise
    audit('user_created',user_id,{'role':body.role})
    return user_profile(user_id)

@router.put('/users/{user_id}')
def update_user(user_id: UUID, body: ProfileUpdate):
    rest('POST','rpc/chatbot_admin_save',body={'kind':'profile','target':str(user_id),'payload':body.model_dump()})
    return {'success':True}

@router.put('/users/{user_id}/email')
def change_email(user_id: UUID, body: EmailChange):
    user_profile(str(user_id))
    privileged('PUT',f'/auth/v1/admin/users/{user_id}',body={'email':body.email,'email_confirm':True})
    audit('email_changed',str(user_id),{'email':body.email})
    return {'success':True}

@router.put('/users/{user_id}/password')
def reset_password(user_id: UUID, body: PasswordReset):
    user_profile(str(user_id))
    # Set the new password first: if it fails nothing changed. Then flag + revoke sessions
    # atomically (audited inside the RPC). The reverse order could lock the user out.
    privileged('PUT',f'/auth/v1/admin/users/{user_id}',body={'password':body.password.get_secret_value()})
    rest('POST','rpc/chatbot_admin_save',body={'kind':'force_password','target':str(user_id),'payload':{}})
    return {'success':True}

@router.post('/users/{user_id}/revoke-sessions')
def revoke_sessions(user_id: UUID):
    rest('POST','rpc/chatbot_admin_save',body={'kind':'revoke_sessions','target':str(user_id),'payload':{}})
    return {'success':True}

@router.get('/knowledge')
def knowledge():
    # Access is edited through /api/knowledge/{id}/access (admins count as owners).
    return {'knowledge':rest('GET','knowledge_bases',params={'select':'id,name,owner_user_id,visibility,created_at,documents(count,size_bytes)','order':'created_at.asc'}),
            'members':rest('GET','knowledge_members')}

@router.get('/models')
def models():
    return {'models':rest('GET','app_models',params={'order':'name.asc'}),'members':rest('GET','model_members')}

@router.put('/models')
def model_access(body: ModelUpdate):
    rest('POST','rpc/chatbot_admin_save',body={'kind':'model','target':body.provider+':'+body.model_id,'payload':body.model_dump(mode='json')})
    return {'success':True}

@router.get('/audit')
def audit_log(offset: int=Query(0,ge=0)):
    return rest('GET','admin_audit',params={'order':'created_at.desc,id.desc','limit':100,'offset':offset})

@account_router.get('/usage')
@router.get('/usage')
def usage(days:int=Query(30,ge=1,le=366), user_id:UUID|None=None, model:str|None=Query(None,max_length=200), provider:Literal['openai','deepseek','ollama']|None=None, offset:int=Query(0,ge=0), export:bool=False):
    since=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat()
    filters={'created_at':f'gte.{since}','order':'created_at.desc,id.desc'}
    if user_id: filters['user_id']=f'eq.{user_id}'
    if model: filters['model_id']=f'eq.{model}'
    if provider: filters['provider']=f'eq.{provider}'
    if export:
        return _export_csv(filters)
    # Aggregates are computed by Postgres (RLS still applies); only one page of events is fetched.
    groups=rest('POST','rpc/chatbot_usage_summary',body={'p_from':since,'p_user':str(user_id) if user_id else None,'p_provider':provider,'p_model':model})
    costs=defaultdict(float); merged={}
    for g in groups:
        if g['cost'] is not None: costs[g['currency']]+=float(g['cost'])
        key=(g['user_id'],g['provider'],g['model_id'],g['operation'])
        m=merged.setdefault(key,{**{k:g[k] for k in ('user_id','provider','model_id','operation')},'calls':0,'errors':0,'input_tokens':0,'output_tokens':0,'unknown_tokens':0,'duration_ms':0,'unknown_cost':0})
        for k in ('calls','errors','input_tokens','output_tokens','unknown_tokens','duration_ms'): m[k]+=g[k]
        if g['cost'] is None and g['operation']!='request': m['unknown_cost']+=g['calls']
    events=rest('GET','usage_events',params={**filters,'limit':100,'offset':offset})
    return {'groups':list(merged.values()),'costs':dict(costs),'total_events':sum(g['calls'] for g in merged.values()),
            'events':events,'unknown_cost_events':sum(g.pop('unknown_cost') for g in merged.values())}

def _export_csv(filters):
    out=io.StringIO(); fields=['created_at','user_id','operation','provider','model_id','status','input_tokens','output_tokens','duration_ms','estimated_cost','currency']
    writer=csv.DictWriter(out,fieldnames=fields,extrasaction='ignore');writer.writeheader()
    cursor=0
    while True:
        batch=rest('GET','usage_events',params={**filters,'select':','.join(fields),'limit':1000,'offset':cursor})
        for row in batch:
            writer.writerow({k:("'"+row[k] if isinstance(row.get(k),str) and row[k].startswith(('=','+','-','@')) else row.get(k)) for k in fields})
        cursor+=len(batch)
        if len(batch)<1000: break
        if cursor>=100000: raise HTTPException(413,'Troppi eventi: riduci il periodo o filtra per utente.')
    return Response(out.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="utilizzi.csv"'})
