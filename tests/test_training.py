"""Exercise complete training lifecycles with tiny genomes and explicit fake scores."""
import pytest
from flyarena.compiler import Compiler
from flyarena.contracts import FlySpec
from flyarena.services.training import TrainingService, TrainingSpec
from flyarena.store import Store
from test_interventions import fixture_graph

@pytest.fixture
def lab(tmp_path):
    store=Store(tmp_path/'var');compiler=Compiler(fixture_graph(tmp_path))
    user=store.identity('Trainer')
    spec=FlySpec(name='Ancestor',connectome_sha256='a'*64)
    parent=store.add_fly(user['id'],spec.model_dump(),compiler.compile(spec,publish=True,root=store.root))
    service=TrainingService(store,lambda:compiler)
    return store,service,user,parent

def create(lab,**kw):
    store,service,user,parent=lab
    plan=TrainingSpec(founder_id=parent['id'],circuits=['olfactory'],population=2,generations=2,duration_seconds=1,**kw)
    return service.create(user['id'],plan,'fixture-runtime')

def complete_next(store,scores):
    claim=store.claim();assert claim
    ident,lease,_=claim
    store.finish(ident,lease,{'scores':scores,'winner_slot':None,'outcome':'solo','receipt_sha256':'fixture'})
    return ident

def test_generation_selection_hidden_candidates_publication_and_reload(lab):
    store,service,user,parent=lab;run=create(lab)
    scores=iter([1.,3.,3.,2.])
    for _ in range(30):
        service.tick()
        queued=[m for m in store.matches() if m['status']=='queued']
        if queued:complete_next(store,[next(scores)])
        if service.get(run['id'])['status']=='complete':break
    result=TrainingService(Store(store.root),service.compiler).get(run['id'])
    assert result['status']=='complete' and result['evaluations_completed']==4
    assert result['baseline_fitness']==1
    assert [m['fitness'] for m in result['members']]==[1,3,3,2]
    first=result['members'][:2];children=result['members'][2:]
    assert all(m['fly']['spec']['parent_id']==first[1]['fly_id'] for m in children)
    assert all(m['fly']['spec']['parent_id']==parent['id'] for m in first)
    assert [f['id'] for f in store.flies()]==[parent['id']]
    assert all(f['matches']==0 for f in store.leaderboard())
    chosen=service.save(run['id'],user['id'],result['best_fly_id'])
    assert chosen['id'] in [f['id'] for f in store.flies()]
    assert all(f['matches']==0 for f in store.leaderboard())
    with pytest.raises(ValueError):service.save(run['id'],'someone-else',chosen['id'])

def test_random_search_keeps_founder_and_mutations_are_reproducible(lab):
    store,service,user,parent=lab;run=create(lab,strategy='random_search')
    for _ in range(30):
        service.tick()
        if any(m['status']=='queued' for m in store.matches()):complete_next(store,[1])
        if service.get(run['id'])['status']=='complete':break
    result=service.get(run['id'])
    assert all(m['fly']['spec']['parent_id']==parent['id'] for m in result['members'])
    assert result['members'][0]['fly']['artifact_id']==parent['artifact_id']
    assert result['members'][1]['fly']['artifact_id']!=parent['artifact_id']
    second=create(lab,strategy='random_search')
    service.tick();service.tick()
    assert [m['fly']['artifact_id'] for m in service.get(second['id'])['members']]==[m['fly']['artifact_id'] for m in result['members'][:2]]

def test_pause_resume_stop_do_not_start_extra_evaluations(lab):
    store,service,user,_=lab;run=create(lab)
    service.tick();service.tick();service.tick()
    assert service.get(run['id'])['evaluations_started']==1
    assert service.control(run['id'],user['id'],'pause')['status']=='pausing'
    complete_next(store,[0]);service.tick()
    paused=service.get(run['id']);assert paused['status']=='paused' and paused['members'][0]['fitness']==0
    for _ in range(3):service.tick()
    assert service.get(run['id'])['evaluations_started']==1
    service.control(run['id'],user['id'],'resume');service.tick()
    assert service.get(run['id'])['evaluations_started']==2
    service.control(run['id'],user['id'],'stop');complete_next(store,[0]);service.tick()
    assert service.get(run['id'])['status']=='stopped'
    with pytest.raises(ValueError):service.control(run['id'],user['id'],'resume')

