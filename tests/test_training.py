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


def proposal(parent,generation,slot,scale=1.1):
    return {'generation':generation,'slot':slot,'spec':parent['spec'] | {
        'name':f'Custom G{generation+1}.{slot+1}', 'parent_id':parent['id'],
        'weight_mutations':[{'selector':'olfactory','scale':scale}],
        'neuron_parameters':{'tau_scale':1.03,'threshold_shift_mv':0},
    }}


def test_external_strategy_chooses_its_own_parents_and_preserves_training_boundaries(lab):
    store,service,user,parent=lab;run=create(lab,strategy='external')
    detail=service.get(run['id'])
    assert detail['proposal_generation']==0 and detail['open_slots']==[1]
    first=service.propose(run['id'],user['id'],proposal(parent,0,1))
    # A client can submit before the worker prepares its baseline.
    service.tick();service.tick();complete_next(store,[1]);service.tick()
    complete_next(store,[4]);service.tick()
    waiting=service.get(run['id'])
    assert waiting['status']=='awaiting_candidates' and waiting['open_slots']==[0,1]
    assert waiting['proposal_generation']==1 and waiting['evaluations_completed']==2
    # The optimizer deliberately branches from both founder and an evaluated descendant.
    second=service.propose(run['id'],user['id'],proposal(parent,1,0,1.05))
    third=service.propose(run['id'],user['id'],proposal(first,1,1,1.12))
    service.tick();complete_next(store,[3]);service.tick();complete_next(store,[5]);service.tick()
    result=service.get(run['id'])
    assert result['status']=='complete' and result['evaluations_completed']==4
    assert result['open_slots']==[] and result['proposal_generation'] is None
    assert result['baseline_fitness']==1 and result['best_fly_id']==third['id']
    assert second['spec']['parent_id']==parent['id'] and third['spec']['parent_id']==first['id']
    assert {f['id'] for f in store.flies()}=={parent['id']}
    assert not any(r['matches'] for r in store.leaderboard())
    assert all(m['fly']['experiment_id'] is None for m in result['members'])
    assert first['submission_channel']=='api' and first['reference_kind']=='user'
    service.save(run['id'],user['id'],third['id'])
    assert {f['id'] for f in store.flies()}=={parent['id'],third['id']}


def test_external_baseline_runs_while_waiting_for_program_and_survives_restart(lab):
    store,service,user,parent=lab;run=create(lab,strategy='external')
    service.tick();service.tick();complete_next(store,[0]);service.tick()
    detail=TrainingService(Store(store.root),service.compiler).get(run['id'])
    assert detail['status']=='awaiting_candidates' and detail['evaluations_started']==1
    service.control(run['id'],user['id'],'pause')
    child=service.propose(run['id'],user['id'],proposal(parent,0,1))
    service.tick();assert service.get(run['id'])['evaluations_started']==1
    assert service.get(run['id'])['status']=='paused'
    service.control(run['id'],user['id'],'resume');service.tick()
    assert service.get(run['id'])['evaluations_started']==2
    assert service.propose(run['id'],user['id'],proposal(parent,0,1))['id']==child['id']
    with pytest.raises(ValueError,match='different candidate'):
        service.propose(run['id'],user['id'],proposal(parent,0,1,1.15))


def test_external_admission_rejects_wrong_session_owner_position_parent_and_stopped_work(lab):
    store,service,user,parent=lab;run=create(lab,strategy='external')
    with pytest.raises(ValueError,match='not found'):
        service.propose(run['id'],'other',proposal(parent,0,1))
    for generation,slot in [(0,0),(0,2),(1,0)]:
        with pytest.raises(ValueError,match='open slot'):
            service.propose(run['id'],user['id'],proposal(parent,generation,slot))
    stranger=proposal(parent,0,1);stranger['spec']['parent_id']='b'*32
    with pytest.raises(ValueError,match='Parent must'):
        service.propose(run['id'],user['id'],stranger)
    builtin=create(lab)
    with pytest.raises(ValueError,match='external strategy'):
        service.propose(builtin['id'],user['id'],proposal(parent,0,1))
    service.control(run['id'],user['id'],'stop')
    with pytest.raises(ValueError,match='terminal'):
        service.propose(run['id'],user['id'],proposal(parent,0,1))


