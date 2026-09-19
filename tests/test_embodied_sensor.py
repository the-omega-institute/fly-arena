from types import SimpleNamespace
import json
import numpy as np
import pytest

from flyarena.common import digest, file_sha, write_json
from flyarena.experiments.embodied_sensor import EmbodiedSensor, PROFILE
from flyarena.neural import Brain
from flyarena.rate import RateBrain


def graph():
    return SimpleNamespace(n=8, ids=np.arange(100, 108),
        side=np.array([1, -1, 1, -1, 1, -1, 1, -1]),
        groups={'olfactory_left':np.array([0]), 'olfactory_right':np.array([1]),
                'visual':np.array([2,3,4,5]), 'mechanosensory_tactile':np.array([6,7])},
        indptr=np.arange(9,dtype=np.int64), post=np.roll(np.arange(8,dtype=np.int32),-1),
        baseline_weights=lambda:np.zeros(8,dtype=np.float32))


@pytest.mark.parametrize('cls',[Brain,RateBrain])
def test_stimuli_reach_only_declared_groups_and_change_neural_state(cls):
    g=graph(); encoder=EmbodiedSensor(g); baseline=cls(g); subject=cls(g)
    baseline.stimulate(.2,.4)
    record=encoder.apply(subject,.2,.4,.7,.1,.5)
    np.testing.assert_allclose(subject.external,[16,24,.07,.01,.07,.01,.05,.05])
    assert record['group_manifest_sha256']==digest(encoder.manifest)
    baseline.advance(1000);subject.advance(1000)
    np.testing.assert_array_equal(subject.rates[:2],baseline.rates[:2])
    # The production gains are intentionally subthreshold on this tiny
    # fixture.  Verify the declared groups received the input; do not turn
    # an implementation gain into a fake requirement for spikes.
    assert subject.external[[2,4,6,7]].min()>0
    assert not baseline.external[2:].any()
    duplicate=cls(g);encoder.apply(duplicate,.2,.4,.7,.1,.5);duplicate.advance(1000)
    for key,value in subject.checkpoint().items():
        np.testing.assert_array_equal(value,duplicate.checkpoint()[key])


@pytest.mark.parametrize('cls',[Brain,RateBrain])
def test_zero_extra_input_preserves_legacy_full_state(cls):
    g=graph();g.groups['visual']=np.arange(8)  # Deliberately overlapping fixture.
    subject,baseline=cls(g),cls(g);encoder=EmbodiedSensor(g)
    for left,right in [(0,0),(.3,.6),(1,0),(0,1)]:
        encoder.apply(subject,left,right);baseline.stimulate(left,right)
        subject.advance(100);baseline.advance(100)
        for key,value in subject.checkpoint().items():
            np.testing.assert_array_equal(value,baseline.checkpoint()[key])


def test_missing_annotations_never_invent_laterality_or_tactile_targets():
    g=graph();g.side[:]=0;del g.groups['mechanosensory_tactile']
    g.groups['mechanosensory']=np.array([6,7])
    subject=Brain(g);subject.stimulate(.5,.5);before=subject.external.copy()
    encoder=EmbodiedSensor(g)
    for inputs in [(0,0,1,0,0),(0,0,0,0,1),(0,0,float('nan'),0,0)]:
        with pytest.raises(ValueError):encoder.apply(subject,*inputs)
        np.testing.assert_array_equal(subject.external,before)


def test_metadata_requires_matching_canonical_id_order(tmp_path):
    g=graph();g.path=tmp_path
    rows=[{'id':str(i),'class':'mechanosensory_tactile'} for i in reversed(g.ids)]
    write_json(tmp_path/'neurons.json',rows)
    g.manifest={'files':{'neurons.json':file_sha(tmp_path/'neurons.json')}}
    with pytest.raises(ValueError,match='canonical neuron IDs'):EmbodiedSensor(g)


