from types import SimpleNamespace
import numpy as np
import pytest
from flyarena.compiler import Compiler
from flyarena.contracts import FlySpec, MatchRequest, TournamentRequest
from flyarena.neural import Brain
from flyarena.store import Store


def graph():
    return SimpleNamespace(n=3,e=3,manifest={'sha256':'a'*64},
      counts=np.array([1,2,1]),pre=np.array([0,1,2]),post=np.array([1,2,0],dtype=np.int32),
      indptr=np.array([0,1,2,3],dtype=np.int64),
      groups={'olfactory':np.array([0]),'projection':np.array([0]),'olfactory_left':np.array([0]),'olfactory_right':np.array([1])},
      baseline_weights=lambda:np.array([.275,-.55,.275],dtype=np.float32))


def test_compile_cancellation_roundtrip_and_bounds(tmp_path):
    c=Compiler(graph())
    base=FlySpec(name='base',connectome_sha256='a'*64)
    report=c.compile(base,publish=True,root=tmp_path)
    cancel=base.model_copy(update={'weight_mutations':FlySpec(name='c',connectome_sha256='a'*64,weight_mutations=[{'selector':'olfactory','scale':1.25},{'selector':'projection','scale':.8}]).weight_mutations})
    assert c.compile(cancel)['artifact_id']==report['artifact_id']
    w,_=c.load_weights(report['artifact_id'],tmp_path)
    np.testing.assert_array_equal(w,graph().baseline_weights())
    for change in [{'edge_deltas':[{'edge':3,'log_delta':.01}]},{'weight_mutations':[{'selector':'olfactory','scale':2},{'selector':'projection','scale':2}]},{'edge_deltas':[{'edge':0,'log_delta':.69},{'edge':1,'log_delta':.69}]}]:
        with pytest.raises(ValueError): c.compile(FlySpec(**(base.model_dump()|change)))
    with pytest.raises(ValueError): c.compile(base.model_copy(update={'connectome_sha256':'b'*64}))


def test_neural_chunking_restore_reset_and_delay():
    g=graph(); a,b=Brain(g),Brain(g)
    a.stimulate(1,.3); b.stimulate(1,.3)
    a.advance(800)
    for n in [1,17,82,300,400]: b.advance(n)
    for key,value in a.checkpoint().items(): np.testing.assert_array_equal(value,b.checkpoint()[key])
    state=b.checkpoint(); b.advance(100); expected=b.checkpoint(); b.restore(state); b.advance(100)
    for key,value in expected.items(): np.testing.assert_array_equal(value,b.checkpoint()[key])
    b.reset(); assert b.tick==0 and not b.delay.any() and np.all(b.v==-52)
    # A forced presynaptic spike must arrive exactly 18 ticks later.
    b.v[0]=-44; b.advance(1); assert b.delay[18,1]==pytest.approx(.275)
    b.advance(17); assert b.current[1]==0
    b.advance(1); assert b.current[1]==pytest.approx(.275)


def test_store_fences_idempotency_and_auth(tmp_path):
    s=Store(tmp_path); u=s.identity('tester')
    assert s.authenticate(u['token'])['id']==u['id']
    assert s.authenticate('wrong') is None
    f=s.add_fly(u['id'],{'name':'test','color':'mint'},{'artifact_id':'a'*64})
    req=MatchRequest(fly_ids=[f['id']],mode='forage').model_dump()
    m=s.add_match(u['id'],req,'r',key='once')
    assert s.add_match(u['id'],req,'r',key='once')['id']==m['id']
    with pytest.raises(ValueError): s.add_match(u['id'],req|{'seed':99},'r',key='once')
    ident,old,generation=s.claim(); assert generation==1 and s.claim() is None
    with s.db() as db: db.execute('UPDATE matches SET expires=0 WHERE id=?',(ident,))
    _,new,generation=s.claim(); assert generation==2
    with pytest.raises(RuntimeError): s.finish(ident,old,{'status':'verified'})
    s.heartbeat(ident,new,.5); s.finish(ident,new,{'status':'verified'})
    assert s.match(ident)['status']=='verified'


def test_contracts_reject_unfair_or_nonfinite_input():
    with pytest.raises(ValueError): FlySpec(name='bad',connectome_sha256='a'*64,edge_deltas=[{'edge':0,'log_delta':float('nan')}])
    with pytest.raises(ValueError): MatchRequest(fly_ids=['a'*32,'b'*32],mode='sumo',map_id='maze')
    with pytest.raises(ValueError): TournamentRequest(name='bad',fly_ids=['a'*32,'a'*32])


def test_tournament_atomic_schedule(tmp_path):
    s=Store(tmp_path)
    flies=[s.add_fly('u',{'name':str(i),'color':'mint'},{'artifact_id':str(i)*64})['id'] for i in range(3)]
    spec=TournamentRequest(name='paired',fly_ids=flies).model_dump()
    t=s.add_tournament('u',spec,'r','series')
    assert len(t['matches'])==6
    assert s.add_tournament('u',spec,'r','series')['id']==t['id']
    assert len(s.matches())==6
    pairs=[m['request']['fly_ids'] for m in t['matches']]
    assert all(pair[::-1] in pairs for pair in pairs)
    with pytest.raises(ValueError): s.add_tournament('u',spec|{'seeds':[42,43]},'r')
    assert len(s.matches())==6 and len(s.tournaments())==1


def test_two_flies_have_independent_contact_sensors():
    from flyarena.body import Bodies
    from flyarena.scenarios import scenario
    b=Bodies(scenario('ring',42),2,42)
    ids=b.sim._intern_groundcontactsensorids_by_fly
    assert len(ids)==2 and not set(ids['fly-0'])&set(ids['fly-1'])
    for _ in range(100): b.step(np.zeros((2,2)))
    assert np.isfinite(b.data.qpos).all()


def test_actual_cross_fly_contact_is_not_filtered():
    from flyarena.body import Bodies
    from flyarena.scenarios import scenario
    scene=scenario('ring',42)
    scene['spawns']=[[-1,0,0],[1,0,np.pi]]
    b=Bodies(scene,2,42)
    assert b.contact_between_flies()
    assert b.model.body_contype.any()
    assert all(b.geom_slots.get(int(c.geom1))!=b.geom_slots.get(int(c.geom2)) for c in b.data.contact if int(c.geom1) in b.geom_slots and int(c.geom2) in b.geom_slots)


def test_old_neural_profile_artifact_is_rejected(tmp_path):
    import json
    from flyarena.common import digest,write_json
    c=Compiler(graph());report=c.compile(FlySpec(name='base',connectome_sha256='a'*64),publish=True,root=tmp_path)
    folder=tmp_path/'artifacts'/report['artifact_id']
    manifest=json.loads((folder/'manifest.json').read_text())
    manifest['phenotype']['model']['threshold_mv']=-40
    new_id=digest(manifest['phenotype'])
    write_json(folder/'manifest.json',manifest);folder.rename(folder.parent/new_id)
    with pytest.raises(ValueError,match='neural model'):c.load_weights(new_id,tmp_path)
