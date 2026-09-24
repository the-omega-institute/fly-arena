import json
import pytest
from fastapi.testclient import TestClient
from flyarena.api import create_app
from flyarena.auth import AuthConfig
from flyarena.services.life import LifeLedger,LifeNote
from test_training import lab,create,complete_next


def finish(lab):
    store,service,user,parent=lab
    run=create(lab,strategy='random_search')
    scores=iter([.4,1.4,.4,0.])
    for _ in range(30):
        service.tick()
        if any(m['status']=='queued' for m in store.matches()):complete_next(store,[next(scores)])
        if service.get(run['id'])['status']=='complete':break
    return service.get(run['id'])


def test_life_record_respects_private_origin_and_matches(lab):
    store,service,user,parent=lab;ledger=LifeLedger(store);run=finish(lab)
    candidate=run['members'][-1];ident=candidate['fly_id']
    assert ledger.get(ident) is None
    assert ident not in [f['id'] for f in ledger.listing()]
    record=ledger.get(ident,user['id']);assert record['origin']['fitness']==0
    assert record['origin']['round']==2 and record['origin']['strategy']=='random_search'
    assert record['ancestors'][0]['id']==parent['id']
    assert len(record['experiences'])==1
    # Saving a fly does not accidentally publish its whole training session.
    service.save(run['id'],user['id'],ident)
    public=ledger.get(ident);assert public['origin'] is None and public['experiences']==[]
    service.publish(run['id'],user['id'])
    public=ledger.get(ident);assert public['origin']['fitness']==0
    assert len(public['experiences'])==1
    assert '"owner"' not in json.dumps(public)
    assert len(ledger.get(parent['id'])['descendants'])==4
    assert public['learning']['acquired_state_inherited'] is False


def test_interpretations_append_correct_idempotently_without_changing_results(lab):
    store,service,user,parent=lab;ledger=LifeLedger(store);run=finish(lab)
    candidate=run['members'][-1];ident=candidate['fly_id'];mid=candidate['matches'][0]['id']
    note=LifeNote(action='hypothesis',reason='One second may be too short',match_id=mid)
    first=ledger.annotate(ident,user['id'],note,'first')
    assert ledger.annotate(ident,user['id'],note,'first')==first
    with pytest.raises(ValueError):ledger.annotate(ident,'stranger',note,'foreign')
    with pytest.raises(ValueError):ledger.annotate(ident,user['id'],note.model_copy(update={'reason':'changed'}),'first')
    with pytest.raises(ValueError):ledger.annotate(ident,user['id'],LifeNote(action='correction',reason='x',supersedes='a'*32),'bad')
    second=ledger.annotate(ident,user['id'],LifeNote(action='correction',reason='Need longer evaluation to test this',supersedes=first),'second')
    third=ledger.annotate(ident,user['id'],LifeNote(action='correction',reason='Use multiple seeds as well',supersedes=second),'third')
    assert [n['id'] for n in ledger.get(ident,user['id'])['notes']]==[first,second,third]
    assert service.get(run['id'])['members'][-1]['fitness']==0
    # Private linked notes remain hidden if candidate alone is saved.
    service.save(run['id'],user['id'],ident)
    assert ledger.get(ident)['notes']==[]
    service.publish(run['id'],user['id'])
    assert len(ledger.get(ident)['notes'])==3
    with pytest.raises(ValueError):LifeNote(action='investigate',reason=' ')


def test_observations_distinguish_zero_failed_and_missing_evidence(lab):
    store,service,user,parent=lab;ledger=LifeLedger(store);run=finish(lab)
    candidate=run['members'][-1];ident=candidate['fly_id'];match=candidate['matches'][0];mid=match['id']
    assert ledger.observation(ident,mid) is None
    assert ledger.observation(ident,mid,user['id'])['status']=='evidence_unavailable'
    folder=store.result_folder(match);folder.mkdir(parents=True)
    frames=[{'time':0,'positions':[[0,0,1]],'energy':[100],'traces':[{'descending':0}]},
            {'time':1,'positions':[[3,4,1]],'energy':[98],'traces':[{'descending':12}]}]
    (folder/'frames.json').write_text(json.dumps(frames));(folder/'events.json').write_text('[]')
    (folder/'receipt.json').write_text(json.dumps({'runtime':{'rules':{'physics_dt':.0001}},'total_spikes':[1000]}))
    service.publish(run['id'],user['id'])
    detail=ledger.observation(ident,mid)
    o=detail['observations'][0]
    assert o['food_consumed']==0 and o['food_outcome']=='no_intake_observed'
    assert o['sampled_path_mm']==5 and o['total_spikes']==1000
    assert o['first_intake_record_seconds'] is None and o['exit_seconds'] is None
    with store.db() as db:db.execute("UPDATE matches SET status='failed',result=NULL WHERE id=?",(mid,))
    assert ledger.observation(ident,mid)=={'status':'failed','observations':None}
    assert ledger.get(ident)['experiences'][0]['scores'] is None


