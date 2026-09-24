#!/usr/bin/env python3
import asyncio, json, os, subprocess
from pathlib import Path
from aiohttp import web, WSMsgType
ROOT=Path(__file__).resolve().parent; WEB=ROOT/'web'; VERSION='v0.7'
clients={'display':set(),'admin':set()}; state={'world':'bubbles','intensity':70,'speed':100,'showControls':True}
async def broadcast(payload,target=None):
    groups=[target] if target else ['display','admin']; dead=[]
    for g in groups:
        for ws in list(clients[g]):
            try: await ws.send_json(payload)
            except Exception: dead.append((g,ws))
    for g,ws in dead: clients[g].discard(ws)
async def ws_handler(request):
    role=request.query.get('role','display')
    if role not in clients: role='display'
    ws=web.WebSocketResponse(heartbeat=20); await ws.prepare(request); clients[role].add(ws)
    await ws.send_json({'type':'hello','version':VERSION,'state':state,'displayConnected':bool(clients['display'])})
    await broadcast({'type':'status','displayConnected':bool(clients['display']),'version':VERSION},'admin')
    try:
        async for msg in ws:
            if msg.type!=WSMsgType.TEXT: continue
            try: data=json.loads(msg.data)
            except Exception: continue
            typ=data.get('type')
            if role=='admin' and typ=='command':
                cmd=data.get('command'); print(f"ADMIN COMMAND RECEIVED: {cmd}",flush=True)
                if cmd=='reload': await broadcast({'type':'command','command':'reload'},'display')
                elif cmd=='world':
                    state['world']=data.get('world','bubbles'); await broadcast({'type':'state','state':state})
                elif cmd=='settings':
                    for k in ('intensity','speed','showControls'):
                        if k in data: state[k]=data[k]
                    await broadcast({'type':'state','state':state})
                elif cmd=='input':
                    event=data.get('event')
                    if event: await broadcast({'type':'input','event':event},'display')
                elif cmd=='reboot':
                    await ws.send_json({'type':'notice','message':'Reboot requested'}); asyncio.create_task(reboot_later())
            elif typ=='screen_state': await broadcast({'type':'screen_state','version':data.get('version',VERSION),'world':data.get('world')},'admin')
    finally:
        clients[role].discard(ws); await broadcast({'type':'status','displayConnected':bool(clients['display']),'version':VERSION},'admin')
    return ws
async def reboot_later():
    await asyncio.sleep(1); subprocess.run(['sudo','/sbin/reboot'])
async def admin(request): return web.FileResponse(WEB/'admin.html')
async def health(request): return web.json_response({'ok':True,'version':VERSION,'displayConnected':bool(clients['display']),'state':state})
app=web.Application(); app.router.add_get('/ws',ws_handler); app.router.add_get('/admin',admin); app.router.add_get('/health',health); app.router.add_static('/',WEB,show_index=True)
if __name__=='__main__': web.run_app(app,host='0.0.0.0',port=int(os.environ.get('PORT','8000')))
