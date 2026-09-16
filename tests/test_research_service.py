"""Service fixtures are deterministic fake probes, NOT biological evidence."""
import json
from types import SimpleNamespace
import numpy as np
import pytest
from fastapi.testclient import TestClient
from flyarena.api import create_app
from flyarena.auth import AuthConfig
from flyarena.common import canonical, digest, file_sha, write_json
from flyarena.compiler import Compiler
from flyarena.contracts import FlySpec
from flyarena.research import ConditionSpec, ExperimentSpec, PhenotypeReport, compare_reports, condition_key, run_key
from flyarena.services.ports import Capability
from flyarena.services.research_service import ResearchService
from flyarena.services.experiments import ExperimentRepository
from flyarena.store import Store
from test_interventions import fixture_graph


class FixtureProbes:
    profile={'id':'fixture-not-biological','ready':True,'hashes':{'fixture':'a'*64},
        'backend_id':'fixture','model_id':'malecns-lif-cpu-v1','sensor_id':'fixture','readout_id':'fixture',
        'embodiment_id':'fixture','capabilities':['fixture']}
    def probe_catalog(self):
        return [{'id':'gradient-v2','scenario':{'geometry_id':'fixture','stimulus_id':'fixture','task_id':'fixture'},'capabilities':['fixture']}]
    def profile_manifest(self,**kwargs):
        return self.profile.copy()
    def runtime_closure(self):
        return {'fixture':'not-biological-evidence-v1'}
    def make_scene(self,probe,seed):
        from flyarena.experiments.probes import make_scene
        return make_scene(probe, seed)


class FixtureExecutor:
    def __init__(self,probes):
        self.probes=probes;self.calls=[];self.failure=None
    def descriptor(self):
        return Capability('fake-unit-test-only',True,('whole-trial','fixture'))
    def execute(self,fly,probe_id,seed,duration_seconds,output):
        self.calls.append((fly['id'],seed,output))
        if self.failure=='raise' and len(self.calls)%3==0:
            raise RuntimeError('Deliberate fixture failure')
        output.mkdir(parents=True)
        conditions={'profile':self.probes.profile_manifest(),'runtime':self.probes.runtime_closure(),
            'scene':self.probes.make_scene(probe_id,seed),'seed':seed,'duration_seconds':duration_seconds,
            'probe_id':probe_id,'ablation':None,'stimulus':'normal','decoder_version':'v2'}
        if self.failure=='mismatch': conditions['stimulus']='wrong'
        offset=0 if fly['reference_kind']=='wildtype' else 1
        evidence={'schema_version':'probe-report/v2','fly_id':fly['id'],'artifact_id':fly['artifact_id'],
            'condition_key':digest(conditions),'probe_id':probe_id,'seed':seed,'duration_seconds':duration_seconds,
            'trajectory':[{'time':0.,'x':0.,'y':0.,'yaw':0.},{'time':float(duration_seconds),'x':float(offset),'y':0.,'yaw':0.}],
            'metrics':{'path_length_mm':float(offset),'food_latency_seconds':None},
            'scene':conditions['scene'], 'neural_trace':[{'time':0.,'drive_left':0.,'drive_right':0.}], 'profile':self.probes.profile_manifest()}
        write_json(output/'evidence.json',evidence)
        receipt={'conditions':conditions,'subject':{'fly_id':fly['id'],'artifact_id':fly['artifact_id']},
            'files':{'evidence.json':file_sha(output/'evidence.json')}}
        receipt['sha256']=digest(receipt);write_json(output/'receipt.json',receipt)
        return evidence|{'status':'partial' if self.failure=='partial' else 'complete','receipt_sha256':receipt['sha256']}


@pytest.fixture
def lab(tmp_path,monkeypatch):
    g=fixture_graph(tmp_path);c=Compiler(g);s=Store(tmp_path/'var')
    probes=FixtureProbes();executor=FixtureExecutor(probes)
    service=ResearchService(s,lambda:c,probes=probes,executor=executor)
    user=s.identity('Fixture designer')
    spec=FlySpec(name='Design',connectome_sha256='a'*64,edge_deltas=[{'edge':0,'log_delta':.01}])
    fly=s.add_fly(user['id'],spec.model_dump(),c.compile(spec,publish=True,root=s.root))
    monkeypatch.setattr('flyarena.api.Connectome',lambda:g)
    app=create_app(with_worker=False,store=s,auth_config=AuthConfig(),research_service=service)
    client=TestClient(app);client.headers['Authorization']='Bearer '+user['token']
    return SimpleNamespace(store=s,service=service,executor=executor,probes=probes,user=user,fly=fly,client=client,compiler=c)


