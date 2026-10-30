"""Server-side backup/export. Private files only, never stdout content or hashes."""
from pathlib import Path
import datetime, json, os, shutil, subprocess
root=Path('/home/mulo/intecha-chat')
backup=root/'migration'
backup.mkdir(mode=0o700,exist_ok=True)
os.chmod(backup,0o700)
legacy='1kx2w4ye7sd5jb9awemsq7yy-20261019T192128'
program='''import os,json,requests
h={'apikey':os.environ['SUPABASE_ADMIN_KEY'],'Authorization':'Bearer '+os.environ['SUPABASE_ADMIN_KEY']}
result={}
for table in ['app_profiles','knowledge_bases','knowledge_members','documents','conversations','messages','usage_events','app_models','model_members','admin_audit','import_jobs']:
 rows=[]; offset=0
 while True:
  r=requests.get(os.environ['SUPABASE_URL'].rstrip('/')+'/rest/v1/'+table,params={'select':'*','limit':1000,'offset':offset},headers=h,timeout=30)
  if not r.ok:raise RuntimeError('Export failed: '+table+' HTTP '+str(r.status_code))
  batch=r.json();rows.extend(batch)
  if len(batch)<1000:break
  offset+=len(batch)
 result[table]=rows
print(json.dumps(result,ensure_ascii=False))
'''
raw=subprocess.check_output(['docker','exec',legacy,'python','-c',program])
data=json.loads(raw)
path=backup/'legacy.json'
if path.exists():
 data=json.loads(path.read_text())
else:
 fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
 with os.fdopen(fd,'wb') as f:f.write(raw)
# Only app users, retaining existing bcrypt hashes without knowing their passwords.
sql="select coalesce(json_agg(json_build_object('id',u.id,'email',u.email,'password_hash',u.encrypted_password)),'[]'::json) from auth.users u join public.app_profiles p on p.id=u.id"
credentials=subprocess.check_output(['docker','exec','supabase-db-ihwshg2ivu52ameoapet4g35','psql','-U','supabase_admin','-d','postgres','-tAc',sql])
users=json.loads(credentials)
if len(users)!=len(data['app_profiles']) or any(not (u['password_hash'] or '').startswith(('$2a$','$2b$','$2y$')) for u in users):
 raise SystemExit('Credentials need review; no plaintext passwords exported')
if not (backup/'auth.json').exists():
 fd=os.open(backup/'auth.json',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
 with os.fdopen(fd,'wb') as f:f.write(credentials)
info=json.loads(subprocess.check_output(['docker','inspect',legacy]))[0]
source=next(Path(m['Source']) for m in info['Mounts'] if m['Destination']=='/data')
# Stop-free originals/JSON export; full coherent backup is taken at cutover.
for name in ['uploads','extracted']:
 if not (backup/name).exists():subprocess.run(['docker','cp',legacy+':/data/'+name,str(backup/name)],check=True)
manifest={'exported_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'legacy_container':legacy,'legacy_image':info['Config']['Image'],
 'counts':{k:len(v) for k,v in data.items()},'pdf_files':len(list((backup/'uploads').rglob('*.pdf')))}
(backup/'manifest.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps({'counts':manifest['counts'],'pdf_files':manifest['pdf_files'],'backup':'/home/mulo/intecha-chat/migration'}))
