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
    role: Literal['admin','manager','user']
    active: bool
    monthly_requests: int | None = Field(default=None, gt=0)
    requests_per_minute: int = Field(default=20, ge=1, le=600)
    concurrent_requests: int = Field(default=2, ge=1, le=20)

class CreateUser(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    password: SecretStr = Field(min_length=12, max_length=128)
    display_name: str = Field(default='', max_length=200)

class PasswordChange(BaseModel):
    current_password: SecretStr = Field(min_length=1, max_length=128)
    password: SecretStr = Field(min_length=12, max_length=128)

class PasswordReset(BaseModel):
    password: SecretStr = Field(min_length=12, max_length=128)

class EmailChange(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')

class Member(BaseModel):
    user_id: UUID
    can_manage: bool = False

class KnowledgeAccess(BaseModel):
    shared: bool
    members: list[Member] = Field(default_factory=list, max_length=1000)

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
    privileged('PATCH','/rest/v1/app_profiles',params={'id':f'eq.{user_id}'},body={'display_name':body.display_name,'must_change_password':True})
    privileged('PUT',f'/auth/v1/admin/users/{user_id}',body={'ban_duration':'none'})
    audit('user_created',user_id)
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
    rest('POST','rpc/chatbot_admin_save',body={'kind':'force_password','target':str(user_id),'payload':{}})
    privileged('PUT',f'/auth/v1/admin/users/{user_id}',body={'password':body.password.get_secret_value()})
    audit('password_reset',str(user_id))
    return {'success':True}

@router.post('/users/{user_id}/revoke-sessions')
def revoke_sessions(user_id: UUID):
    rest('POST','rpc/chatbot_admin_save',body={'kind':'revoke_sessions','target':str(user_id),'payload':{}})
    return {'success':True}

@router.get('/knowledge')
def knowledge():
    return {'knowledge':rest('GET','knowledge_bases',params={'select':'*,documents(count,size_bytes)','order':'created_at.asc'}),
            'members':rest('GET','knowledge_members')}

@router.put('/knowledge/{knowledge_id}/access')
def knowledge_access(knowledge_id: UUID,body: KnowledgeAccess):
    rest('POST','rpc/chatbot_admin_save',body={'kind':'knowledge','target':str(knowledge_id),'payload':body.model_dump(mode='json')})
    return {'success':True}

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
    filters={'created_at':f'gte.{(datetime.now(timezone.utc)-timedelta(days=days)).isoformat()}','order':'created_at.desc,id.desc'}
    if user_id: filters['user_id']=f'eq.{user_id}'
    if model: filters['model_id']=f'eq.{model}'
    if provider: filters['provider']=f'eq.{provider}'
    # Page all rows for accurate aggregates; do not mistake PostgREST's row cap for totals.
    rows=[]; cursor=0
    while True:
        batch=rest('GET','usage_events',params={**filters,'limit':1000,'offset':cursor})
        rows.extend(batch); cursor+=len(batch)
        if len(batch)<1000: break
        if cursor>=100000: raise HTTPException(413,'Troppi eventi: riduci il periodo o filtra per utente.')
    if export:
        out=io.StringIO(); fields=['created_at','user_id','operation','provider','model_id','status','input_tokens','output_tokens','duration_ms','estimated_cost','currency']
        writer=csv.DictWriter(out,fieldnames=fields,extrasaction='ignore');writer.writeheader()
        for row in rows:
            writer.writerow({k:("'"+str(row.get(k)) if isinstance(row.get(k),str) and row[k].startswith(('=','+','-','@')) else row.get(k)) for k in fields})
        return Response(out.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="utilizzi.csv"'})
    groups={}; costs=defaultdict(float)
    for row in rows:
        key=(row['user_id'],row['provider'],row['model_id'],row['operation'])
        group=groups.setdefault(key,{'user_id':key[0],'provider':key[1],'model_id':key[2],'operation':key[3],'calls':0,'errors':0,'input_tokens':0,'output_tokens':0,'unknown_tokens':0,'duration_ms':0})
        group['calls']+=1;group['errors']+=row['status']=='error';group['input_tokens']+=row.get('input_tokens') or 0;group['output_tokens']+=row.get('output_tokens') or 0;group['duration_ms']+=row.get('duration_ms') or 0
        group['unknown_tokens']+=row.get('input_tokens') is None or row.get('output_tokens') is None
        if row.get('estimated_cost') is not None: costs[row['currency']]+=float(row['estimated_cost'])
    return {'groups':list(groups.values()),'costs':dict(costs),'total_events':len(rows),'events':rows[offset:offset+100], 'unknown_cost_events':sum(r['operation']!='request' and r.get('estimated_cost') is None for r in rows)}
