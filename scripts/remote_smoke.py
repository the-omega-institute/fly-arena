"""Run the actual public API contract over loopback on a deployment."""
import json
import os
from pathlib import Path
import subprocess
import sys
import httpx

c=httpx.Client(base_url='http://127.0.0.1:8080/api/v1',timeout=120)
print('health',c.get('/health').raise_for_status().json(),flush=True)
u=c.post('/identities',json={'name':'Genesis verification agent'}).raise_for_status().json()
c.headers['Authorization']='Bearer '+u['token']
flies=c.get('/flies').raise_for_status().json()
base=next(f for f in flies if f['name']=='Wild Type / 原型')
nectar=next(f for f in flies if f['name']=='Nectar / 花蜜')
for mode,mapid in [('forage','orchard'),('contest','maze'),('sumo','ring')]:
    m=c.post('/matches',json={'fly_ids':[base['id']] if mode=='forage' else [base['id'],nectar['id']], 'map_id':mapid,'mode':mode,'seed':42,'duration_seconds':2}).raise_for_status().json()
    print('sample',mapid,m['id'],flush=True)
print('anatomical preview',c.get('/preview').raise_for_status().status_code,flush=True)
subprocess.run([sys.executable,'scripts/ai_designer.py'],env=os.environ|{'ARENA_URL':'http://127.0.0.1:8080','ARENA_TOKEN':u['token']},check=True)
