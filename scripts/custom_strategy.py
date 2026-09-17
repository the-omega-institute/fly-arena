"""Run your own optimizer locally; Arena executes only validated FlySpec candidates.

Set ARENA_URL and ARENA_TOKEN, then:
  python scripts/custom_strategy.py --generations 2 --population 2 --budget 4
Attach to an external-strategy session created in the browser:
  python scripts/custom_strategy.py --run SESSION_ID

Replace propose() with your optimizer. It may use any local library/model, while
all evaluation, budget, score and replay handling stays in the Arena API.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import time
import uuid

import httpx


def propose(founder: dict, history: list[dict], generation: int, slot: int) -> dict:
    """Example: deterministic coordinate search with a retained incumbent.

This hook runs on the user's machine. Fitness can be zero or negative; only
finished earlier generations are eligible parents. FlySpecs are absolute edits
relative to the canonical graph, not deltas added a second time to the parent.
"""
    eligible = [m for m in history if m['generation'] < generation and m['fitness'] is not None]
    parent = max(eligible, key=lambda m: (m['fitness'], -m['generation'], -m['slot']))['fly'] if eligible else founder
    spec = deepcopy(parent['spec'])
    spec.update(name=f'Coordinate G{generation+1}.{slot+1}', parent_id=parent['id'])
    if generation and slot == 0:
        return spec
    circuit = ['olfactory', 'projection', 'descending'][(generation+slot-1) % 3]
    scales = {}
    for mutation in spec['weight_mutations']:
        scales[mutation['selector']] = scales.get(mutation['selector'], 1.) * mutation['scale']
    step = .08/(generation+1) * (-1 if slot % 2 == 0 else 1)
    scales[circuit] = min(2., max(.5, scales.get(circuit, 1.) + step))
    spec['weight_mutations'] = [{'selector':key, 'scale':value} for key,value in sorted(scales.items())]
    return spec


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run')
    parser.add_argument('--founder')
    parser.add_argument('--population',type=int,default=2)
    parser.add_argument('--generations',type=int,default=2)
    parser.add_argument('--budget',type=int,default=4)
    parser.add_argument('--seconds',type=int,default=1)
    parser.add_argument('--map',choices=['orchard','maze','ring'],default='orchard')
    parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--key',default=uuid.uuid4().hex)
    parser.add_argument('--save-best',action='store_true')
    parser.add_argument('--timeout',type=int,default=3600)
    parser.add_argument('--output',type=Path,default=Path('var/custom-strategies'))
    args=parser.parse_args()
    token=os.environ.get('ARENA_TOKEN')
    if not token:parser.error('Set ARENA_TOKEN to your designer/agent API token.')
    base=os.environ.get('ARENA_URL','http://127.0.0.1:18080').rstrip('/')
    with httpx.Client(base_url=base+'/api/v1',headers={'Authorization':'Bearer '+token},timeout=120) as client:
        def api(method,path,**kwargs):
            # Candidate identity is (session, generation, slot); retrying the exact
            # proposal is safe even when a write succeeded but its response was lost.
            for attempt in range(3):
                try:return client.request(method,path,**kwargs).raise_for_status().json()
                except httpx.TransportError:
                    if attempt==2:raise
                    time.sleep(2)
        if args.run:
            run=api('GET','/training/'+args.run)
        else:
            flies=api('GET','/flies')
            founder=args.founder or next(f['id'] for f in flies if f.get('reference_kind')=='wildtype')
            print('Creation key:',args.key,flush=True)
            run=api('POST','/training',headers={'Idempotency-Key':args.key},json={
                'name':'My coordinate search','strategy':'external','founder_id':founder,
                'circuits':[], 'population':args.population,'generations':args.generations,
                'max_evaluations':args.budget,'duration_seconds':args.seconds,'map_id':args.map,
                'seed':args.seed,'mode':'forage','bridge_profile':'legacy-v1',
            })
        if run['spec']['strategy']!='external':parser.error('This session is managed by a built-in strategy.')
        ident=run['id'];path='/training/'+ident
        founder=api('GET','/flies/'+run['spec']['founder_id'])
        folder=args.output/ident;folder.mkdir(parents=True,exist_ok=True)
        print('Session:',ident,flush=True)
        print('Observe in the browser:',base+'/#tab=train&training='+ident,flush=True)
        deadline=time.monotonic()+args.timeout
        while True:
            (folder/'training.json').write_text(json.dumps(run,indent=2),encoding='utf-8')
            print(run['status'],f"{run['evaluations_completed']}/{run['evaluations_total']}",flush=True)
            if run['status'] in {'complete','failed','stopped','paused','pausing'}:break
            if time.monotonic()>deadline:
                raise SystemExit('Observation timed out; use --run '+ident+' to continue the optimizer.')
            if run['control']=='run':
                for slot in run.get('open_slots',[]):
                    generation=run['proposal_generation']
                    candidate=propose(founder,run['members'],generation,slot)
                    proposal={'generation':generation,'slot':slot,'spec':candidate}
                    # No /flies publication: candidates remain in training and do not enqueue Lab work.
                    fly=api('POST',path+'/candidates',json=proposal)
                    (folder/f'proposal-{generation}-{slot}.json').write_text(json.dumps(proposal,indent=2),encoding='utf-8')
                    print('Proposed',generation+1,slot+1,fly['id'],flush=True)
            time.sleep(5)
            run=api('GET',path)
        if args.save_best and run['best_fly_id']:
            fly=api('POST',path+'/save',json={'fly_id':run['best_fly_id']})
            print('Saved evaluated individual:',fly['id'])
        print('Plan, actual scores, lineage and proposals:',folder)
        print('Download replay evidence with scripts/train.py --run',ident)
        if run['status']=='failed':raise SystemExit(run['error'])


if __name__=='__main__':main()
