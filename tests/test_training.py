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


@pytest.mark.parametrize('sensory', ['odor-only-v1','engineered-kernel-contact-v1'])
def test_training_can_evaluate_ready_research_assets_without_match_qualification(lab, monkeypatch, tmp_path, sensory):
    from fastapi.testclient import TestClient
    from flyarena.api import create_app
    from flyarena.auth import AuthConfig
    from flyarena.bridge import training_profiles, match_profiles
    store, service, user, parent = lab
    monkeypatch.setattr('flyarena.api.Connectome', lambda: service.compiler().graph)
    monkeypatch.setattr('flyarena.api.runtime_manifest', lambda **kw: {'fixture': True, **kw})
    monkeypatch.setattr('flyarena.bridge.profile_manifest', lambda *args: {'ready': True})
    monkeypatch.setattr('flyarena.bridge.QUALIFICATION', tmp_path / 'missing.json')
    assert training_profiles()[1]['ready']
    assert not match_profiles()[1]['ready']
    with TestClient(create_app(with_worker=False, store=store, auth_config=AuthConfig())) as client:
        client.headers['Authorization'] = 'Bearer ' + user['token']
        body = {'founder_id': parent['id'], 'population': 2, 'generations': 1,
                'circuits': ['olfactory'], 'bridge_profile': 'sensorimotor-research-v2', 'sensory_profile': sensory}
        response = client.post('/api/v1/training', json=body)
        assert response.status_code == 202, response.text
        ident = response.json()['id']
        for _ in range(3):
            service.tick()  # Two candidates, then the first queued evaluation.
        match = store.matches()[0]
        assert match['request']['bridge_profile'] == body['bridge_profile']
        assert match['request']['sensory_profile'] == sensory
        assert sensory in training_profiles()[1]['sensory_profiles']
        assert 'engineered-kernel-contact-v1' not in training_profiles()[0]['sensory_profiles']
        # Ordinary matches still follow their independent admission policy.
        response = client.post('/api/v1/matches', json={
            'fly_ids': [parent['id']], 'mode': 'forage', 'bridge_profile': body['bridge_profile']})
        assert response.status_code == 422
        assert 'Bridge unavailable' in response.json()['detail']
        assert client.post('/api/v1/training', json=body | {
            'sensory_profile': 'engineered-contact-support-v1'}).status_code == 422
        rate_spec = FlySpec.model_validate(parent['spec']).model_copy(update={'model_profile': 'malecns-rate-cpu-v1'})
        rate = store.add_fly(user['id'], rate_spec.model_dump(), service.compiler().compile(rate_spec, publish=True, root=store.root))
        assert client.post('/api/v1/training', json=body | {'founder_id': rate['id']}).status_code == 422
        monkeypatch.setattr('flyarena.bridge.profile_manifest', lambda *args: {
            'ready': False, 'reason': 'incompatible readout'})
        response = client.post('/api/v1/training', json=body | {'name': 'Unavailable'})
        assert response.status_code == 422 and 'Training bridge unavailable' in response.json()['detail']
        assert service.get(ident)['spec']['bridge_profile'] == body['bridge_profile']

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
    assert result['evaluation_context']=='fixture-runtime'
    assert 'runtime_hash' not in result
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

@pytest.mark.parametrize('map_id',['orchard','scarcity','terrarium'])
def test_contest_uses_swapped_slots_and_food_margin(lab,map_id):
    store,service,_,parent=lab;run=create(lab,mode='contest',opponent_id=parent['id'],map_id=map_id)
    for _ in range(3):service.tick()
    ident=complete_next(store,[5,2]);service.tick()
    assert store.match(ident)['request']['map_id']==map_id
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

