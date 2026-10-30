"""Run on the deployment host. Never print credentials or legacy chat contents."""
from pathlib import Path
import json,os,secrets,subprocess
root=Path('/home/mulo/intecha-chat')
root.mkdir(mode=0o700,exist_ok=True)
os.chmod(root,0o700)
legacy='1kx2w4ye7sd5jb9awemsq7yy-20261019T192128'
info=json.loads(subprocess.check_output(['docker','inspect',legacy]))[0]
env=dict(x.split('=',1) for x in info['Config']['Env'] if '=' in x)
path=root/'.env'
if not path.exists():
 values={
  'INTECHA_REBRANDING_CONFIRMED':'small-scale-50',
  'WEBUI_SECRET_KEY':secrets.token_urlsafe(48),
  'GATEWAY_API_KEY':secrets.token_urlsafe(48),
  'DEEPSEEK_API_KEY':env['DEEPSEEK_API_KEY'],
  'DEEPSEEK_CHAT_MODEL':env.get('DEEPSEEK_CHAT_MODEL','deepseek-flash'),
  'ANONYMIZER_TOKEN':env['ANONYMIZER_TOKEN'],
  'ANONYMIZER_URL':'http://anonymizer:8000',
  'OLLAMA_BASE_URL':'http://ollama:11434',
  'INTECHA_NETWORK':'coolify',
  'WEBUI_URL':'https://chatbot.intecha.dev',
  'INTECHA_PREVIEW_PORT':'3080',
 }
 for value in values.values():
  if any(c in value for c in "\n\r'"):raise SystemExit('Unsupported secret encoding; no values were written')
 fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
 with os.fdopen(fd,'w') as stream:
  stream.write(''.join(f"{key}='{value}'\n" for key,value in values.items()))
print('Deployment environment ready; existing anonymizer token/provider key retained; secrets not printed')