@pytest.mark.integration
def test_full_connectome_uses_official_tactile_and_side_annotations():
    from flyarena.connectome import Connectome
    g=Connectome();encoder=EmbodiedSensor(g)
    assert len(encoder.groups['touch'])==2558
    for name,sign in [('visual_left',1),('visual_right',-1)]:
        assert len(encoder.groups[name])>0
        assert np.all(g.side[encoder.groups[name]]==sign)


def test_real_physics_records_inputs_and_encoder_manifest(tmp_path):
    from test_replay_parity import tiny_assets
    from flyarena.connectome import Connectome
    from flyarena.compiler import Compiler
    from flyarena.contracts import FlySpec,MatchRequest
    from flyarena.runner import simulate
    from flyarena.judge import verify
    data,var,_=tiny_assets(tmp_path/'assets');folder=data/'connectome'
    write_json(folder/'neurons.json',[{'id':str(i),'class':'mechanosensory_tactile'} for i in range(4)])
    manifest=json.loads((folder/'manifest.json').read_text())
    manifest.pop('sha256');manifest['files']['neurons.json']=file_sha(folder/'neurons.json')
    manifest['sha256']=digest(manifest);write_json(folder/'manifest.json',manifest)
    readout=json.loads((folder/'readout.json').read_text());readout.pop('sha256')
    readout['connectome_sha256']=manifest['sha256'];readout['sha256']=digest(readout)
    write_json(folder/'readout.json',readout)
    graph=Connectome(data);artifact=Compiler(graph).compile(
        FlySpec(name='fixture',connectome_sha256=manifest['sha256']),publish=True,root=var)
    fly=dict(id='a'*32,name='fixture',color='mint',artifact_id=artifact['artifact_id'])
    request=MatchRequest(fly_ids=[fly['id']],mode='forage',duration_seconds=1,sensory_profile=PROFILE['id'])
    out=tmp_path/'run';receipt=simulate(request,[fly],out,data=data,var=var)
    assert verify(out)['status']=='verified'
    scene=json.loads((out/'scene.json').read_text());frames=json.loads((out/'frames.json').read_text())
    result=json.loads((out/'result.json').read_text())
    events=json.loads((out/'events.json').read_text())
    assert result['food_contact_ticks']==[[e['tick'] for e in events if e['type']=='food_contact' and e['slot']==0]]
    assert result['intake_ticks']==[[e['tick'] for e in events if e['type']=='intake' and e['slot']==0]]
    assert scene['sensory_encoder']==EmbodiedSensor(graph).manifest
    assert receipt['runtime']['sensory_profile']==PROFILE
    for frame in frames[1:]:
        sense=frame['senses'][0];encoded=sense['neural_input']
        assert encoded['group_manifest_sha256']==digest(scene['sensory_encoder'])
        assert encoded['values']['visual_left']==sense['visual'][0]
        assert encoded['values']['touch']==sense['touch']
    assert any(f['senses'][0]['visual'][0]>0 for f in frames)


def test_experimental_results_do_not_change_public_ranking():
    from flyarena.services.ranking import rank,tournament_projection
    ids=['a'*32,'b'*32];flies=[{'id':i} for i in ids]
    match={'status':'verified','runtime_hash':'fixture','created':1,
           'request':{'fly_ids':ids,'map_id':'orchard','mode':'contest','sensory_profile':PROFILE['id']},
           'result':{'scores':[20,0],'winner_slot':0}}
    assert all(r['matches']==0 for r in rank(flies,[match]))
    assert all(r['played']==0 for r in tournament_projection([match],ids)['standings'])


def test_research_bridge_cannot_silently_inherit_experimental_input():
    from flyarena.contracts import MatchRequest
    with pytest.raises(ValueError,match='legacy-v1 only'):
        MatchRequest(fly_ids=['a'*32],mode='forage',bridge_profile='sensorimotor-research-v2',sensory_profile=PROFILE['id'])
