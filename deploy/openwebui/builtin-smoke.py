"""Server-only synthetic check using the deployed feature flags and saved-chat tools.

Reads no user rows, chats or documents. Only public builtin schemas enter the
provider request. Run with python3 on the verified Docker host.
"""
import json
import subprocess

schema_script = '''import asyncio,json
from starlette.requests import Request
from open_webui.utils.tools import get_builtin_tools
async def main():
    tools=await get_builtin_tools(Request({'type':'http','state':{}}),{
        '__user__':{'id':'synthetic-user','role':'admin'},
        '__metadata__':{'chat_id':'11111111-1111-4111-8111-111111111111'}})
    print('SPECS:'+json.dumps([{'type':'function','function':v['spec']} for v in tools.values()]))
asyncio.run(main())
'''
result = subprocess.run(['docker','exec','-i','intecha-chat-webui-1','python','-'],
                        input=schema_script, text=True, capture_output=True, check=True)
specs = json.loads(next(line[6:] for line in result.stdout.splitlines() if line.startswith('SPECS:')))
body = {'model':'deepseek-flash','messages':[{'role':'user','content':
        'Ciao! Rispondi solo con un breve saluto in italiano, senza usare strumenti.'}],
        'tools':specs,'max_tokens':150,'temperature':0}
request_script = '''import os,json,httpx
body=json.loads(BODY)
with httpx.Client(trust_env=False,timeout=300) as client:
    r=client.post('http://127.0.0.1:8081/v1/chat/completions',json=body,
        headers={'Authorization':'Bearer '+os.environ['GATEWAY_API_KEY']})
    assert r.status_code==200,('builtin_smoke_http',r.status_code)
    text=r.json()['choices'][0]['message'].get('content') or ''
    assert text.strip() and 'PII_' not in text
    print(json.dumps({'builtin_tools':len(body['tools']),'synthetic_greeting_ok':True,'http':r.status_code}))
'''.replace('BODY',repr(json.dumps(body)))
subprocess.run(['docker','exec','-i','intecha-chat-privacy-gateway-1','python','-'],
               input=request_script, text=True, check=True)
