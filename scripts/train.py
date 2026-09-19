"""Run a bounded training session through the same API as the web sandbox.

Set ARENA_URL and ARENA_TOKEN (from the web app), then run:
  python scripts/train.py --founder FLY_ID --population 2 --generations 2 --budget 4
Resume observation without creating work:
  python scripts/train.py --run RUN_ID
Pause/resume/stop:
  python scripts/train.py --run RUN_ID --control pause
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time
import uuid

import httpx


def evaluation_condition(value):
    """Argparse type for a bounded map:seed condition, also used by agents."""
    try:
        map_id,seed=value.split(':')
        if map_id not in {'orchard','maze','scarcity','ring','terrarium','enclosure'} or not seed.isascii() or not seed.isdigit():raise ValueError
        number=int(seed)
        if number>2**31-1:raise ValueError
        return {'map_id':map_id,'seed':number}
    except ValueError as exc:
        raise argparse.ArgumentTypeError('Use MAP:SEED, e.g. orchard:42 or scarcity:7, with an integer seed from 0 to 2147483647') from exc


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--founder', help='Starting fly ID; defaults to the canonical reference')
    p.add_argument('--run', help='Observe an existing session instead of starting another')
    p.add_argument('--strategy', choices=['evolution', 'random_search', 'cross_entropy'], default='evolution')
    p.add_argument('--map', choices=['orchard', 'maze', 'scarcity', 'ring', 'terrarium', 'enclosure'], default='orchard')
    p.add_argument('--opponent', help='Fixed opponent; enables mirrored food competition')
    p.add_argument('--circuits', nargs='+', default=['olfactory', 'projection', 'descending'])
    p.add_argument('--population', type=int, default=2)
    p.add_argument('--generations', type=int, default=2)
    p.add_argument('--budget', type=int, default=4)
    p.add_argument('--seconds', type=int, default=1)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--condition', action='append', type=evaluation_condition,
                   help='Evaluation MAP:SEED; repeat up to four times. Overrides --map/--seed for evaluation only.')
    p.add_argument('--key', default=uuid.uuid4().hex, help='Reuse this key to safely retry creation')
    p.add_argument('--control', choices=['pause', 'resume', 'stop'])
    p.add_argument('--save-best', action='store_true')
    p.add_argument('--timeout', type=int, default=3600)
    p.add_argument('--output', type=Path, default=Path('var/training-examples'))
    a = p.parse_args()
    if a.condition and (len(a.condition)>4 or len({(c['map_id'],c['seed']) for c in a.condition})!=len(a.condition)):
        p.error('Provide at most four distinct map/seed conditions.')
    token = os.environ.get('ARENA_TOKEN')
    if not token:
        p.error('Set ARENA_TOKEN to your designer/agent API token. Never commit it.')
    if a.control and not a.run:
        p.error('--control requires --run')
    base = os.environ.get('ARENA_URL', 'http://127.0.0.1:18080').rstrip('/')
    with httpx.Client(base_url=base+'/api/v1', headers={'Authorization': 'Bearer '+token}, timeout=120) as client:
        def api(method, path, **kw):
            return client.request(method, path, **kw).raise_for_status().json()
        if a.run:
            run = api('GET', '/training/'+a.run)
        else:
            flies = api('GET', '/flies')
            founder = a.founder or next(f['id'] for f in flies if f.get('reference_kind') == 'wildtype')
            print('Creation key:', a.key, flush=True)
            run = api('POST', '/training', headers={'Idempotency-Key': a.key}, json={
                'name': 'API '+a.strategy, 'founder_id': founder, 'opponent_id': a.opponent,
                'strategy': a.strategy, 'map_id': a.map, 'mode': 'contest' if a.opponent else 'forage',
                'circuits': a.circuits, 'population': a.population, 'generations': a.generations,
                'max_evaluations': a.budget, 'duration_seconds': a.seconds, 'seed': a.seed,
                'bridge_profile': 'legacy-v1', 'evaluation_conditions': a.condition,
            })
        path = '/training/'+run['id']
        print('Session:', run['id'], flush=True)
        if a.control:
            run = api('POST', path+'/control', json={'action': a.control})
            print('Control:', run['status'], flush=True)
            if a.control != 'resume':
                return
        deadline = time.monotonic()+a.timeout
        while True:
            print(run['status'], f"{run['evaluations_completed']}/{run['evaluations_total']}", flush=True)
            if run['status'] in {'complete', 'failed', 'stopped', 'paused'}:
                break
            if time.monotonic() >= deadline:
                raise SystemExit('Observation timed out; session continues. Use --run '+run['id'])
            time.sleep(5)
            run = api('GET', path)
        folder = a.output/run['id']
        folder.mkdir(parents=True, exist_ok=True)
        (folder/'training.json').write_text(json.dumps(run, indent=2), encoding='utf-8')
        for member in run['members']:
            print('Generation', member['generation']+1, member['fly_id'], 'fitness', member['fitness'])
            for condition in member.get('condition_results',[]):
                print('  Condition',condition['condition'],'fitness',condition['fitness'],
                      f"{condition['evaluations_completed']}/{condition['evaluations_total']}")
            for match in member['matches']:
                if match['status'] != 'verified':
                    continue
                for artifact in ('scene', 'frames', 'events', 'receipt'):
                    data = api('GET', f"/matches/{match['id']}/{artifact}")
                    (folder/f"{match['id']}-{artifact}.json").write_text(json.dumps(data), encoding='utf-8')
        if a.save_best and run['best_fly_id']:
            fly = api('POST', path+'/save', json={'fly_id': run['best_fly_id']})
            print('Saved to library:', fly['id'])
        print('Actual results and neural/behavior replays:', folder)
        if run['status'] == 'failed':
            raise SystemExit(run['error'])


if __name__ == '__main__':
    main()
