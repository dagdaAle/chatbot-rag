"""Run inside the new WebUI container against a private legacy export.

No network access to Supabase and no secrets in logs. Original export remains
server-side. Idempotence is tracked in state.json; never import into an unrelated DB.
"""
from pathlib import Path
from datetime import datetime,timedelta
import asyncio,json,logging,re,time
import requests

logging.disable(logging.CRITICAL)
ROOT=Path('/tmp/intecha-migration')
DATA=json.loads((ROOT/'legacy.json').read_text())
CREDS=json.loads((ROOT/'auth.json').read_text())
STATE_PATH=ROOT/'state.json'
STATE=json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {'users':{},'knowledge':{},'files':{},'chats':{}}
API='http://127.0.0.1:8080'

def save():
    tmp=STATE_PATH.with_suffix('.pending')
    tmp.write_text(json.dumps(STATE,indent=2));tmp.chmod(0o600);tmp.replace(STATE_PATH)

def api(method,path,token,**kwargs):
    with requests.Session() as session:
        session.trust_env=False
        response=session.request(method,API+path,headers={'Authorization':'Bearer '+token},timeout=600,**kwargs)
    if not response.ok:
        # Do not log response bodies (they can contain document contents).
        raise RuntimeError(f'Migration API {path.split("?")[0]} HTTP {response.status_code}')
    return response.json()

def seconds(value):
    return int(datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()) if value else int(time.time())

async def token_for(user_id):
    from open_webui.models.auths import Auths
    from open_webui.utils.auth import create_token
    auth=await Auths.get_auth_by_id(user_id)
    return create_token({'id':user_id,'session_stamp':auth.session_stamp,'auth_method':'password','auth_time':int(time.time())},timedelta(hours=2))

async def users():
    from open_webui.models.auths import Auths
    from open_webui.models.users import Users
    profiles={p['id']:p for p in DATA['app_profiles']}
    for old in CREDS:
        profile=profiles[old['id']]
        if profile['role']!='admin':
            raise RuntimeError('Non-admin IAM mapping must be reviewed before migration')
        if not profile['active'] or profile.get('must_change_password'):
            raise RuntimeError('Inactive or reset-required account needs explicit migration policy')
        found=await Users.get_user_by_email(old['email'])
        if found and STATE['users'].get(old['id'])!=found.id:
            raise RuntimeError('Destination already has an unmapped account; refusing takeover')
        if not found:
            found=await Auths.insert_new_auth(email=old['email'],password=old['password_hash'],
                name=profile.get('display_name') or old['email'].split('@')[0],
                role='admin' if profile['role']=='admin' else 'user')
            if not found:raise RuntimeError('Could not create migrated account')
        STATE['users'][old['id']]=found.id;save()
    print('accounts_migrated',len(STATE['users']),flush=True)

async def documents():
    for kb in DATA['knowledge_bases']:
        owner=STATE['users'][kb['owner_user_id']]
        token=await token_for(owner)
        if kb['id'] not in STATE['knowledge']:
            grants=[]
            if kb['visibility']=='organization':
                grants.append({'principal_type':'user','principal_id':'*','permission':'read'})
            for member in DATA['knowledge_members']:
                if member['knowledge_id']==kb['id']:
                    grants.append({'principal_type':'user','principal_id':STATE['users'][member['user_id']],
                                   'permission':'write' if member['role']=='editor' else 'read'})
            result=api('POST','/api/v1/knowledge/create',token,json={'name':kb['name'],'description':kb.get('description',''),'access_grants':grants})
            STATE['knowledge'][kb['id']]=result['id'];save()
        for doc in DATA['documents']:
            if doc['knowledge_id']!=kb['id'] or doc['document_id'] in STATE['files']:continue
            path=ROOT/'uploads'/kb['id']/(doc['document_id']+'.pdf')
            if not path.is_file():raise RuntimeError('Missing original PDF; refusing partial migration')
            print('indexing_document',len(STATE['files'])+1,'of',len(DATA['documents']),flush=True)
            file_id=STATE.get('pending_files',{}).get(doc['document_id'])
            if not file_id:
                with path.open('rb') as file:
                    result=api('POST','/api/v1/files/?process=true&process_in_background=false',token,
                               files={'file':(doc['filename'],file,'application/pdf')})
                file_id=result['id']
            # Save pending ID first so an interrupted KB attachment can be retried.
            STATE.setdefault('pending_files',{})[doc['document_id']]=file_id;save()
            api('POST',f"/api/v1/knowledge/{STATE['knowledge'][kb['id']]}/file/add",token,json={'file_id':file_id})
            STATE['files'][doc['document_id']]=file_id
            STATE['pending_files'].pop(doc['document_id'],None);save()
    print('documents_migrated',len(STATE['files']),flush=True)

async def chats():
    from open_webui.models.chats import Chats,ChatForm
    kbs={kb['id']:kb for kb in DATA['knowledge_bases']}
    for conv in DATA['conversations']:
        if conv['id'] in STATE['chats']:continue
        owner=STATE['users'][conv['owner_user_id']]
        records=sorted((m for m in DATA['messages'] if m['conversation_id']==conv['id']),key=lambda m:m['timestamp'])
        messages={};previous=None
        for row in records:
            mid=row['id'];text=row['content']
            sources=[]
            for source in row.get('sources') or []:
                did=source.get('document_id')
                if did not in STATE['files']:continue
                sources.append({'source':{'id':STATE['files'][did],'name':source.get('filename','Documento'),'type':'file'},
                                'document':[source.get('text','')],
                                'metadata':[{'source':source.get('filename',''),'page':max(0,source.get('page_start',1)-1)}],
                                'distances':[source.get('score',0)]})
            if sources:text=re.sub(r'\[Fonte\s+(\d+)\]',r'[\1]',text)
            message={'id':mid,'parentId':previous,'childrenIds':[],'role':row['role'],'content':text,
                     'timestamp':seconds(row['timestamp']),'done':True}
            if row['role']=='assistant':
                message.update(model='deepseek-flash',modelName='DeepSeek Flash',modelIdx=0)
                if sources:message['sources']=sources
            if previous:messages[previous]['childrenIds']=[mid]
            messages[mid]=message;previous=mid
        kb=kbs.get(conv.get('knowledge_id'))
        payload={'title':conv['title'],'models':['deepseek-flash'],
                 'history':{'messages':messages,'currentId':previous},'messages':list(messages.values()),
                 'timestamp':seconds(conv['created_at'])*1000,
                 'files':[{'id':STATE['knowledge'][kb['id']],'name':kb['name'],'type':'collection'}] if kb else []}
        existing=await Chats.get_chat_by_id(conv['id'])
        if existing:raise RuntimeError('Unmapped destination chat exists; refusing overwrite')
        result=await Chats.insert_new_chat(conv['id'],owner,ChatForm(chat=payload))
        if not result:raise RuntimeError('Chat migration failed')
        STATE['chats'][conv['id']]=result.id;save()
    print('chats_migrated',len(STATE['chats']),flush=True)

async def main():
    import sys
    stage=sys.argv[1] if len(sys.argv)>1 else 'all'
    if stage in ('all','users'):await users()
    if stage in ('all','documents'):await documents()
    if stage in ('all','chats'):await chats()
    print('migration_stage_complete',stage,flush=True)

if __name__=='__main__':asyncio.run(main())