def test_request_queue_independent_comparison_and_durable_reload(lab):
    response=lab.client.post('/api/v1/experiments',json={'fly_id':lab.fly['id'],'seeds':[42,43]},headers={'Idempotency-Key':'run'})
    assert response.status_code==202,response.text
    experiment=response.json();assert experiment['status']=='queued' and lab.executor.calls==[]
    assert [s['role'] for s in experiment['subjects']]==['wildtype','official','design']
    assert len({s['fly_id'] for s in experiment['subjects']})==3
    claim=lab.service.repository.claim();result=lab.service.execute_claim(claim)
    assert result['status']=='complete',result['error']
    assert len(lab.executor.calls)==6 and len(result['reports'])==6
    assert len(result['comparison']['paired'])==4
    assert all(p['deltas']['food_latency_seconds'] is None for p in result['comparison']['paired'])
    assert result['comparison']['paired'][0]['trajectory_divergence_mm']==pytest.approx(.5)
    reload=ExperimentRepository(Store(lab.store.root)).get(experiment['id'])
    assert reload==result
    assert lab.client.get('/api/v1/experiments/'+experiment['id']).json()['status']=='complete'
    assert lab.client.get('/api/v1/experiments').json()[0]['id']==experiment['id']
    assert lab.client.get('/api/v1/experiments/'+'f'*32).status_code==404
    assert lab.store.matches()==[] and all(r['matches']==0 for r in lab.store.leaderboard())
    replay=lab.client.post('/api/v1/experiments',json={'fly_id':lab.fly['id'],'seeds':[42,43]},headers={'Idempotency-Key':'run'})
    assert replay.json()['id']==experiment['id']
    assert lab.client.post('/api/v1/experiments',json={'fly_id':lab.fly['id'],'seeds':[44]},headers={'Idempotency-Key':'run'}).status_code==422


def test_auto_save_schedules_exact_one_and_reports_errors(lab):
    response=lab.client.post('/api/v1/flies',json={'name':'Saved','connectome_sha256':'a'*64})
    assert response.status_code==201,response.text
    fly=response.json();assert fly['experiment_status']=='queued' and fly['submission_channel']=='api'
    assert fly['reference_kind']=='user' and fly['release_id'] is None
    auto=lab.service.repository.get(fly['experiment_id'])
    assert auto['spec']=={'fly_id':fly['id'],'probe_id':'gradient-v2','seeds':[42],'duration_seconds':3}
    assert lab.service.schedule_saved(fly)['experiment_id']==fly['experiment_id']
    assert len(lab.service.repository.list())==1
    lab.probes.profile=lab.probes.profile|{'ready':False}
    failed=lab.client.post('/api/v1/flies',json={'name':'Unavailable','connectome_sha256':'a'*64}).json()
    assert failed['experiment_status']=='error' and failed['experiment_id'] is None
    assert 'unavailable' in failed['experiment_error']


@pytest.mark.parametrize('field,value',[('provenance',{'kind':'official'}),('scientific_version','arbitrary'),
    ('reference_kind','official'),('release_id','forged'),('submission_channel','seed')])
def test_public_provenance_spoof_rejected(lab,field,value):
    response=lab.client.post('/api/v1/flies',json={'name':'Wild Type / 原型','connectome_sha256':'a'*64,field:value})
    assert response.status_code==422
    with pytest.raises(ValueError,match='server-owned'):
        lab.store.add_fly('arena',{'name':'Spoof','color':'mint',field:value},{'artifact_id':'a'*64})


def test_reference_names_and_arena_owner_do_not_attest(lab):
    spec=FlySpec(name='Nectar / 花蜜',connectome_sha256='a'*64)
    spoof=lab.store.add_fly('arena',spec.model_dump(),lab.compiler.compile(spec,publish=True,root=lab.store.root))
    assert spoof['reference_kind']=='user'
    refs=lab.service.references()
    assert refs['official']['id'] != spoof['id'] and refs['official']['reference_kind']=='official'
    assert refs['wildtype']['reference_kind']=='wildtype'
    clone=lab.store.add_fly(lab.user['id'],refs['official']['spec'],refs['official']['report'])
    assert clone['artifact_id']==refs['official']['artifact_id'] and clone['reference_kind']=='user'
    again=ResearchService(lab.store,lambda:lab.compiler,probes=lab.probes,executor=lab.executor).references()
    assert again['official']['id']==refs['official']['id']
    assert lab.client.get('/api/v1/research/catalog').json()['references']['official']['id']==refs['official']['id']


