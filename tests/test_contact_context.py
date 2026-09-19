"""Food and lateral contact remain distinct all the way into recorded neural input."""
import json
import numpy as np
import pytest
from flyarena.body import Bodies
from flyarena.scenarios import scenario
from flyarena.neural import Brain
from flyarena.rate import RateBrain
from flyarena.experiments.embodied_sensor import EmbodiedSensor, CONTACT_CONTEXT_PROFILE, SUPPORT_CONTACT_PROFILE
from test_embodied_sensor import graph


@pytest.mark.parametrize('brain_type', [Brain, RateBrain])
def test_taste_and_left_right_currents_target_distinct_annotations(brain_type):
    g = graph(); g.groups['gustatory'] = np.array([4])
    encoder = EmbodiedSensor(g, CONTACT_CONTEXT_PROFILE['id'])
    brain = brain_type(g)
    for channel, index in [('taste', 4), ('touch_left', 6), ('touch_right', 7)]:
        record = encoder.apply(brain, .2, .4, **{channel: 1})
        expected = np.array([16,24,0,0,0,0,0,0], dtype=float); expected[index] = 8
        np.testing.assert_allclose(brain.external, expected)
        assert record['values'][channel] == 1
        assert 'touch' not in record['values']
    before = brain.external.copy()
    with pytest.raises(ValueError): encoder.apply(brain, 0, 0, touch=1)
    with pytest.raises(ValueError): encoder.apply(brain, 0, 0, taste=float('nan'))
    np.testing.assert_array_equal(brain.external, before)


def test_unknown_anatomical_side_is_not_assigned_to_left_or_right():
    g = graph(); g.side[6:] = 0
    encoder = EmbodiedSensor(g, CONTACT_CONTEXT_PROFILE['id'])
    assert not len(encoder.groups['touch_left']) and not len(encoder.groups['touch_right'])
    with pytest.raises(ValueError, match='annotated'): encoder.apply(Brain(g), 0, 0, touch_left=1)


def test_real_wall_side_tracks_thorax_rotation_and_excludes_ground_and_food():
    scene = scenario('enclosure',42); scene['spawns'] = [[11.8,0,0]]
    body = Bodies(scene,1,42)
    contacts = body.lateral_environment_contacts(0)
    assert set(sum(contacts.values(),[])) == set(body.environment_contacts(0))
    assert any(contacts.values())
    # Read the same MuJoCo contacts with opposite local lateral basis. A world-axis
    # test would not swap them; do not change physics or manufacture contact points.
    position, rotation = body.pose(0)
    body.pose = lambda slot: (position, rotation @ np.diag([1,-1,-1]))
    mirrored = body.lateral_environment_contacts(0)
    assert mirrored['left'] == contacts['right'] and mirrored['right'] == contacts['left']
    assert mirrored['center'] == contacts['center']
    scene = scenario('orchard',42); scene['obstacles'] = []
    x,y,_ = scene['food'][0]['position']; scene['spawns'] = [[x-.2,y,0]]
    body = Bodies(scene,1,42)
    assert body.food_contacts(0)
    assert body.lateral_environment_contacts(0) == dict(left=[],right=[],center=[])


@pytest.mark.parametrize('profile_id',[CONTACT_CONTEXT_PROFILE['id'],SUPPORT_CONTACT_PROFILE['id']])
@pytest.mark.parametrize('context',['food','depleted-food','wall'])
def test_physics_neural_input_and_recording_keep_food_and_walls_distinct(tmp_path, monkeypatch, context, profile_id):
    from test_replay_parity import tiny_assets
    from flyarena.common import write_json,digest,file_sha
    from flyarena.connectome import Connectome
    from flyarena.compiler import Compiler
    from flyarena.contracts import FlySpec,MatchRequest
    from flyarena.runner import simulate
    from flyarena.judge import verify
    data,var,_ = tiny_assets(tmp_path/'assets');folder=data/'connectome'
    write_json(folder/'neurons.json',[{'id':str(i),'class':'gustatory' if i==0 else 'mechanosensory_tactile'} for i in range(4)])
    manifest=json.loads((folder/'manifest.json').read_text());manifest.pop('sha256')
    manifest['files']['neurons.json']=file_sha(folder/'neurons.json');manifest['sha256']=digest(manifest);write_json(folder/'manifest.json',manifest)
    readout=json.loads((folder/'readout.json').read_text());readout.pop('sha256')
    readout['connectome_sha256']=manifest['sha256'];readout['sha256']=digest(readout);write_json(folder/'readout.json',readout)
    graph=Connectome(data);spec=FlySpec(name='Contact fixture',connectome_sha256=manifest['sha256'])
    report=Compiler(graph).compile(spec,publish=True,root=var)
    fly=dict(id='a'*32,name=spec.name,color=spec.color,artifact_id=report['artifact_id'])
    scene=scenario('enclosure',42)
    if context=='wall':
        scene['spawns']=[[11.8,0,0]]
        scene['food']=[{**f,'position':[100+i*5,100,0]} for i,f in enumerate(scene['food'])]
    else:
        scene['obstacles']=[];x,y,_=scene['food'][0]['position'];scene['spawns']=[[x-.2,y,0]]
        if context=='depleted-food':scene['food']=[{**f,'initial':0} for f in scene['food']]
    monkeypatch.setattr('flyarena.runner.arena_scene',lambda *a:dict(scene));monkeypatch.setattr('flyarena.judge.receipt_scene',lambda *a:dict(scene))
    out=tmp_path/'run';request=MatchRequest(fly_ids=[fly['id']],mode='forage',duration_seconds=1,sensory_profile=profile_id)
    simulate(request,[fly],out,data=data,var=var)
    assert verify(out)['status']=='verified'
    frames=json.loads((out/'frames.json').read_text())
    senses=[f['senses'][0] for f in frames[1:]]
    from flyarena.experiments.embodied_sensor import EmbodiedSensor
    encoder=EmbodiedSensor(graph,profile_id)
    expected={name:[str(int(graph.ids[i])) for i in encoder.groups[name][:6]]
              for name in ['taste','touch_left','touch_right']}
    for frame in frames:
        sample=frame['brain'][0]
        assert sample['sampling']['sensory_groups']==expected
        assert sample['sampling']['count']==len(sample['sampled_nodes'])
        assert set(sum(expected.values(),[]))<={n['id'] for n in sample['sampled_nodes']}
    for frame in frames[1:]:
        for name in expected:
            if len(encoder.groups[name]):
                assert frame['brain'][0]['circuits'][name]==frame['senses'][0]['contact_activity'][name]
    if profile_id == SUPPORT_CONTACT_PROFILE['id']:
        assert all(isinstance(s['contact_support'],list) for s in senses)
    assert all(set(s['contact_activity'])=={'taste','touch_left','touch_right'} for s in senses)
    for s in senses:
        for name in ['taste','touch_left','touch_right']:assert s['neural_input']['values'][name]==s[name]
    if context=='wall':
        assert any(s['touch_left'] or s['touch_right'] for s in senses)
        assert all(s['taste']==0 for s in senses)
    else:
        assert any(s['contact_food'] for s in senses)
        assert all(s['touch_left']==s['touch_right']==0 for s in senses)
        assert any(s['taste'] for s in senses) if context=='food' else all(s['taste']==0 for s in senses)
