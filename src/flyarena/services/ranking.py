"""Versioned competition projection. Research trials never enter this policy."""
from ..research import SeasonSpec

POLICY_ID = 'ranking/v1'


def scope(match):
    request = match['request']
    season = SeasonSpec(id=request.get('season_id','genesis-alpha'),runtime_sha256=match['runtime_hash'],
                        scenario_id=request['map_id'],mode=request['mode'])
    return (season.id,season.runtime_sha256,season.scenario_id,season.mode,request.get("bridge_profile", "legacy-v1"))


def rank(flies, matches, *, runtime_hash=None, scenario_id=None, mode=None, season_id='genesis-alpha', bridge_profile=None):
    matches = [m for m in matches if m['status']=='verified' and not m['request'].get('sandbox',False) and
               m['request'].get('sensory_profile', 'odor-only-v1') == 'odor-only-v1' and
               scope(m)[0] == season_id and
               (runtime_hash is None or m['runtime_hash']==runtime_hash) and
               (scenario_id is None or m['request']['map_id']==scenario_id) and
               (mode is None or m['request']['mode']==mode) and
               (bridge_profile is None or m['request'].get('bridge_profile','legacy-v1')==bridge_profile)]
    # Unqualified legacy endpoint projects the most recent compatible session scope.
    selected = scope(max(matches,key=lambda m:m['created'])) if matches else None
    matches = [m for m in matches if scope(m)==selected]
    rows = {f['id']:{'fly':f,'wins':0,'draws':0,'losses':0,'matches':0,'food':0.,'points':0,
                       'ranking_policy':POLICY_ID,'scope':list(selected) if selected else None} for f in flies}
    for match in matches:
        ids, result = match['request']['fly_ids'], match['result']
        if len(ids)!=2 or ids[0]==ids[1]:
            continue
        for slot, ident in enumerate(ids):
            if ident not in rows:
                continue
            row=rows[ident]; row['matches']+=1; row['food']+=result['scores'][slot]
            if result['winner_slot'] is None:
                row['draws']+=1; row['points']+=1
            elif result['winner_slot']==slot:
                row['wins']+=1; row['points']+=3
            else:
                row['losses']+=1
    return sorted(rows.values(),key=lambda r:(-r['points'],-r['food'],r['fly']['id']))


def tournament_projection(matches, fly_ids, *, scope_checked=False):
    """Reuse totals after schedule_report checks every condition and runtime, including duel."""
    standings = {f:{'fly_id':f,'points':0,'played':0,'wins':0,'draws':0,'losses':0} for f in fly_ids}
    sandbox = bool(matches) and all(m['request'].get('sandbox',False) for m in matches)
    sensory_qualified = sandbox or all(m['request'].get('sensory_profile', 'odor-only-v1') == 'odor-only-v1'
                            for m in matches)
    compatible = sensory_qualified and (scope_checked or len({(scope(m), m["request"].get("sandbox",False), m["request"].get("sensory_profile","odor-only-v1")) for m in matches}) <= 1)
    for match in matches if compatible else []:
        if match['status'] != 'verified':
            continue
        for slot, ident in enumerate(match['request']['fly_ids']):
            row=standings[ident];row['played']+=1
            winner=match['result']['winner_slot']
            if winner is None:
                row['draws']+=1;row['points']+=1
            elif winner == slot:
                row['wins']+=1;row['points']+=3
            else:
                row['losses']+=1
    terminal = all(m['status'] in {'verified','failed'} for m in matches)
    status = ('incomplete' if not compatible or any(m['status']=='failed' for m in matches) else 'complete') if terminal else 'running'
    return {'standings':sorted(standings.values(),key=lambda r:(-r['points'],r['fly_id'])),
            'status':status,'ranking_policy':POLICY_ID,'sandbox':sandbox,
            'ranking_error':None if compatible else ('Tournament uses an experimental sensory profile'
                            if not sensory_qualified else
                            'Tournament contains incompatible season/runtime/scenario/mode sessions')}