def test_failed_match_stops_training_without_fabricated_fitness(lab):
    store,service,_,_=lab;run=create(lab)
    service.tick();service.tick();service.tick()
    ident,lease,_=store.claim();store.finish(ident,lease,None,'Simulation failed')
    service.tick();result=service.get(run['id'])
    assert result['status']=='failed' and 'Simulation failed' in result['error']
    assert result['members'][0]['fitness'] is None and result['evaluations_started']==1

def test_contest_uses_swapped_slots_and_food_margin(lab):
    store,service,_,parent=lab;run=create(lab,mode='contest',opponent_id=parent['id'])
    for _ in range(3):service.tick()
    ident=complete_next(store,[5,2]);service.tick()
    first=store.match(ident)['request']['fly_ids']
    queued=next(m for m in store.matches() if m['status']=='queued')
    assert queued['request']['fly_ids']==list(reversed(first))
    complete_next(store,[4,2]);service.tick()
    assert service.get(run['id'])['members'][0]['fitness']==.5

def test_budget_idempotency_owner_and_admission_limits(lab):
    store,service,user,parent=lab
    with pytest.raises(ValueError):create(lab,max_evaluations=3)
    spec=TrainingSpec(founder_id=parent['id'],population=2,generations=1)
    a=service.create(user['id'],spec,'fixture','same')
    assert service.create(user['id'],spec,'fixture','same')['id']==a['id']
    with pytest.raises(ValueError):service.create(user['id'],spec.model_copy(update={'name':'Changed'}),'fixture','same')
    with pytest.raises(ValueError):service.control(a['id'],'wrong-owner','pause')
    service.create(user['id'],spec,'fixture')
    with pytest.raises(ValueError):service.create(user['id'],spec,'fixture')
    with pytest.raises(ValueError):service.save(a['id'],user['id'],parent['id'])

def test_training_api_authentication_owner_and_full_controls(lab,monkeypatch):
    from fastapi.testclient import TestClient
    from flyarena.api import create_app
    from flyarena.auth import AuthConfig
    store,service,user,parent=lab
    monkeypatch.setattr('flyarena.api.Connectome',lambda:service.compiler().graph)
    monkeypatch.setattr('flyarena.api.runtime_manifest',lambda **kw:{'fixture':True})
    monkeypatch.setattr('flyarena.api.require_bridge',lambda profile:None)
    with TestClient(create_app(with_worker=False,store=store,auth_config=AuthConfig())) as client:
        plan={'founder_id':parent['id'],'population':2,'generations':1,'circuits':['olfactory']}
        assert client.post('/api/v1/training',json=plan).status_code==401
        client.headers['Authorization']='Bearer '+user['token']
        created=client.post('/api/v1/training',json=plan,headers={'Idempotency-Key':'first'})
        assert created.status_code==202,created.text
        run=created.json();path='/api/v1/training/'+run['id']
        assert client.post('/api/v1/training',json=plan,headers={'Idempotency-Key':'first'}).json()['id']==run['id']
        assert client.get('/api/v1/training').json()[0]['id']==run['id']
        assert client.post(path+'/control',json={'action':'pause'}).json()['status']=='paused'
        assert client.post(path+'/control',json={'action':'resume'}).status_code==200
        assert client.post(path+'/control',json={'action':{}}).status_code==422
        stranger=store.identity('Other')
        client.headers['Authorization']='Bearer '+stranger['token']
        assert client.get(path).status_code==404
        assert client.post(path+'/control',json={'action':'stop'}).status_code==404
        assert client.post(path+'/save',json={'fly_id':parent['id']}).status_code==404
        assert client.get('/api/v1/training').json()==[]