def test_life_api_auth_note_corrections_and_readonly_records(lab,monkeypatch):
    store,service,user,parent=lab
    monkeypatch.setattr('flyarena.api.Connectome',lambda:service.compiler().graph)
    with TestClient(create_app(with_worker=False,store=store,auth_config=AuthConfig())) as client:
        path='/api/v1/lives/'+parent['id']
        assert client.get('/api/v1/lives').json()[0]['id']==parent['id']
        assert client.get(path).json()['can_annotate'] is False
        note={'action':'retain','reason':'Reference for later comparisons'}
        assert client.post(path+'/notes',json=note).status_code==401
        client.headers['Authorization']='Bearer '+user['token']
        assert client.get(path).json()['can_annotate'] is True
        assert client.post(path+'/notes',json=note).status_code==422
        r=client.post(path+'/notes',json=note,headers={'Idempotency-Key':'keep'});assert r.status_code==201
        assert client.post(path+'/notes',json=note,headers={'Idempotency-Key':'keep'}).json()==r.json()
        assert client.delete(path+'/notes/'+r.json()['id']).status_code in [404,405]
        client.headers.clear();assert len(client.get(path).json()['notes'])==1
        assert client.get('/api/v1/lives/'+'a'*32).status_code==404


def test_deployed_replay_appears_in_life_history_and_observations(lab):
    store,service,user,parent=lab
    ledger=LifeLedger(store);mid='b'*32
    folder=store.root/'research'/'replay-gallery-v1';folder.mkdir(parents=True)
    match={'id':mid,'status':'verified','attempt':1,'request':{'fly_ids':[parent['id']]},
           'result':{'scores':[0]}}
    (folder/f'{mid}-match.json').write_text(json.dumps(match))
    frames=[{'time':0,'positions':[[0,0,1]],'energy':[100],'traces':[{'descending':0}]},
            {'time':1,'positions':[[3,4,1]],'energy':[98],'traces':[{'descending':12}]}]
    (folder/f'{mid}-frames.json').write_text(json.dumps(frames))
    (folder/f'{mid}-events.json').write_text('[]')
    (folder/f'{mid}-receipt.json').write_text(json.dumps({'runtime':{'rules':{'physics_dt':.0001}},'total_spikes':[1000]}))
    assert store.match(mid) is None
    record=ledger.get(parent['id'])
    assert [e['match']['id'] for e in record['experiences']]==[mid]
    assert record['experiences'][0]['scores']==[0]
    observation=ledger.observation(parent['id'],mid)['observations'][0]
    assert observation['sampled_path_mm']==5
    assert observation['total_spikes']==1000
    assert observation['food_consumed']==0


@pytest.mark.parametrize('fault', [None, 'runtime_mismatch', 'artifact_mismatch', 'missing_runtime',
                                   'missing_artifacts', 'slot_artifacts', 'incomplete', 'running', 'failed', 'loose', 'spoofed_wt'])
def test_guide_requires_complete_validated_wt_series(lab, fault):
    """Synthetic bookkeeping evidence only; these zero scores are not simulation results."""
    from flyarena.contracts import TournamentRequest
    store,service,user,parent=lab
    reference=store.add_fly(user['id'],parent['spec'] | {'name':'WT fixture'},parent['report'] | {'artifact_id':'b'*64})
    with store.db() as db:
        if fault!='spoofed_wt':
            db.execute("UPDATE fly_provenance SET reference_kind='wildtype' WHERE fly_id=?",(reference['id'],))
    series=store.add_tournament(user['id'],TournamentRequest(name='Guide fixture',fly_ids=[parent['id'],reference['id']],
                               seeds=[42,43],duration_seconds=2,sandbox=True).model_dump(),'runtime-A')
    with store.db() as db:
        db.execute("UPDATE matches SET status='verified',result=? WHERE tournament=?",
                   (json.dumps({'winner_slot':None,'scores':[0,0],'receipt_sha256':'synthetic-fixture'}),series['id']))
        last=series['matches'][-1]['id']
        if fault=='runtime_mismatch':db.execute('UPDATE matches SET runtime_hash=? WHERE id=?',('runtime-B',last))
        if fault=='artifact_mismatch':db.execute('UPDATE matches SET artifacts=? WHERE id=?',(json.dumps(['different']*2),last))
        if fault=='slot_artifacts':db.execute('UPDATE matches SET artifacts=? WHERE id=?',(json.dumps(series['matches'][0]['artifacts']),last))
        if fault=='failed':db.execute("UPDATE matches SET status='failed',result=NULL,error='fixture failure' WHERE id=?",(last,))
        if fault=='missing_runtime':db.execute("UPDATE matches SET runtime_hash='' WHERE tournament=?",(series['id'],))
        if fault=='missing_artifacts':db.execute("UPDATE matches SET artifacts='[]' WHERE id=?",(last,))
        if fault=='incomplete':db.execute('DELETE FROM matches WHERE id=?',(last,))
        if fault=='running':db.execute("UPDATE matches SET status='running',result=NULL WHERE id=?",(last,))
        if fault=='loose':db.execute('UPDATE matches SET tournament=NULL WHERE tournament=?',(series['id'],))
    with TestClient(create_app(with_worker=False,store=store,auth_config=AuthConfig())) as client:
        record=client.get('/api/v1/lives/'+parent['id']).json()
    if fault is not None:
        assert record['wt_comparison'] is None
    else:
        evidence=record['wt_comparison']
        assert evidence['series_id']==series['id'] and evidence['protocol_id']=='paired-series/v1'
        assert evidence['status']=='complete' and evidence['reference_id']==reference['id']
        assert evidence['match']['id']==series['matches'][0]['id']
        assert evidence['match']['result']['scores']==[0,0]
        assert 'owner' not in evidence['match']


def test_guide_strategy_list_is_derived_from_training_spec(lab):
    from flyarena.services.training import TrainingSpec
    store,service,user,parent=lab
    record=LifeLedger(store).get(parent['id'],user['id'])
    assert record['training_strategies']==TrainingSpec.model_json_schema()['properties']['strategy']['enum']
    assert 'cross_entropy' in record['training_strategies']