@pytest.mark.parametrize('multi',[False,True])
def test_training_api_authentication_owner_and_full_controls(lab,monkeypatch,multi):
    from fastapi.testclient import TestClient
    from flyarena.api import create_app
    from flyarena.auth import AuthConfig
    store,service,user,parent=lab
    monkeypatch.setattr('flyarena.api.Connectome',lambda:service.compiler().graph)
    monkeypatch.setattr('flyarena.api.runtime_manifest',lambda **kw:{'fixture':True})
    monkeypatch.setattr('flyarena.api.require_bridge',lambda profile:None)
    with TestClient(create_app(with_worker=False,store=store,auth_config=AuthConfig())) as client:
        plan={'founder_id':parent['id'],'population':2,'generations':1,'circuits':['olfactory']}
        if multi:plan.update(evaluation_conditions=CONDITIONS,max_evaluations=4)
        assert client.post('/api/v1/training',json=plan).status_code==401
        client.headers['Authorization']='Bearer '+user['token']
        created=client.post('/api/v1/training',json=plan,headers={'Idempotency-Key':'first'})
        assert created.status_code==202,created.text
        run=created.json();path='/api/v1/training/'+run['id']
        assert run['evaluations_total']==(4 if multi else 2)
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


CONDITIONS=[{'map_id':'orchard','seed':42},{'map_id':'scarcity','seed':7}]

@pytest.mark.parametrize('strategy',['evolution','random_search','external'])
def test_multi_condition_scores_drive_generations_for_every_strategy(lab,strategy):
    store,service,user,parent=lab
    run=create(lab,strategy=strategy,evaluation_conditions=CONDITIONS,max_evaluations=8)
    scores=iter([10,0,6,6,6,6,2,2]);requests=[]
    for _ in range(60):
        service.tick();detail=service.get(run['id'])
        if strategy=='external' and detail['open_slots']:
            generation=detail['proposal_generation'];slot=detail['open_slots'][0]
            ancestor=parent if generation==0 else max((m for m in detail['members'] if m['generation']==0),key=lambda m:m['fitness'])['fly']
            service.propose(run['id'],user['id'],proposal(ancestor,generation,slot))
        if any(m['status']=='queued' for m in store.matches()):
            ident=complete_next(store,[next(scores)]);requests.append(store.match(ident)['request'])
        if service.get(run['id'])['status']=='complete':break
    result=service.get(run['id'])
    assert result['status']=='complete' and result['evaluations_completed']==8
    assert [(r['map_id'],r['seed']) for r in requests]==[('orchard',42),('scarcity',7)]*4
    assert [m['fitness'] for m in result['members']]==[5,6,6,2]
    assert [[c['fitness'] for c in m['condition_results']] for m in result['members']]==[[10,0],[6,6],[6,6],[2,2]]
    expected=parent['id'] if strategy=='random_search' else result['members'][1]['fly_id']
    assert all(m['fly']['spec']['parent_id']==expected for m in result['members'][2:])
    assert all(f['matches']==0 for f in store.leaderboard())


def test_multi_condition_contest_swaps_each_pair_and_waits_for_complete_mean(lab):
    store,service,user,parent=lab
    spec=TrainingSpec(founder_id=parent['id'],opponent_id=parent['id'],mode='contest',population=2,generations=1,
                      evaluation_conditions=CONDITIONS,max_evaluations=8)
    run=service.create(user['id'],spec,'fixture')
    outcomes=iter([[5,2],[4,2],[1,5],[3,7]]*2);requests=[]
    for _ in range(50):
        service.tick()
        if any(m['status']=='queued' for m in store.matches()):
            ident=complete_next(store,next(outcomes));requests.append(store.match(ident)['request'])
            if len(requests)==1:
                service.control(run['id'],user['id'],'pause');service.tick()
                paused=service.get(run['id']);assert paused['status']=='paused'
                assert paused['members'][0]['fitness'] is None
                assert paused['members'][0]['condition_results'][0]['fitness'] is None
                for _ in range(3):service.tick()
                assert service.get(run['id'])['evaluations_started']==1
                service=TrainingService(Store(store.root),service.compiler)
                service.control(run['id'],user['id'],'resume')
            if len(requests)==2:
                partial=service.get(run['id'])['members'][0]
                assert partial['condition_results'][0]['fitness']==.5
                assert partial['condition_results'][1]['fitness'] is None and partial['fitness'] is None
        if service.get(run['id'])['status']=='complete':break
    result=service.get(run['id']);assert result['status']=='complete'
    assert result['evaluations_completed']==8
    assert [m['fitness'] for m in result['members']]==[.25,.25]
    for i in range(0,8,2):assert requests[i]['fly_ids']==list(reversed(requests[i+1]['fly_ids']))
    assert [(r['map_id'],r['seed']) for r in requests]==[('orchard',42)]*2+[('scarcity',7)]*2+[('orchard',42)]*2+[('scarcity',7)]*2


