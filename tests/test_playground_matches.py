"""Saved research offspring can compete without changing formal rankings."""
import pytest
from flyarena.services.ranking import rank, tournament_projection
from test_research_service import lab


def test_ready_unqualified_brain_runs_sandbox_and_swapped_series(lab, monkeypatch, tmp_path):
    monkeypatch.setattr('flyarena.bridge.profile_manifest', lambda *a: {'ready': True})
    monkeypatch.setattr('flyarena.bridge.QUALIFICATION', tmp_path/'missing.json')
    monkeypatch.setattr('flyarena.api.runtime_manifest', lambda **kw: {'fixture': True, **kw})
    ids = [lab.fly['id'], lab.service.references()['wildtype']['id']]
    body = dict(fly_ids=ids, bridge_profile='sensorimotor-research-v2',
                sensory_profile='engineered-kernel-contact-v1', sandbox=True, duration_seconds=1)
    result = lab.client.post('/api/v1/matches', json=body)
    assert result.status_code == 202, result.text
    assert all(result.json()['request'][key] == value for key, value in body.items())
    series = lab.client.post('/api/v1/tournaments', json=body | {'name':'Unranked comparison'})
    assert series.status_code == 202, series.text
    matches = series.json()['matches']
    assert [m['request']['fly_ids'] for m in matches] == [ids, ids[::-1]]
    assert all(m['request']['sandbox'] and m['request']['sensory_profile']==body['sensory_profile'] for m in matches)
    assert lab.client.post('/api/v1/matches', json=body | {'sandbox':False}).status_code == 422
    monkeypatch.setattr('flyarena.bridge.profile_manifest', lambda *a: {'ready':False,'reason':'missing readout'})
    assert lab.client.post('/api/v1/matches', json=body).status_code == 422


@pytest.mark.parametrize('senses',['odor-only-v1','engineered-kernel-contact-v1'])
def test_sandbox_has_comparison_standings_but_no_public_points(senses):
    ids=['a'*32,'b'*32];flies=[{'id':i} for i in ids]
    match={'status':'verified','runtime_hash':'fixture','created':1,
           'request':{'fly_ids':ids,'map_id':'enclosure','mode':'contest','bridge_profile':'sensorimotor-research-v2','sensory_profile':senses,'sandbox':True},
           'result':{'scores':[10,2],'winner_slot':0}}
    assert all(r['matches']==0 for r in rank(flies,[match]))
    comparison=tournament_projection([match],ids)
    assert comparison['status']=='complete' and comparison['sandbox']
    assert comparison['standings'][0]['points']==3
    mixed={**match,'request':{**match['request'],'sandbox':False}}
    assert tournament_projection([match,mixed],ids)['status']=='incomplete'


@pytest.mark.parametrize('map_id', ['maze', 'switchback'])
def test_navigation_comparisons_reject_new_requests_but_keep_stored_matches(lab, monkeypatch, map_id):
    import json
    from flyarena.contracts import MatchRequest, TournamentRequest
    monkeypatch.setattr('flyarena.api.runtime_manifest', lambda **kw: {'fixture': True, **kw})
    ids = [lab.fly['id'], lab.service.references()['wildtype']['id']]
    body = dict(fly_ids=ids, map_id=map_id, mode='contest', sandbox=True, duration_seconds=1)
    for endpoint, payload in [('matches', body), ('tournaments', body | {'name': 'Navigation pair'})]:
        response = lab.client.post('/api/v1/'+endpoint, json=payload)
        assert response.status_code == 422, response.text
        assert 'observation only' in response.text and '#82' in response.text
    # Store admission also protects direct CLI/service callers.
    with pytest.raises(ValueError, match='#82'):
        lab.store.add_match('fixture', MatchRequest(**body).model_dump(), 'fixture')
    with pytest.raises(ValueError, match='#82'):
        lab.store.add_tournament('fixture', TournamentRequest(**body, name='Pair').model_dump(), 'fixture')
    solo = lab.client.post('/api/v1/matches', json=body | {'fly_ids': ids[:1], 'mode': 'forage'})
    assert solo.status_code == 202, solo.text
    historical = MatchRequest(**body).model_dump()
    with lab.store.db() as db:
        db.execute('UPDATE matches SET request=? WHERE id=?', (json.dumps(historical), solo.json()['id']))
    stored = lab.client.get('/api/v1/matches/'+solo.json()['id'])
    assert stored.status_code == 200 and stored.json()['request'] == historical


def test_labyrinth_remains_solo_observation(lab, monkeypatch):
    monkeypatch.setattr('flyarena.api.runtime_manifest', lambda **kw: {'fixture': True, **kw})
    body = dict(fly_ids=[lab.fly['id']], map_id='labyrinth', mode='forage', sandbox=True, duration_seconds=1)
    assert lab.client.post('/api/v1/matches', json=body).status_code == 202
    assert lab.client.post('/api/v1/training', json={'founder_id': lab.fly['id'], 'map_id': 'labyrinth'}).status_code == 422