@pytest.mark.parametrize('failure',['raise','partial','mismatch'])
def test_failed_partial_mismatch_are_terminal_without_zero_comparison(lab,failure):
    lab.executor.failure=failure
    exp=lab.service.admit(lab.user['id'],{'fly_id':lab.fly['id']})
    result=lab.service.execute_claim(lab.service.repository.claim())
    assert result['status']=='failed' and result['error'] and result['comparison'] is None
    assert len(result['reports'])>=1
    assert result['id']==exp['id']


def test_cached_reference_full_condition_artifact_and_receipt(lab):
    def run(seed=42):
        lab.service.admit(lab.user['id'],{'fly_id':lab.fly['id'],'seeds':[seed]})
        return lab.service.execute_claim(lab.service.repository.claim())
    assert run()['status']=='complete';assert len(lab.executor.calls)==3
    assert run()['status']=='complete';assert len(lab.executor.calls)==4  # design is independently rerun
    assert run(43)['status']=='complete';assert len(lab.executor.calls)==7
    _,_,folder=lab.executor.calls[0]
    (folder/'evidence.json').write_text('{}')
    assert run()['status']=='complete';assert len(lab.executor.calls)==9  # corrupt WT cache reruns


def test_generation_fencing_quota_and_changed_conditions(lab):
    exp=lab.service.admit(lab.user['id'],{'fly_id':lab.fly['id']})
    repo=lab.service.repository
    ident,old,generation=repo.claim();assert generation==1 and repo.claim() is None
    with lab.store.db() as db:db.execute('UPDATE experiments SET expires=0 WHERE id=?',(ident,))
    _,new,generation=repo.claim();assert generation==2
    with pytest.raises(RuntimeError):repo.finish(ident,old,1,[],{})
    with pytest.raises(RuntimeError):repo.heartbeat(ident,old,1)
    lab.probes.profile=lab.probes.profile|{'reason':'changed fixture conditions'}
    assert lab.service.execute_claim((ident,new,generation))['status']=='failed'
    for _ in range(12):lab.service.admit(lab.user['id'],{'fly_id':lab.fly['id']})
    with pytest.raises(ValueError,match='quota'):lab.service.admit(lab.user['id'],{'fly_id':lab.fly['id']})


def test_owner_unknown_and_strict_request_validation(lab):
    assert lab.client.post('/api/v1/experiments',json={'fly_id':lab.fly['id'],'subjects':[]}).status_code==422
    assert lab.client.post('/api/v1/experiments',json={'fly_id':lab.fly['id'],'probe_id':'invented'}).status_code==422
    for seeds in [[-1],[42,42],[2**31],[]]:
        assert lab.client.post('/api/v1/experiments',json={'fly_id':lab.fly['id'],'seeds':seeds}).status_code==422
    other=lab.store.identity('other')
    assert lab.client.post('/api/v1/experiments',json={'fly_id':lab.fly['id']},headers={'Authorization':'Bearer '+other['token']}).status_code==422


def test_condition_and_run_identity_are_separate(lab):
    exp=lab.service.admit(lab.user['id'],{'fly_id':lab.fly['id']})
    condition=ConditionSpec.model_validate(exp['conditions'][0])
    assert 'fly_id' not in condition.model_dump()
    assert run_key(condition,'a'*64)!=run_key(condition,'b'*64)
    assert condition_key(condition)!=condition_key(condition.model_copy(update={'duration_seconds':4}))
    assert condition_key(condition)!=condition_key(condition.model_copy(update={'runtime':{'reason':'changed fixture conditions'}}))


def test_comparison_rejects_duplicate_partial_horizons_and_preserves_null(lab):
    lab.service.admit(lab.user['id'],{'fly_id':lab.fly['id']})
    result=lab.service.execute_claim(lab.service.repository.claim());reports=result['reports']
    assert compare_reports(reports,result['subjects']).paired[0].deltas['food_latency_seconds'] is None
    for bad in [reports[:2],[reports[0],reports[0],reports[2]], [reports[0]|{'status':'partial'},*reports[1:]],
                [reports[0]|{'condition_key':'f'*64},*reports[1:]]]:
        with pytest.raises(ValueError):compare_reports(bad,result['subjects'])
    shortened=json.loads(json.dumps(reports));shortened[1]['trajectory'][-1]['time']=2
    with pytest.raises(ValueError,match='horizon'):compare_reports(shortened,result['subjects'])
    nan=json.loads(json.dumps(reports[0]));nan['metrics']['bad']=float('nan')
    with pytest.raises(ValueError):PhenotypeReport.model_validate(nan)

# Reuse the existing offline RSA/OIDC fixture without changing its tests or behavior.
from test_auth import oidc


