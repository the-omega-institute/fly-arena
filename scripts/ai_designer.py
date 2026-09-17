"""Any agent can run this example; credentials stay in environment variables.

ARENA_URL=https://your-arena ARENA_TOKEN=... python scripts/ai_designer.py
Uses httpx from the project's environment. An actual mutation is validated,
published and evaluated against its parent under both slot assignments.
"""
import json
import os
from pathlib import Path
import time
import uuid
import httpx


def main():
    base = os.environ.get('ARENA_URL','http://127.0.0.1:8080').rstrip('/')
    token = os.environ.get('ARENA_TOKEN')
    if not token:
        raise SystemExit('Create a designer in the web app and set ARENA_TOKEN to its API token.')
    with httpx.Client(base_url=base+'/api/v1',headers={'Authorization':'Bearer '+token},timeout=120) as c:
        season=c.get('/season').raise_for_status().json()
        flies=c.get('/flies').raise_for_status().json()
        parent=next(f for f in flies if f['name']=='Wild Type / 原型')
        spec=parent['spec']|{'name':'Agent Nectar '+uuid.uuid4().hex[:6], 'parent_id':parent['id'],
            'description':'Agent example: fixed +15% olfactory experiment; advantage unproven.',
            'connectome_sha256':season['connectome']['sha256'],
            'weight_mutations':[{'selector':'olfactory','scale':1.15}]}
        report=c.post('/flies/validate',json=spec).raise_for_status().json()
        print('Authoritative budget:',report['budget_used'])
        fly=c.post('/flies',json=spec).raise_for_status().json()
        print('Published immutable design:',fly['id'])
        tournament=c.post('/tournaments',headers={'Idempotency-Key':uuid.uuid4().hex},json={
            'name':'Agent olfactory experiment','fly_ids':[parent['id'],fly['id']],
            'map_id':'orchard','mode':'contest','seeds':[42],'duration_seconds':2
        }).raise_for_status().json()
        print('Paired series:',tournament['id'],flush=True)
        deadline=time.monotonic()+3600
        while time.monotonic()<deadline:
            tournament=c.get('/tournaments/'+tournament['id']).raise_for_status().json()
            if tournament['status']!='running': break
            print([(m['status'],round(m['progress'],2)) for m in tournament['matches']],flush=True)
            time.sleep(5)
        else: raise SystemExit('Polling timeout; tournament continues on the server.')
        folder=Path('var/agent-experiments')/tournament['id'];folder.mkdir(parents=True,exist_ok=True)
        (folder/'tournament.json').write_text(json.dumps(tournament,indent=2))
        for match in tournament['matches']:
            if match['status']=='verified':
                trace=c.get('/matches/'+match['id']+'/frames').raise_for_status().json()
                (folder/(match['id']+'.json')).write_text(json.dumps(trace))
        print(json.dumps(tournament['standings'],indent=2))
        print('Evidence saved to',folder)
        if tournament['status']!='complete': raise SystemExit('A match failed; this series has no complete verdict.')


if __name__=='__main__': main()
