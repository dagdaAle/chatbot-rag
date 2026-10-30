"""Reviewed host-specific cutover. Keep all legacy resources for rollback."""
from pathlib import Path
import datetime,json,os,subprocess,time,urllib.request
root=Path('/home/mulo/intecha-chat')
legacy='1kx2w4ye7sd5jb9awemsq7yy-20261019T192128'
worker='import-worker-jort9hm5ny7nruhpn6fbtmwz'
new='intecha-chat-webui-1'
subprocess.run(['python3',str(root/'deploy/openwebui/pre-cutover.py')],check=True)
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup=root/'backups'/stamp
backup.mkdir(parents=True,mode=0o700)
os.chmod(root/'backups',0o700)
# Preserve routing evidence without dumping container environment secrets.
old_info=json.loads(subprocess.check_output(['docker','inspect',legacy]))[0]
(backup/'legacy-routing.json').write_text(json.dumps({'container':legacy,'worker':worker,
 'image':old_info['Config']['Image'],'labels':old_info['Config'].get('Labels',{}),
 'mounts':[{'source':m['Source'],'destination':m['Destination']} for m in old_info['Mounts']]},indent=2))
compose=['docker','compose','-f',str(root/'docker-compose.yml'),'-f',str(root/'deploy/openwebui/docker-compose.route.yml')]
try:
 subprocess.run(['docker','stop','-t','60',worker,legacy,new],check=True,stdout=subprocess.DEVNULL)
 print('legacy_and_candidate_stopped_for_consistent_backup',flush=True)
 script="""import pathlib,tarfile
for source,name in [('/legacy','legacy-data.tar.gz'),('/webui','webui-data.tar.gz')]:
 with tarfile.open('/backup/'+name,'w:gz') as archive:archive.add(source,arcname='data')
"""
 subprocess.run(['docker','run','--rm','-v','1kx2w4ye7sd5jb9awemsq7yy-chatbot-data:/legacy:ro',
   '-v','intecha-openwebui-data:/webui:ro','-v',str(backup)+':/backup',
   'python:3.12-slim','python','-c',script],check=True)
 subprocess.run(['docker','run','--rm','-v',str(backup)+':/backup','python:3.12-slim','python','-c',
                 "import os,pathlib;[(os.chown(p,1000,1000),os.chmod(p,0o600)) for p in pathlib.Path('/backup').iterdir()]"],check=True)
 print('consistent_backups_saved',str(backup),flush=True)
 subprocess.run(compose+['up','-d'],cwd=root,check=True)
 # Verify both local API and routed public endpoint without sending any document to a provider.
 for attempt in range(150):
  try:
   with urllib.request.urlopen('http://127.0.0.1:3080/api/config',timeout=3) as response:local=json.load(response)
   if local.get('name')=='Intecha':break
  except Exception:pass
  time.sleep(1)
 else:raise RuntimeError('New application startup failed')
 public=None
 for attempt in range(12):
  try:
   req=urllib.request.Request('https://chatbot.intecha.dev/api/config',headers={'User-Agent':'Mozilla/5.0','Cache-Control':'no-cache'})
   with urllib.request.urlopen(req,timeout=15) as response:public=json.load(response)
   if public.get('name')=='Intecha':break
  except Exception:pass
  time.sleep(2)
 if not public or public.get('name')!='Intecha':raise RuntimeError('Public router verification failed')
 report={'completed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'domain':'https://chatbot.intecha.dev',
         'name':public['name'],'version':public.get('version'),'locale':public.get('default_locale'),
         'backup':str(backup),'legacy_stopped':True,'documents_llm_test':'not_run_without_specific_consent'}
 (root/'migration/cutover.json').write_text(json.dumps(report,indent=2))
 print(json.dumps(report),flush=True)
except BaseException:
 # No destruction: return traffic to the unchanged legacy router.
 subprocess.run(['docker','stop','-t','10',new],stdout=subprocess.DEVNULL,check=False)
 subprocess.run(['docker','start',legacy,worker],stdout=subprocess.DEVNULL,check=False)
 print('cutover_failed_legacy_restarted',flush=True)
 raise