def test_condition_limits_and_historical_idempotency(lab):
    import json
    store,service,user,parent=lab
    plan=TrainingSpec(founder_id=parent['id'],population=2,generations=1,max_evaluations=8)
    historical=plan.model_dump();historical.pop('evaluation_conditions')
    run=service.create(user['id'],plan,'fixture','old-key')
    with store.db() as db:
        db.execute('UPDATE training_keys SET spec=? WHERE key=?',(json.dumps(historical),'old-key'))
        db.execute('UPDATE training_runs SET spec=? WHERE id=?',(json.dumps(historical),run['id']))
    assert service.create(user['id'],historical,'fixture','old-key')['id']==run['id']
    assert service.get(run['id'])['evaluations_total']==2
    assert TrainingSpec(**(historical|{'evaluation_conditions':[{'map_id':'maze','seed':i} for i in range(4)]})).evaluations==8
    for conditions in [[],CONDITIONS*2,[{'map_id':'orchard','seed':i} for i in range(5)],
                       [{'map_id':'unknown','seed':1}],[{'map_id':'maze','seed':-1}],
                       [{'map_id':'maze','seed':1.5}],[{'map_id':'maze','seed':True}]]:
        with pytest.raises(ValueError):TrainingSpec(**(historical|{'evaluation_conditions':conditions}))
    with pytest.raises(ValueError,match='budget'):
        TrainingSpec(**(historical|{'evaluation_conditions':CONDITIONS,'mode':'contest','opponent_id':parent['id'],'max_evaluations':7}))
    with pytest.raises(ValueError,match='another training plan'):
        service.create(user['id'],historical|{'evaluation_conditions':CONDITIONS},'fixture','old-key')


def test_failed_second_condition_preserves_partial_result_without_fitness_or_more_jobs(lab):
    store,service,_,_=lab
    run=create(lab,evaluation_conditions=CONDITIONS,max_evaluations=8)
    for _ in range(3):service.tick()
    complete_next(store,[2]);service.tick()
    ident,lease,_=store.claim();store.finish(ident,lease,None,'second condition failed')
    service.tick();result=service.get(run['id'])
    assert result['status']=='failed' and 'second condition failed' in result['error']
    first=result['members'][0]
    assert first['fitness'] is None
    assert [c['fitness'] for c in first['condition_results']]==[2,None]
    for _ in range(3):service.tick()
    assert service.get(run['id'])['evaluations_started']==2


def test_cem_updates_distribution_from_elites_and_restarts_deterministically(lab):
    store,service,user,parent=lab
    plan=TrainingSpec(founder_id=parent['id'],strategy='cross_entropy',circuits=['olfactory'],
                      population=3,generations=2,max_evaluations=6,duration_seconds=1)
    run=service.create(user['id'],plan,'fixture-runtime')
    scores=iter([1.,4.,2.,4.,3.,5.])
    for _ in range(45):
        service=TrainingService(Store(store.root),service.compiler)
        service.tick()
        if any(m['status']=='queued' for m in store.matches()):complete_next(store,[next(scores)])
        if service.get(run['id'])['status']=='complete':break
    detail=service.get(run['id']);assert detail['status']=='complete'
    first=detail['members'][:3];second=detail['members'][3:]
    assert all(m['fly']['spec']['parent_id']==first[1]['fly_id'] for m in second)
    assert second[0]['fly']['artifact_id']==first[1]['fly']['artifact_id']
    # Independent mathematical check: top half (2/3), log-space mean/std,
    # smoothed alpha=.7 with initial zero mean and .08 standard deviation.
    import numpy as np
    import math
    elite=np.array([math.log(m['fly']['spec']['weight_mutations'][0]['scale']) for m in [first[1],first[2]]])
    mean=.7*elite.mean();sigma=max(.01,.3*.08+.7*elite.std())
    expected=np.random.default_rng(np.random.SeedSequence([42,1,1])).normal(mean,sigma)
    actual=math.log(second[1]['fly']['spec']['weight_mutations'][0]['scale'])
    assert actual==pytest.approx(expected)
    # No hidden optimizer state: a fresh service generates the same candidate.
    again=service.create(user['id'],plan,'fixture-runtime')
    clone=service._candidate(again,plan,1,1,first[1]['fly'],first)
    assert clone['artifact_id']==second[1]['fly']['artifact_id']


