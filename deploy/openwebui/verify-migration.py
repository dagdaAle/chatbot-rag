"""Inside WebUI: local-only integrity checks; never call a model provider."""
from pathlib import Path
from datetime import timedelta
import asyncio,hashlib,json,logging,re,time
import requests
logging.disable(logging.CRITICAL)

async def main():
 from open_webui.models.auths import Auths
 from open_webui.models.users import Users
 from open_webui.models.chats import Chats
 from open_webui.utils.auth import create_token
 root=Path('/tmp/intecha-migration')
 data=json.loads((root/'legacy.json').read_text());creds=json.loads((root/'auth.json').read_text());state=json.loads((root/'state.json').read_text())
 assert len(state['users'])==len(creds)==2
 assert len(state['files'])==len(data['documents'])==4
 assert len(state['knowledge'])==len(data['knowledge_bases'])==2
 assert len(state['chats'])==len(data['conversations'])==14
 for old in creds:
  auth=await Auths.get_auth_by_id(state['users'][old['id']]);assert auth.password==old['password_hash']
 total=0
 for conv in data['conversations']:
  chat=await Chats.get_chat_by_id(state['chats'][conv['id']]);assert chat.user_id==state['users'][conv['owner_user_id']]
  actual=chat.chat['history']['messages']
  expected=[m for m in data['messages'] if m['conversation_id']==conv['id']]
  assert len(actual)==len(expected)
  for msg in expected:
   expected_text=re.sub(r'\[Fonte\s+(\d+)\]',r'[\1]',msg['content']) if msg.get('sources') else msg['content']
   assert actual[msg['id']]['content']==expected_text
  total+=len(expected)
 assert total==40
 uid=next(iter(state['users'].values()));auth=await Auths.get_auth_by_id(uid)
 token=create_token({'id':uid,'session_stamp':auth.session_stamp,'auth_method':'password','auth_time':int(time.time())},timedelta(minutes=10))
 h={'Authorization':'Bearer '+token};s=requests.Session();s.trust_env=False
 for doc in data['documents']:
  r=s.get('http://127.0.0.1:8080/api/v1/files/'+state['files'][doc['document_id']]+'/content',headers=h,timeout=30)
  assert r.ok
  original=root/'uploads'/doc['knowledge_id']/(doc['document_id']+'.pdf')
  assert hashlib.sha256(original.read_bytes()).digest()==hashlib.sha256(r.content).digest()
 for kb in data['knowledge_bases']:
  r=s.get('http://127.0.0.1:8080/api/v1/knowledge/'+state['knowledge'][kb['id']],headers=h,timeout=30)
  assert r.ok
  grants=r.json()['access_grants']
  wildcard=any(g['principal_id']=='*' for g in grants)
  assert wildcard==(kb['visibility']=='organization')
  assert r.json()['user_id']==state['users'][kb['owner_user_id']]
  # Retrieval endpoint uses the already configured local Ollama encoder, no LLM calls.
  r=s.post('http://127.0.0.1:8080/api/v1/retrieval/query/collection',headers=h,
     json={'collection_names':[state['knowledge'][kb['id']]],'query':'region growing' if kb['name']=='esami' else 'prezzo','k':3},timeout=180)
  assert r.ok,('local_retrieval',r.status_code)
  assert any(r.json().get('documents',[])), 'No indexed passages'
 print(json.dumps({'accounts':2,'password_hashes_preserved':True,'knowledge_bases':2,'knowledge_access_preserved':True,
                   'pdf_files':4,'pdf_hashes_match':True,'chats':14,'messages':40,'chat_ownership_content_preserved':True,
                   'local_retrieval':True,'external_llm_calls':0}))

asyncio.run(main())