def test_external_stop_during_compilation_cannot_admit_a_candidate(lab,monkeypatch):
    store,service,user,parent=lab;run=create(lab,strategy='external')
    compiler=service.compiler();original=compiler.compile
    def stop_then_compile(*args,**kwargs):
        service.control(run['id'],user['id'],'stop')
        return original(*args,**kwargs)
    monkeypatch.setattr(compiler,'compile',stop_then_compile)
    with pytest.raises(ValueError,match='terminal'):
        service.propose(run['id'],user['id'],proposal(parent,0,1))
    assert service.get(run['id'])['members']==[]


def test_external_api_owner_schema_and_identical_retry(lab,monkeypatch):
    from fastapi.testclient import TestClient
    from flyarena.api import create_app
    from flyarena.auth import AuthConfig
    store,service,user,parent=lab;run=create(lab,strategy='external')
    monkeypatch.setattr('flyarena.api.Connectome',lambda:service.compiler().graph)
    with TestClient(create_app(with_worker=False,store=store,auth_config=AuthConfig())) as client:
        path='/api/v1/training/'+run['id']+'/candidates';body=proposal(parent,0,1)
        assert client.post(path,json=body).status_code==401
        other=store.identity('Other');client.headers['Authorization']='Bearer '+other['token']
        assert client.post(path,json=body).status_code==404
        client.headers['Authorization']='Bearer '+user['token']
        first=client.post(path,json=body);assert first.status_code==201,first.text
        assert client.post(path,json=body).json()['id']==first.json()['id']
        assert client.post(path,json=body | {'slot':1.2}).status_code==422
        assert client.post(path,json=body | {'spec':body['spec'] | {'plasticity':'stdp'}}).status_code==422
        assert client.post(path,json=body | {'spec':body['spec'] | {'weight_mutations':[{'selector':'olfactory','scale':100}]}}).status_code==422


def test_retained_baseline_preserves_founder_spec_and_artifact_exactly(lab):
    store,service,user,parent=lab
    raw=parent['spec'] | {'name':'Repeated edits','weight_mutations':[{'selector':'olfactory','scale':1.02},{'selector':'olfactory','scale':1.03}]}
    spec=FlySpec.model_validate(raw)
    founder=store.add_fly(user['id'],raw,service.compiler().compile(spec,publish=True,root=store.root))
    plan=TrainingSpec(founder_id=founder['id'],population=2,generations=1,strategy='external')
    run=service.create(user['id'],plan,'fixture')
    service.tick();baseline=service.get(run['id'])['members'][0]['fly']
    assert baseline['artifact_id']==founder['artifact_id']
    assert baseline['spec']['weight_mutations']==founder['spec']['weight_mutations']


def test_external_registered_agent_provenance_cannot_be_claimed_in_spec(lab,monkeypatch):
    import time
    from fastapi.testclient import TestClient
    from flyarena.api import create_app
    from flyarena.auth import AuthConfig,hashed
    store,service,user,parent=lab;run=create(lab,strategy='external')
    monkeypatch.setattr('flyarena.api.Connectome',lambda:service.compiler().graph)
    app=create_app(with_worker=False,store=store,auth_config=AuthConfig())
    with store.db() as db:
        db.execute('INSERT INTO agent_tokens VALUES(?,?,?,?,?)',('registered-agent',user['id'],hashed('test-agent-token'),time.time()+60,time.time()))
    with TestClient(app) as client:
        client.headers['Authorization']='Bearer test-agent-token'
        path='/api/v1/training/'+run['id']+'/candidates';body=proposal(parent,0,1)
        fake=body | {'spec':body['spec'] | {'reference_kind':'official'}}
        assert client.post(path,json=fake).status_code==422
        result=client.post(path,json=body)
        assert result.status_code==201,result.text
        assert result.json()['reference_kind']=='ai' and result.json()['submission_channel']=='api'