def test_completed_showcase_is_opt_in_owner_controlled_and_sanitized(lab,monkeypatch):
    from fastapi.testclient import TestClient
    from flyarena.api import create_app
    from flyarena.auth import AuthConfig
    store,service,user,parent=lab
    run=create(lab)
    monkeypatch.setattr('flyarena.api.Connectome',lambda:service.compiler().graph)
    with TestClient(create_app(with_worker=False,store=store,auth_config=AuthConfig())) as client:
        assert client.get('/api/v1/training-showcase').json()==[]
        path='/api/v1/training/'+run['id']+'/publish'
        assert client.post(path).status_code==401
        client.headers['Authorization']='Bearer '+user['token']
        assert client.post(path).status_code==422
        for _ in range(30):
            service.tick()
            if any(m['status']=='queued' for m in store.matches()):complete_next(store,[1])
            if service.get(run['id'])['status']=='complete':break
        stranger=store.identity('Stranger');client.headers['Authorization']='Bearer '+stranger['token']
        assert client.post(path).status_code==404
        client.headers['Authorization']='Bearer '+user['token']
        assert client.post(path).status_code==200
        client.headers.clear()
        public=client.get('/api/v1/training-showcase/'+run['id']);assert public.status_code==200
        data=public.json();assert data['status']=='complete' and len(data['members'])==4
        assert data['evaluation_context']=='fixture-runtime'
        for private in ['owner','designer','control','error','lease','token']:
            assert '"'+private+'"' not in public.text
        assert client.get('/api/v1/training/'+run['id']).status_code==401
        assert len(client.get('/api/v1/training-showcase').json())==1


def test_bundled_public_gallery_and_replay_artifacts_are_read_only(lab):
    """A deployment bundle can serve published examples without its source DB."""
    from fastapi.testclient import TestClient
    from flyarena.api import create_app
    from flyarena.auth import AuthConfig
    import json
    store,service,_,_=lab
    folder=store.root/'research'/'evolution-gallery-v038';folder.mkdir(parents=True)
    match_id='a'*32
    match={'id':match_id,'status':'verified','progress':1,'attempt':1,
           'request':{'fly_ids':[],'map_id':'orchard','mode':'forage','seed':42,'duration_seconds':1},
           'result':{'scores':[1.0],'winner_slot':None,'outcome':'solo','receipt_sha256':'b'*64}}
    run={'id':'bundled-run','status':'complete','spec':{'strategy':'evolution','generations':1,'population':1},
         'members':[{'generation':0,'slot':0,'fitness':1.0,'fly_id':'c'*32,'fly':{},'matches':[match]}]}
    (folder/'evolution-public.json').write_text(json.dumps(run))
    for artifact,payload in {'scene':{},'frames':[],'events':[],'receipt':{'sha256':'b'*64}}.items():
        (folder/f'{match_id}-{artifact}.json').write_text(json.dumps(payload))
    assert [r['id'] for r in service.showcase()]==['bundled-run']
    assert service.gallery_match(match_id)['status']=='verified'
    with TestClient(create_app(with_worker=False,store=store,auth_config=AuthConfig())) as client:
        assert client.get('/api/v1/training-showcase').json()[0]['id']=='bundled-run'
        assert client.get(f'/api/v1/matches/{match_id}').status_code==200
        assert client.get(f'/api/v1/matches/{match_id}/events').status_code==200


