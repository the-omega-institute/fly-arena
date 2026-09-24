"""Synthetic ledger/API fixtures; no simulation performance is asserted."""
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from flyarena.api import create_app
from flyarena.auth import AuthConfig
from flyarena.services.observation_series import (
    ObservationSeriesRequest, create_series, get_series, list_series, observation_schedule,
)
from flyarena.store import Store


@pytest.fixture
def ledger(tmp_path):
    store = Store(tmp_path)
    ids = [store.add_fly('owner', {'name': c, 'color': 'mint'}, {'artifact_id': c*64})['id'] for c in 'ab']
    return store, ids


def plan(ids, mode='forage', **changes):
    return ObservationSeriesRequest(name='synthetic observation', fly_ids=ids[:1] if mode == 'forage' else ids,
                                    mode=mode, map_id='labyrinth' if mode == 'forage' else 'duel',
                                    **dict(seeds=[42, 43], duration_seconds=30, **changes)).model_dump()


def finish(store, report):
    for match in report['matches']:
        solo = report['observation_only']
        result = {'winner_slot': None if solo else 0, 'scores': [99] if solo else [2, 1],
                  'outcome': 'solo' if solo else 'win', 'task': {'arrival_seconds': None, 'completed': False}}
        with store.db() as db:
            db.execute("UPDATE matches SET status='verified',result=? WHERE id=?", (json.dumps(result), match['id']))
    return get_series(store, report['id'])


@pytest.mark.parametrize('mode,expected', [('forage', 2), ('duel', 4)])
def test_frozen_plan_survives_restart_with_missing_failed_and_pending_legs(ledger, mode, expected):
    store, ids = ledger
    spec = plan(ids, mode)
    saved = create_series(store, 'owner', spec, 'runtime', 'retry')
    assert saved['status'] == 'running' and saved['expected_matches'] == expected
    assert saved['expected_schedule'] == observation_schedule(spec)
    assert saved['frozen']['artifacts'] == {f: store.fly(f)['artifact_id'] for f in spec['fly_ids']}
    assert all(row['status'] == 'queued' for row in saved['schedule'])
    with store.db() as db:
        db.execute('DELETE FROM matches WHERE id=?', (saved['matches'][0]['id'],))
        db.execute("UPDATE matches SET status='failed',error='measured fixture failure' WHERE id=?", (saved['matches'][1]['id'],))
    restarted = Store(store.root)
    report = get_series(restarted, saved['id'])
    assert report['status'] == 'incomplete' and report['standings'] == []
    assert len(report['schedule']) == expected
    assert sorted(row['status'] for row in report['schedule']) == sorted(['missing', 'failed'] + ['queued']*(expected-2))
    assert any(row['errors'] == ['measured fixture failure'] for row in report['schedule'])
    assert create_series(restarted, 'owner', spec, 'different-runtime', 'retry')['id'] == saved['id']
    assert get_series(restarted, 'absent') is None


def test_solo_completion_does_not_score_or_fabricate_arrival(ledger):
    store, ids = ledger
    report = finish(store, create_series(store, 'owner', plan(ids), 'runtime'))
    assert report['status'] == 'complete' and report['verified_matches'] == 2
    assert report['observation_only'] and report['standings'] == [] and report['ranking_policy'] is None
    assert all(row['outcomes'] is None and row['spawn_order'] == 1 for row in report['schedule'])
    assert all(m['result']['task']['arrival_seconds'] is None for m in report['matches'])


def test_duel_pair_uses_both_slots_before_shared_aggregate(ledger):
    store, ids = ledger
    saved = create_series(store, 'owner', plan(ids, 'duel'), 'runtime')
    assert [r['fly_ids'] for r in saved['schedule']] == [ids, ids[::-1]]*2
    report = finish(store, saved)
    assert report['status'] == 'complete' and not report['observation_only']
    assert all(row['wins'] == row['losses'] == 2 and row['points'] == 6 for row in report['standings'])
    with store.db() as db:
        db.execute("UPDATE matches SET status='running',result=NULL WHERE id=?", (saved['matches'][0]['id'],))
    partial = get_series(store, saved['id'])
    assert partial['status'] == 'running' and partial['standings'] == []


@pytest.mark.parametrize('field,value,issue', [
    ('runtime_hash', 'changed-for-all', 'runtime_mismatch'),
    ('artifacts', '["changed-for-all"]', 'artifact_mismatch'),
    ('owner', 'other', 'membership_mismatch'),
    ('status', 'invented', 'invalid_status'),
    ('result', '{}', 'invalid_result'),
    ('result', '[1]', 'invalid_result'),
])
def test_frozen_evidence_rejects_even_consistent_replacements(ledger, field, value, issue):
    store, ids = ledger
    saved = finish(store, create_series(store, 'owner', plan(ids), 'runtime'))
    with store.db() as db:
        db.execute(f'UPDATE matches SET {field}=?', (value,))
    report = get_series(store, saved['id'])
    assert report['status'] == 'incomplete' and issue in report['issues']