def test_session_and_registered_agent_provenance_derive_authenticated_channel(oidc,tmp_path,monkeypatch):
    client,store,config,state,begin,finish,provider=oidc
    graph=fixture_graph(tmp_path)
    monkeypatch.setattr('flyarena.api.Connectome',lambda:graph)
    # Keep this auth test independent of the scientific worker's real profile readiness.
    client.app.state.research.schedule_saved=lambda fly:fly
    begin();finish()
    session=client.get('/api/v1/auth/session').json()
    csrf={'Origin':config.origin,'X-Arena-CSRF':session['csrf_token']}
    body={'name':'Channel test','connectome_sha256':'a'*64}
    browser=client.post('/api/v1/flies',json=body,headers=csrf)
    assert browser.status_code==201,browser.text
    assert browser.json()['submission_channel']=='web' and browser.json()['reference_kind']=='user'
    token=client.post('/api/v1/auth/agent-tokens',headers=csrf).json()['token']
    agent=client.post('/api/v1/flies',json=body,headers={'Authorization':'Bearer '+token,'X-Arena-Submission-Channel':'web'})
    assert agent.status_code==201,agent.text
    assert agent.json()['submission_channel']=='api' and agent.json()['reference_kind']=='ai'
    assert agent.json()['owner']==browser.json()['owner']==session['user']['id']
    assert agent.json()['release_id'] is None


def test_receipt_tamper_and_false_metrics_rejected(lab):
    lab.service.admit(lab.user['id'],{'fly_id':lab.fly['id']})
    result=lab.service.execute_claim(lab.service.repository.claim())
    report=result['reports'][0];folder=lab.executor.calls[0][2]
    with pytest.raises(ValueError,match='disagrees'):
        lab.service.verify_report(report|{'metrics':{'path_length_mm':999}},folder)
    receipt=json.loads((folder/'receipt.json').read_text());receipt['subject']['artifact_id']='b'*64
    write_json(folder/'receipt.json',receipt)
    with pytest.raises(ValueError,match='receipt digest'):
        lab.service.verify_report(report,folder)


def test_atomic_concurrent_idempotent_admission(lab):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:lab.service.admit(lab.user['id'],{'fly_id':lab.fly['id']},'concurrent'),range(8)))
    assert len({r['id'] for r in results})==1
    assert len(lab.service.repository.list())==1


def test_exhausted_worker_lease_is_explicit_failure(lab):
    lab.service.admit(lab.user['id'],{'fly_id':lab.fly['id']})
    repo=lab.service.repository;ident,lease,generation=repo.claim()
    with lab.store.db() as db:db.execute('UPDATE experiments SET expires=0 WHERE id=?',(ident,))
    ident,lease,generation=repo.claim();assert generation==2
    with lab.store.db() as db:db.execute('UPDATE experiments SET expires=0 WHERE id=?',(ident,))
    assert repo.claim() is None
    assert repo.get(ident)['status']=='failed' and repo.get(ident)['comparison'] is None


def test_strict_seeds_profile_graph_and_receipt_binding(lab):
    for seeds in [[True],['42'],[42.0]]:
        assert lab.client.post('/api/v1/experiments',json={'fly_id':lab.fly['id'],'seeds':seeds}).status_code==422
    assert lab.client.post('/api/v1/experiments',json={'fly_id':lab.fly['id'],'duration_seconds':'3'}).status_code==422
    lab.probes.profile=lab.probes.profile|{'hashes':{'connectome':'b'*64}}
    with pytest.raises(ValueError,match='profile graph mismatch'):
        lab.service.admit(lab.user['id'],{'fly_id':lab.fly['id']})


def test_service_admission_exercises_executor_capability_contract(lab,monkeypatch):
    monkeypatch.setattr(lab.executor,'descriptor',lambda:Capability('wrong-runtime',True,('browser',)))
    with pytest.raises(ValueError,match='whole-trial'):
        lab.service.admit(lab.user['id'],{'fly_id':lab.fly['id']})
    assert lab.service.repository.list()==[]


@pytest.mark.parametrize('headers',[{'X-Arena-Submission-Channel':'web'},{'Sec-Fetch-Site':'same-origin'}])
def test_local_bearer_browser_channel_is_web_without_reference_authority(lab,headers):
    response=lab.client.post('/api/v1/flies',json={'name':'Local browser','connectome_sha256':'a'*64},headers=headers)
    assert response.status_code==201,response.text
    assert response.json()['submission_channel']=='web'
    assert response.json()['reference_kind']=='user' and response.json()['release_id'] is None
    assert lab.client.post('/api/v1/flies',json={'name':'Invalid channel','connectome_sha256':'a'*64},headers={'X-Arena-Submission-Channel':'seed'}).status_code==422