def test_bundled_replay_is_listed_without_source_database(lab):
    """A selected real replay can be served by a source-only deployment."""
    from fastapi.testclient import TestClient
    from flyarena.api import create_app
    from flyarena.auth import AuthConfig
    import json
    store,service,_,_=lab
    folder=store.root/'research'/'replay-gallery-v1';folder.mkdir(parents=True)
    match_id='b'*32
    match={'id':match_id,'status':'verified','progress':1,'attempt':2,
           'request':{'fly_ids':[],'map_id':'orchard','mode':'contest','seed':42,'duration_seconds':30},
           'result':{'scores':[0.0,1.4],'winner_slot':1,'outcome':'win','receipt_sha256':'c'*64}}
    (folder/f'{match_id}-match.json').write_text(json.dumps(match))
    for artifact,payload in {'scene':{'flies':[]},'frames':[],'events':[],'receipt':{'sha256':'c'*64}}.items():
        (folder/f'{match_id}-{artifact}.json').write_text(json.dumps(payload))
    with TestClient(create_app(with_worker=False,store=store,auth_config=AuthConfig())) as client:
        listed=client.get('/api/v1/matches').json()
        assert any(item['id']==match_id for item in listed)
        assert client.get(f'/api/v1/matches/{match_id}').json()['status']=='verified'
        assert client.get(f'/api/v1/matches/{match_id}/scene').json()=={'flies':[]}
        assert client.get(f'/api/v1/matches/{match_id}/receipt').status_code==200


@pytest.mark.parametrize('sensory', ['odor-only-v1', 'engineered-multimodal-v2', 'engineered-touch-response-v1'])
def test_training_keeps_senses_across_generations_conditions_and_mirrored_positions(lab, sensory):
    store, service, _, parent = lab
    run = create(lab, mode='contest', opponent_id=parent['id'], sensory_profile=sensory,
                 evaluation_conditions=[{'map_id':'orchard','seed':42}, {'map_id':'enclosure','seed':43}],
                 max_evaluations=16)
    for _ in range(50):
        service.tick()
        if any(m['status']=='queued' for m in store.matches()):
            complete_next(store, [1, 0])  # Explicit lifecycle fixture, not scientific scores.
        if service.get(run['id'])['status']=='complete':break
    result=service.get(run['id'])
    assert result['status']=='complete'
    matches=[match for member in result['members'] for match in member['matches']]
    assert len(matches)==16
    assert all(match['request']['sensory_profile']==sensory for match in matches)
    assert {m['request']['map_id'] for m in matches}=={'orchard','enclosure'}
    assert result['spec']['sensory_profile']==sensory


def test_training_rejects_incompatible_senses_and_preserves_historical_default(lab):
    _, _, _, parent = lab
    legacy=TrainingSpec(founder_id=parent['id'])
    assert legacy.sensory_profile=='odor-only-v1'
    with pytest.raises(ValueError,match='legacy-v1'):
        TrainingSpec(founder_id=parent['id'], bridge_profile='sensorimotor-research-v2',
                     sensory_profile='engineered-touch-response-v1')
    with pytest.raises(ValueError):
        TrainingSpec(founder_id=parent['id'],sensory_profile='invented')


def test_training_api_binds_selected_senses_to_node_and_queued_match(lab, monkeypatch):
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from flyarena.api import create_app
    from flyarena.auth import AuthConfig
    from flyarena.common import digest
    store, service, user, parent = lab
    monkeypatch.setattr('flyarena.api.Connectome',lambda:service.compiler().graph)
    monkeypatch.setattr('flyarena.api.require_bridge',lambda profile:None)
    calls=[]
    sensory='engineered-touch-response-v1'
    runtime={'platform':'fixture-node','sensory_profile':{'id':sensory}}
    def node_runtime(bridge, senses):
        calls.append((bridge,senses));return runtime
    monkeypatch.setattr('flyarena.services.node.configured_node',lambda:SimpleNamespace(runtime=node_runtime))
    def no_local(**kw):raise AssertionError('Selected node must provide training runtime')
    monkeypatch.setattr('flyarena.api.runtime_manifest',no_local)
    with TestClient(create_app(with_worker=False,store=store,auth_config=AuthConfig())) as client:
        client.headers['Authorization']='Bearer '+user['token']
        payload={'founder_id':parent['id'],'population':2,'generations':1,'circuits':['olfactory'], 'sensory_profile':sensory}
        response=client.post('/api/v1/training',json=payload,headers={'Idempotency-Key':'senses'})
        assert response.status_code==202,response.text
        assert calls==[('legacy-v1',sensory)]
        run=response.json()
        assert run['evaluation_context']==digest(runtime)
        for _ in range(3):service.tick()
        match=next(m for m in store.matches() if m['status']=='queued')
        assert match['request']['sensory_profile']==sensory
        assert match['runtime_hash']==digest(runtime)
        changed={**payload,'sensory_profile':'odor-only-v1'}
        assert client.post('/api/v1/training',json=changed,headers={'Idempotency-Key':'senses'}).status_code==422