def test_conditions_duplicates_and_unexpected_members_do_not_complete(ledger):
    store, ids = ledger
    saved = create_series(store, 'owner', plan(ids), 'runtime')
    duplicate = store.add_match('owner', saved['expected_schedule'][0], 'runtime')
    extra = store.add_match('owner', dict(saved['expected_schedule'][0], seed=999), 'runtime')
    with store.db() as db:
        for match in (duplicate, extra):
            db.execute('INSERT INTO observation_legs VALUES(?,?)', (saved['id'], match['id']))
        request = deepcopy(saved['expected_schedule'][1]); request['duration_seconds'] = 1
        db.execute('UPDATE matches SET request=? WHERE id=?', (json.dumps(request), saved['frozen']['match_ids'][1]))
    report = get_series(store, saved['id'])
    assert set(report['issues']) >= {'duplicate_match', 'unexpected_match', 'condition_mismatch'}
    assert report['unexpected_match_ids'] == [extra['id']]


def test_replacing_membership_with_an_identical_request_is_detected(ledger):
    store, ids = ledger
    saved = create_series(store, 'owner', plan(ids), 'runtime')
    duplicate = store.add_match('owner', saved['expected_schedule'][0], 'runtime')
    with store.db() as db:
        db.execute('UPDATE observation_legs SET match_id=? WHERE series_id=? AND match_id=?',
                   (duplicate['id'], saved['id'], saved['frozen']['match_ids'][0]))
    assert 'membership_mismatch' in get_series(store, saved['id'])['issues']


@pytest.mark.parametrize('patch', [
    {'seeds': []}, {'seeds': [1, 1]}, {'seeds': [1, 2, 3, 4]}, {'seeds': [-1]},
    {'seeds': [2147483648]}, {'seeds': [True]}, {'seeds': [1.0]},
    {'duration_seconds': 301}, {'duration_seconds': 0}, {'duration_seconds': 1.5},
    {'sandbox': False}, {'mode': 'contest'}, {'mode': 'duel'}, {'map_id': 'duel'},
    {'fly_ids': ['a'*32, 'b'*32]},
])
def test_invalid_plans_are_rejected_before_admission(ledger, patch):
    _, ids = ledger
    with pytest.raises(ValueError):
        ObservationSeriesRequest.model_validate(dict(plan(ids), **patch))


def test_atomic_quota_and_idempotency_cross_resource_conflicts(ledger):
    store, ids = ledger
    spec = plan(ids, 'duel')
    with ThreadPoolExecutor(max_workers=2) as pool:
        reports = list(pool.map(lambda _: create_series(store, 'owner', spec, 'runtime', 'same'), range(2)))
    assert reports[0]['id'] == reports[1]['id'] and len(store.matches()) == 4
    with pytest.raises(ValueError, match='different request'):
        create_series(store, 'owner', dict(spec, seeds=[9]), 'runtime', 'same')
    with pytest.raises(ValueError, match='different request'):
        store.add_match('owner', reports[0]['expected_schedule'][0], 'runtime', key='same')
    for seed in (100, 200):
        create_series(store, 'owner', dict(spec, seeds=[seed, seed+1]), 'runtime')
    with pytest.raises(ValueError, match='queue slots'):
        create_series(store, 'owner', spec, 'runtime', 'overflow')
    assert len(list_series(store, 'owner')) == 3 and len(store.matches()) == 12
    with store.db() as db:
        assert db.execute("SELECT count(*) FROM idempotency WHERE key='overflow'").fetchone()[0] == 0


def test_api_admission_retry_readiness_recovery_and_owner_filter(ledger, monkeypatch):
    store, ids = ledger
    identity = store.identity('fixture')
    monkeypatch.setattr('flyarena.api.runtime_manifest', lambda **kw: {'fixture': True, **kw})
    monkeypatch.setattr('flyarena.api.require_training_bridge', lambda profile: None)
    spec = plan(ids, 'duel')
    headers = {'Authorization': 'Bearer '+identity['token'], 'Idempotency-Key': 'api-key'}
    with TestClient(create_app(with_worker=False, store=store, auth_config=AuthConfig())) as client:
        assert client.post('/api/v1/observation-series', json=spec).status_code == 401
        response = client.post('/api/v1/observation-series', json=spec, headers=headers)
        assert response.status_code == 202, response.text
        saved = response.json()
        def unavailable(profile):
            raise ValueError('measured fixture readiness failure')
        monkeypatch.setattr('flyarena.api.require_training_bridge', unavailable)
        retry = client.post('/api/v1/observation-series', json=spec, headers=headers)
        assert retry.status_code == 202 and retry.json()['id'] == saved['id']
        assert client.post('/api/v1/observation-series', json=spec, headers=dict(headers, **{'Idempotency-Key': 'new'})).status_code == 422
        assert client.get('/api/v1/observation-series/'+saved['id']).json()['expected_matches'] == 4
        assert client.get('/api/v1/observation-series/absent').status_code == 404
        with store.db() as db:
            for i in range(31):
                db.execute('INSERT INTO observation_series SELECT ?,?,spec,schedule,frozen,created+? FROM observation_series WHERE id=?',
                           (f'other-{i}', 'other', i+1, saved['id']))
        assert [r['id'] for r in client.get('/api/v1/observation-series?owner='+identity['id']).json()] == [saved['id']]


def test_storage_failure_rolls_back_legs_identity_and_key(ledger):
    store, ids = ledger
    with store.db() as db:
        db.execute("""CREATE TRIGGER fixture_failure BEFORE INSERT ON matches
                      WHEN (SELECT count(*) FROM matches) = 1
                      BEGIN SELECT RAISE(ABORT, 'synthetic second-leg storage failure'); END""")
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError, match='second-leg'):
        create_series(store, 'owner', plan(ids, 'duel'), 'runtime', 'rollback')
    with store.db() as db:
        for table in ('matches', 'observation_series', 'observation_legs', 'idempotency'):
            assert db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0
