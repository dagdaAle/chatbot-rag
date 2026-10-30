"""Read-only final source consistency check. Do not publish if source data changed."""
from pathlib import Path
import json,subprocess
root=Path('/home/mulo/intecha-chat')
original=json.loads((root/'migration/legacy.json').read_text())
program='''import os,json,requests
h={'apikey':os.environ['SUPABASE_ADMIN_KEY'],'Authorization':'Bearer '+os.environ['SUPABASE_ADMIN_KEY']}
result={}
for table in ['app_profiles','knowledge_bases','knowledge_members','documents','conversations','messages']:
 rows=[];offset=0
 while True:
  r=requests.get(os.environ['SUPABASE_URL'].rstrip('/')+'/rest/v1/'+table,params={'select':'*','limit':1000,'offset':offset},headers=h,timeout=30)
  if not r.ok:raise RuntimeError('Source verification failed')
  batch=r.json();rows.extend(batch)
  if len(batch)<1000:break
  offset+=len(batch)
 result[table]=rows
print(json.dumps(result))
'''
current=json.loads(subprocess.check_output(['docker','exec','1kx2w4ye7sd5jb9awemsq7yy-20261019T192128','python','-c',program]))
def canonical(rows):return sorted(json.dumps(r,sort_keys=True) for r in rows)
for table,rows in current.items():
 if canonical(rows)!=canonical(original[table]):raise SystemExit('Source changed since export: '+table+'; synchronize before cutover')
query="select count(*) from auth.mfa_factors f join public.app_profiles p on p.id=f.user_id where f.status='verified'"
count=int(subprocess.check_output(['docker','exec','supabase-db-ihwshg2ivu52ameoapet4g35','psql','-U','supabase_admin','-d','postgres','-tAc',query]))
if count:raise SystemExit('Existing MFA must be migrated before cutover')
print('Source snapshot unchanged; no verified MFA factors to lose; cutover consistency OK')