def test_behavior_objective_selects_later_feeding_parent_and_retains_components(lab):
    store,service,_,_=lab
    run=create(lab,fitness_objective='sustained-foraging-v1')
    # Explicit fixtures: higher food alone is worse under sustained behavior.
    cases=iter([(10,0,.2),(6,6,1),(6,6,1),(6,3,1)])
    for _ in range(30):
        service.tick()
        if any(m['status']=='queued' for m in store.matches()):
            ident,lease,_=store.claim();food,late,upright=next(cases)
            metric=dict(schema='sustained-foraging-v1',food=food,latter_half_food=late,
                        upright_fraction=upright,fitness=(food+late)*upright)
            store.finish(ident,lease,{'scores':[food],'winner_slot':None,'outcome':'solo',
                                     'receipt_sha256':'fixture','behavior':[metric]})
        if service.get(run['id'])['status']=='complete':break
    result=service.get(run['id'])
    assert result['status']=='complete'
    assert [m['fitness'] for m in result['members']]==[2,12,12,9]
    parent=result['members'][1]
    assert all(m['fly']['spec']['parent_id']==parent['fly_id'] for m in result['members'][2:])
    assert result['members'][0]['matches'][0]['result']['scores']==[10]
    assert parent['matches'][0]['result']['behavior'][0]['latter_half_food']==6


def test_behavior_objective_missing_worker_observations_fails_without_food_fallback(lab):
    store,service,_,_=lab;run=create(lab,fitness_objective='sustained-foraging-v1')
    for _ in range(3):service.tick()
    complete_next(store,[100]);service.tick()
    result=service.get(run['id'])
    assert result['status']=='failed'
    assert result['members'][0]['fitness'] is None
    assert 'complete recorded behavior' in result['error']


def test_behavior_contest_uses_both_participants_and_swapped_positions():
    from flyarena.services.training import condition_results
    plan=TrainingSpec(founder_id='a'*32,opponent_id='b'*32,mode='contest',
                      population=2,generations=1,max_evaluations=4,
                      fitness_objective='sustained-foraging-v1')
    def match(scores):
        return {'status':'verified','result':{'scores':[99,99],
                'behavior':[dict(schema='sustained-foraging-v1',fitness=s) for s in scores]}}
    # Own slot0: 12-3=9; own slot1: 2-4=-2; mean3.5.
    assert condition_results(plan,[match([12,3]),match([4,2])])[0]['fitness']==3.5
    assert condition_results(plan,[match([12,3])])[0]['fitness'] is None


@pytest.mark.parametrize('map_id', ['maze', 'switchback'])
@pytest.mark.parametrize('extra', [False, True])
def test_navigation_training_rejected_only_at_creation(lab, map_id, extra):
    import json
    store, service, user, parent = lab
    changes = {'evaluation_conditions': [{'map_id': map_id, 'seed': 42}]} if extra else {'map_id': map_id}
    spec = TrainingSpec(founder_id=parent['id'], **changes)
    # Historical parsing remains valid, including additional conditions.
    assert TrainingSpec.model_validate_json(spec.model_dump_json()) == spec
    with pytest.raises(ValueError, match='observation only.*#82'):
        service.create(user['id'], spec, 'fixture-runtime')
    run = create(lab)
    historical = run['spec'] | changes
    with store.db() as db:
        db.execute('UPDATE training_runs SET spec=? WHERE id=?', (json.dumps(historical), run['id']))
    assert service.get(run['id'])['spec'] == historical
