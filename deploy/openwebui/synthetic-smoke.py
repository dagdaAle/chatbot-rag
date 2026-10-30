"""Server-side isolated WebUI fixture. Never mounts the migrated user/document volume."""
import json,secrets,subprocess,time,requests
name='intecha-chat-synthetic-smoke'
source=json.loads(subprocess.check_output(['docker','inspect','intecha-chat-webui-1']))[0]
env=dict(item.split('=',1) for item in source['Config']['Env'] if '=' in item)
password=secrets.token_urlsafe(40)
env.update(WEBUI_ADMIN_EMAIL='smoke@intecha.invalid',WEBUI_ADMIN_PASSWORD=password,
           WEBUI_ADMIN_NAME='Collaudo sintetico',WEBUI_SECRET_KEY=secrets.token_urlsafe(40),WEBUI_URL='http://127.0.0.1:3081',
           CORS_ALLOW_ORIGIN='http://127.0.0.1:3081')
args=['docker','run','-d','--name',name,'--network','coolify','-p','127.0.0.1:3081:8080',
      '--tmpfs','/app/backend/data:rw,mode=1777']
for key,value in env.items():args.extend(['-e',f'{key}={value}'])
args.append('intecha-chat:0.12.5')
subprocess.run(args,stdout=subprocess.DEVNULL,check=True)
s=requests.Session();s.trust_env=False
base='http://127.0.0.1:3081'
try:
 for _ in range(120):
  try:
   if s.get(base+'/health',timeout=2).ok:break
  except requests.RequestException:pass
  time.sleep(1)
 else:raise RuntimeError('Synthetic WebUI startup timeout')
 r=s.post(base+'/api/v1/auths/signin',json={'email':'smoke@intecha.invalid','password':password},timeout=30)
 assert r.ok,('signin',r.status_code)
 token=r.json()['token'];h={'Authorization':'Bearer '+token}
 r=s.get(base+'/api/models',headers=h,timeout=30)
 assert r.ok,('models',r.status_code)
 print('synthetic_login_models_ok',flush=True)
 # Exercise the full default builtin tool set, without attached knowledge.
 greeting={'model':'deepseek-flash','stream':True,'messages':[{'role':'user','content':'Ciao! Rispondi con un breve saluto in italiano.'}],
           'params':{'function_calling':'native','temperature':0,'max_tokens':150},'features':{}}
 r=s.post(base+'/api/chat/completions',headers=h,json=greeting,timeout=300)
 assert r.ok,('greeting',r.status_code)
 greeting_events=[]
 for line in r.text.splitlines():
  if line.startswith('data: ') and line[6:]!='[DONE]':
   try:greeting_events.append(json.loads(line[6:]))
   except ValueError:pass
 greeting_text=''.join(str(choice.get('delta',{}).get('content') or '') for event in greeting_events for choice in event.get('choices',[]))
 greeting_ok=bool(greeting_text.strip()) and not any('error' in event for event in greeting_events) and 'PII_' not in greeting_text
 print(json.dumps({'synthetic_greeting_ok':greeting_ok,'events':len(greeting_events)}),flush=True)
 if not greeting_ok:raise RuntimeError('Synthetic greeting with default builtin tools failed')
 r=s.post(base+'/api/v1/knowledge/create',headers=h,json={'name':'Collaudo sintetico','description':'Solo dati fittizi','access_grants':[]},timeout=120)
 assert r.ok,('create_kb',r.status_code)
 kb=r.json()['id']
 fixture='Scheda di collaudo Intecha. Il codice fittizio INTECHA-42 ha stato VERDE. Il codice INTECHA-99 ha stato ROSSO. Tutti questi dati sono inventati esclusivamente per un test tecnico.'
 r=s.post(base+'/api/v1/files/?process=true&process_in_background=false',headers=h,
          files={'file':('collaudo-sintetico.txt',fixture.encode(),'text/plain')},timeout=180)
 assert r.ok,('upload',r.status_code)
 file_id=r.json()['id']
 r=s.post(base+f'/api/v1/knowledge/{kb}/file/add',headers=h,json={'file_id':file_id},timeout=180)
 assert r.ok,('attach',r.status_code)
 body={'model':'deepseek-flash','stream':True,'messages':[{'role':'user','content':'Cerca nel documento di collaudo: qual è lo stato del codice INTECHA-42? Cita la fonte e non usare altri dati.'}],
       'files':[{'id':kb,'type':'collection','name':'Collaudo sintetico'}],
       'params':{'function_calling':'native','temperature':0,'max_tokens':700},'features':{}}
 r=s.post(base+'/api/chat/completions',headers=h,json=body,timeout=300)
 assert r.ok,('chat',r.status_code)
 events=[]
 for line in r.text.splitlines():
  if line.startswith('data: ') and line[6:]!='[DONE]':
   try:events.append(json.loads(line[6:]))
   except ValueError:pass
 text=''.join(str(choice.get('delta',{}).get('content') or '') for event in events for choice in event.get('choices',[]))
 print(json.dumps({'synthetic_chat_http':r.status_code,'events':len(events),'correct_answer':'verde' in text.lower(),
       'citations':'[' in text,'no_placeholders':'PII_' not in text,'error_events':any('error' in e for e in events)}),flush=True)
 if 'verde' not in text.lower():
  # Synthetic fixture only, safe diagnostic output.
  print('synthetic_response',r.text[:8000],flush=True)
  raise RuntimeError('Synthetic retrieval did not produce expected answer')
finally:
 subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,check=False)
