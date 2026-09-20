"""Task semantics and observation limits, independent of expensive brain runs."""
import json
from collections import deque
import pytest
from flyarena.contracts import MatchRequest, TournamentRequest
from flyarena.scenarios import arena_scene, RULES
from flyarena.behavior import territory_slot, task_metrics
from flyarena.replay import LONG_POLICY, POLICY, recording_policy, validate_policy
from flyarena.judge import verify
from flyarena.common import write_json
from test_replay import receipt_factory, resign


def test_observation_horizon_does_not_expand_training_or_tournaments():
    assert MatchRequest(fly_ids=['a'*32], mode='forage', map_id='labyrinth', duration_seconds=300, sandbox=True)
    for request in [dict(fly_ids=['a'*32],mode='forage',duration_seconds=301),
                    dict(fly_ids=['a'*32,'b'*32],mode='contest',map_id='labyrinth'),
                    dict(fly_ids=['a'*32,'b'*32],mode='duel',map_id='orchard')]:
        with pytest.raises(ValueError): MatchRequest(**request)
    with pytest.raises(ValueError):
        TournamentRequest(name='bounded series',fly_ids=['a'*32,'b'*32],duration_seconds=180)
    assert recording_policy(30)==POLICY
    assert recording_policy(180)==LONG_POLICY
    validate_policy(LONG_POLICY,RULES)


def test_maze_has_clearance_path_and_no_direct_line():
    scene=arena_scene('labyrinth',42)
    # A one-mm-radius footprint must be able to traverse the whole maze.
    def open_at(x,y):
        return all(abs(x-o['position'][0])>o['size'][0]/2+1 or
                   abs(y-o['position'][1])>o['size'][1]/2+1 for o in scene['obstacles'])
    start=(-11,-10);goal=(10,10);seen={start};queue=deque([start])
    while queue:
        x,y=queue.popleft()
        for dx,dy in [(1,0),(-1,0),(0,1),(0,-1)]:
            nxt=(x+dx,y+dy)
            if nxt not in seen and max(abs(nxt[0]),abs(nxt[1]))<14 and open_at(*nxt):
                seen.add(nxt);queue.append(nxt)
    assert goal in seen
    assert not all(open_at(-11+21*t/100,-10+20*t/100) for t in range(101))


def test_arrival_is_measured_contact_never_zero_for_failure():
    scene=arena_scene('labyrinth',42)
    frames=[{'time':t,'positions':[[0,0,1]]} for t in [0,.05,180]]
    result={'contact_ticks':0,'scores':[0]}
    assert task_metrics(scene,frames,[],result)['arrival_seconds'] is None
    events=[{'type':'food_contact','tick':123450,'slot':0,'food':['food-0']}]
    metric=task_metrics(scene,frames,events,result)
    assert metric['arrival_seconds']==pytest.approx(12.345)
    assert metric['observed_seconds']==180
    assert metric['completed'] is True


def test_territory_requires_exclusive_occupancy_not_a_food_score():
    scene=arena_scene('duel',42)
    assert territory_slot(scene,[[1,0,1],[4,0,1]])==0
    assert territory_slot(scene,[[1,0,1],[-1,0,1]]) is None
    assert territory_slot(scene,[[1,0,4],[-1,0,1]])==1
    assert territory_slot(scene,[[4,0,1],[-4,0,1]]) is None


def test_long_replay_preserves_real_endpoint_and_neural_clock(receipt_factory):
    # Synthetic format test, explicitly not a long biological simulation.
    folder=receipt_factory()
    frames=json.loads((folder/'frames.json').read_text())
    base=frames[0]
    frames=[dict(base,tick=t,time=t*.0001) for t in range(0,1800001,500)]
    write_json(folder/'frames.json',frames)
    receipt=json.loads((folder/'receipt.json').read_text())
    receipt['request']['duration_seconds']=180;receipt['final_tick']=1800000
    receipt['replay_policy']=dict(LONG_POLICY)
    receipt['runtime']['replay_policies']=[POLICY,LONG_POLICY]
    write_json(folder/'receipt.json',receipt)
    scene=json.loads((folder/'scene.json').read_text());scene['replay_policy']=dict(LONG_POLICY);write_json(folder/'scene.json',scene)
    result=json.loads((folder/'result.json').read_text());result['final_tick']=1800000;write_json(folder/'result.json',result)
    import numpy as np
    for name in ['physics.npz','brain-0.npz']:np.savez(folder/name,tick=np.array(1800000),v=np.zeros(1))
    resign(folder)
    assert verify(folder)['final_tick']==1800000
    frames.pop(200);write_json(folder/'frames.json',frames);resign(folder)
    with pytest.raises(ValueError,match='missing ticks'):verify(folder)


def test_duel_judge_reconstructs_territory_winner_from_positions(receipt_factory):
    import numpy as np
    folder=receipt_factory(end=600)
    receipt=json.loads((folder/'receipt.json').read_text())
    receipt['request'].update(map_id='duel',mode='duel',sandbox=True)
    receipt['final_tick']=10000
    old_scene=json.loads((folder/'scene.json').read_text())
    scene=arena_scene('duel',42)
    scene.update(body=old_scene['body'],flies=old_scene['flies'],replay_policy=POLICY)
    frames=[dict(tick=t,time=t*.0001,poses=[[1,0,1,1,0,0,0],[5,0,1,1,0,0,0]],
                 positions=[[1,0,1],[5,0,1]],energy=[100,100],food=[],drives=[[0,0],[0,0]],
                 scores=[(t//500)*.05,0]) for t in range(0,10001,100)]
    events=[dict(type='territory',tick=t,slot=0,amount=.05) for t in range(500,10001,500)]
    result=dict(final_tick=10000,scores=[1.,0.],food_remaining=[],exit_ticks=[None,None],contact_ticks=0)
    for name,value in [('receipt',receipt),('scene',scene),('frames',frames),('events',events),('result',result)]:
        write_json(folder/(name+'.json'),value)
    for name in ['physics.npz','brain-0.npz','brain-1.npz']:np.savez(folder/name,tick=np.array(10000),v=np.zeros(1))
    resign(folder)
    verdict=verify(folder)
    assert verdict['winner_slot']==0
    assert verdict['scores']==[1.,0.]
    assert verdict['task']['control_seconds']==[1.,0.]
    # A scoring claim cannot survive when both contestants occupy the region.
    frames[5]['positions'][1]=[0,0,1];write_json(folder/'frames.json',frames);resign(folder)
    with pytest.raises(ValueError,match='Territory score'):verify(folder)
