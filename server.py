#!/usr/bin/env python3
import asyncio,json,os,subprocess
from pathlib import Path
from aiohttp import web,WSMsgType
ROOT=Path(__file__).resolve().parent;WEB=ROOT/'web';VERSION='v10.3'
update_running=False
clients={'display':set(),'admin':set()}
gpio_buttons=[]

def pi_stats():
    try:
        temp=float(Path('/sys/class/thermal/thermal_zone0/temp').read_text().strip())/1000
    except Exception: temp=None
    try:
        raw=subprocess.check_output(['vcgencmd','get_throttled'],text=True,timeout=1).strip()
        throttled=raw.split('=',1)[1] if '=' in raw else raw
    except Exception: throttled=None
    try:
        raw=subprocess.check_output(['vcgencmd','measure_clock','arm'],text=True,timeout=1).strip()
        clock_mhz=round(int(raw.split('=',1)[1])/1_000_000) if '=' in raw else None
    except Exception: clock_mhz=None
    return {'tempC':round(temp,1) if temp is not None else None,'throttled':throttled,'clockMHz':clock_mhz}

async def system_reporter():
    while True:
        if clients['admin']:
            await broadcast({'type':'system_stats',**pi_stats()},'admin')
        await asyncio.sleep(2)

async def gpio_reporter():
    global gpio_buttons
    try:
        from gpiozero import Button
        loop=asyncio.get_running_loop()
        button_map=[
            ('BLUE',17,11),
            ('RED',27,13),
            ('GREEN',22,15),
            ('YELLOW',23,16),
        ]
        for name,gpio,pin in button_map:
            button=Button(gpio,pull_up=True,bounce_time=0.05)
            button.when_pressed=lambda n=name: asyncio.run_coroutine_threadsafe(
                broadcast({'type':'input','event':f'{n}_DOWN'},'display'),loop)
            button.when_released=lambda n=name: asyncio.run_coroutine_threadsafe(
                broadcast({'type':'input','event':f'{n}_UP'},'display'),loop)
            gpio_buttons.append(button)
            print(f"GPIO: {name.title()} button ready on GPIO{gpio} (physical pin {pin}) to GND",flush=True)
    except Exception as e:
        for button in gpio_buttons:
            button.close()
        gpio_buttons=[]
        print(f"GPIO: disabled ({e})",flush=True)

async def startup(app):
    app['system_reporter']=asyncio.create_task(system_reporter())
    await gpio_reporter()

async def cleanup(app):
    global gpio_buttons
    for button in gpio_buttons:
        button.close()
    gpio_buttons=[]
    app['system_reporter'].cancel()
    try: await app['system_reporter']
    except asyncio.CancelledError: pass

state={'world':'bubbles','intensity':70,'speed':100,'showControls':True}
async def broadcast(payload,target=None):
    dead=[]
    for g in ([target] if target else ['display','admin']):
        for ws in list(clients[g]):
            try: await ws.send_json(payload)
            except Exception: dead.append((g,ws))
    for g,ws in dead: clients[g].discard(ws)
async def ws_handler(request):
    role=request.query.get('role','display')
    if role not in clients:role='display'
    ws=web.WebSocketResponse(heartbeat=20);await ws.prepare(request);clients[role].add(ws)
    await ws.send_json({'type':'hello','version':VERSION,'state':state,'displayConnected':bool(clients['display'])})
    await broadcast({'type':'status','displayConnected':bool(clients['display']),'version':VERSION},'admin')
    try:
        async for msg in ws:
            if msg.type!=WSMsgType.TEXT:continue
            try:data=json.loads(msg.data)
            except Exception:continue
            typ=data.get('type')
            if role=='admin' and typ=='command':
                cmd=data.get('command');print(f"ADMIN COMMAND RECEIVED: {cmd}",flush=True)
                if cmd=='reload':await broadcast({'type':'command','command':'reload'},'display')
                elif cmd=='world':state['world']=data.get('world','bubbles');await broadcast({'type':'state','state':state})
                elif cmd=='settings':
                    for k in ('intensity','speed','showControls'):
                        if k in data:state[k]=data[k]
                    await broadcast({'type':'state','state':state})
                elif cmd=='input':
                    if data.get('event'):await broadcast({'type':'input','event':data['event']},'display')
                elif cmd=='control':await broadcast({'type':'control','control':data.get('control',{})},'display')
                elif cmd=='update':
                    if update_running:await ws.send_json({'type':'update_status','status':'running','message':'Update already in progress…'})
                    else:asyncio.create_task(run_update())
                elif cmd=='reboot':await ws.send_json({'type':'notice','message':'Reboot requested'});asyncio.create_task(reboot_later())
            elif role=='display' and typ=='screen_state':await broadcast(dict(data,type='screen_state'),'admin')
    finally:
        clients[role].discard(ws);await broadcast({'type':'status','displayConnected':bool(clients['display']),'version':VERSION},'admin')
    return ws
async def run_update():
    global update_running
    if update_running:return
    update_running=True
    await broadcast({'type':'update_status','status':'running','message':'Downloading and installing update…'},'admin')
    try:
        # Run the updater with systemd detached from this service.  The updater
        # restarts bubbleworld.service, so it must not be our child process.
        # --no-block returns before the transient unit finishes; Admin will
        # disconnect during restart and reconnect to the new server.
        unit='bubbleworld-update'
        proc=await asyncio.create_subprocess_exec(
            'sudo','-n','/usr/bin/systemd-run','--unit',unit,'--collect',
            '--property=WorkingDirectory='+str(ROOT),
            '/usr/bin/bash',str(ROOT/'update'),
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT)
        out,_=await proc.communicate()
        log=out.decode(errors='replace')[-4000:]
        if proc.returncode:
            await broadcast({'type':'update_status','status':'error','message':f'Could not start updater (exit {proc.returncode})','log':log},'admin')
            update_running=False
        else:
            await broadcast({'type':'update_status','status':'running','message':'Updater started. The server will reconnect automatically.'},'admin')
    except Exception as e:
        await broadcast({'type':'update_status','status':'error','message':f'Update failed: {e}'},'admin')
        update_running=False

async def reboot_later():await asyncio.sleep(1);subprocess.run(['sudo','/sbin/reboot'])
async def admin(request):return web.FileResponse(WEB/'admin.html')
async def health(request):return web.json_response({'ok':True,'version':VERSION,'displayConnected':bool(clients['display']),'state':state})
app=web.Application();app.on_startup.append(startup);app.on_cleanup.append(cleanup);app.router.add_get('/ws',ws_handler);app.router.add_get('/admin',admin);app.router.add_get('/health',health);app.router.add_static('/',WEB,show_index=True)
if __name__=='__main__':web.run_app(app,host='0.0.0.0',port=int(os.environ.get('PORT','8000')))
