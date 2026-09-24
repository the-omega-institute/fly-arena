"""Synthetic protocol fixtures test bookkeeping, not simulated performance."""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from flyarena.api import create_app
from flyarena.auth import AuthConfig
from flyarena.contracts import TournamentRequest
from flyarena.services.competition_protocol import competition_protocol, expected_schedule
from flyarena.store import Store


@pytest.fixture
def series():
    spec = TournamentRequest(name='paired fixture', fly_ids=['a'*32, 'b'*32], seeds=[42, 43],
                             duration_seconds=2, sandbox=True).model_dump()
    tournament = {'id': 'series', 'owner': 'owner', 'spec': spec}
    matches = [dict(id=f'leg-{i}', tournament='series', owner='owner', created=i,
                    request=request, artifacts=[fly[0]*64 for fly in request['fly_ids']],
                    runtime_hash='runtime', status='verified', error=None,
                    result={'winner_slot': 0, 'scores': [2, 1]})
               for i, request in enumerate(expected_schedule(spec))]
    return tournament, matches


def test_schedule_and_totals_follow_fly_identity_across_swapped_slots(series):
    tournament, matches = series
    result = competition_protocol(tournament, list(reversed(matches)))
    assert result['status'] == 'complete'
    assert [(row['seed'], row['spawn_order']) for row in result['schedule']] == [(42, 1), (42, 2), (43, 1), (43, 2)]
    assert result['expected_matches'] == result['verified_matches'] == 4
    assert all(row['wins'] == row['losses'] == 2 and row['points'] == 6 for row in result['standings'])
    assert result['schedule'][1]['outcomes'][0] == {'fly_id': 'b'*32, 'score': 2, 'outcome': 'win'}


def test_first_leg_and_empty_series_never_establish_completion(series):
    tournament, matches = series
    for subset in ([], matches[:1], matches[:3]):
        result = competition_protocol(tournament, subset)
        assert result['status'] == 'incomplete' and result['standings'] == []
        assert len(result['schedule']) == 4
        assert sum(row['status'] == 'missing' for row in result['schedule']) == 4-len(subset)
    result = competition_protocol(tournament, matches[:1])
    assert result['schedule'][0]['outcomes'][0]['outcome'] == 'win'


def test_queued_or_running_legs_withhold_aggregate(series):
    tournament, matches = series
    for status in ('queued', 'running'):
        matches[1].update(status=status, result=None)
        result = competition_protocol(tournament, matches)
        assert result['status'] == 'running' and result['standings'] == []
        assert result['schedule'][1]['outcomes'] is None


def test_failure_dominates_pending_and_preserves_error(series):
    tournament, matches = series
    matches[1].update(status='failed', result=None, error='Measured worker failure')
    matches[2].update(status='queued', result=None)
    result = competition_protocol(tournament, matches)
    assert result['status'] == 'incomplete' and result['standings'] == []
    assert result['schedule'][1]['errors'] == ['Measured worker failure']
    assert result['schedule'][1]['status'] == 'failed'


@pytest.mark.parametrize('key,value', [('map_id', 'scarcity'), ('mode', 'sumo'), ('duration_seconds', 3),
                                      ('bridge_profile', 'sensorimotor-research-v2'), ('sensory_profile', 'other'),
                                      ('sandbox', False), ('season_id', 'other')])
def test_conditions_must_match_durable_spec_even_if_all_legs_agree(series, key, value):
    tournament, matches = series
    for match in matches:
        match['request'][key] = value
    result = competition_protocol(tournament, matches)
    assert result['status'] == 'incomplete' and result['standings'] == []
    assert 'condition_mismatch' in result['issues']


@pytest.mark.parametrize('field,value,issue', [('runtime_hash', 'other', 'runtime_mismatch'),
                                             ('artifacts', ['different', 'different'], 'artifact_mismatch'),
                                             ('artifacts', [], 'artifact_mismatch'),
                                             ('owner', 'other', 'membership_mismatch'),
                                             ('tournament', 'other', 'membership_mismatch'),
                                             ('status', 'unknown', 'invalid_status')])
def test_mismatched_evidence_cannot_score(series, field, value, issue):
    tournament, matches = series
    matches[1][field] = value
    result = competition_protocol(tournament, matches)
    assert result['status'] == 'incomplete' and result['standings'] == []
    assert issue in result['issues']


@pytest.mark.parametrize('result', [None, {}, {'scores': [1, 2]}, {'winner_slot': 7, 'scores': [1, 2]},
                                    {'winner_slot': True, 'scores': [1, 2]}, {'winner_slot': 0, 'scores': [float('nan'), 2]}])
def test_invalid_verified_result_is_visible_not_scored(series, result):
    tournament, matches = series
    matches[0]['result'] = result
    report = competition_protocol(tournament, matches)
    assert report['status'] == 'incomplete' and report['standings'] == []
    assert 'invalid_result' in report['schedule'][0]['issues']


def test_duplicate_and_unscheduled_matches_remain_visible(series):
    tournament, matches = series
    duplicate = deepcopy(matches[0]); duplicate['id'] = 'duplicate'
    extra = deepcopy(matches[0]); extra['id'] = 'extra'; extra['request']['seed'] = 99
    result = competition_protocol(tournament, matches + [duplicate, extra])
    assert result['status'] == 'incomplete' and result['standings'] == []
    assert result['schedule'][0]['match_ids'] == ['leg-0', 'duplicate']
    assert result['unexpected_match_ids'] == ['extra']


def test_draws_and_historical_profile_defaults(series):
    tournament, matches = series
    for key in ('bridge_profile', 'sensory_profile', 'sandbox'):
        tournament['spec'].pop(key)
        for match in matches:
            match['request'].pop(key)
            match['result']['winner_slot'] = None
    report = competition_protocol(tournament, matches)
    assert report['status'] == 'complete'
    assert all(row['draws'] == row['points'] == 4 for row in report['standings'])


def test_round_robin_schedule_includes_every_pair_and_seed():
    spec = TournamentRequest(name='round robin', fly_ids=[c*32 for c in 'abc'], seeds=[1, 2]).model_dump()
    schedule = expected_schedule(spec)
    assert len(schedule) == 12
    assert len({(row['seed'], tuple(row['fly_ids'])) for row in schedule}) == 12
    for a, b in zip(schedule[::2], schedule[1::2]):
        assert a['seed'] == b['seed'] and a['fly_ids'] == b['fly_ids'][::-1]


def test_api_recovers_durable_schedule_and_filters_owner_before_limit(tmp_path):
    store = Store(tmp_path)
    flies = [store.add_fly('owner', {'name': c, 'color': 'mint'}, {'artifact_id': c*64})['id'] for c in 'ab']
    spec = TournamentRequest(name='durable fixture', fly_ids=flies).model_dump()
    saved = store.add_tournament('owner', spec, 'runtime', 'retry-key')
    assert store.add_tournament('owner', spec, 'runtime', 'retry-key')['id'] == saved['id']
    with store.db() as db:
        db.execute('DELETE FROM matches WHERE id=?', (saved['matches'][1]['id'],))
        db.execute("UPDATE matches SET status='failed',error='fixture failure' WHERE tournament=?", (saved['id'],))
        for i in range(31):
            db.execute('INSERT INTO tournaments SELECT ?,?,spec,created+? FROM tournaments WHERE id=?',
                       (f'other-{i}', 'other', i+1, saved['id']))
    restarted = Store(tmp_path)
    with TestClient(create_app(with_worker=False, store=restarted, auth_config=AuthConfig())) as client:
        report = client.get('/api/v1/tournaments/'+saved['id']).json()
        assert report['id'] == saved['id'] and report['status'] == 'incomplete'
        assert report['standings'] == [] and report['expected_matches'] == 2
        assert [row['status'] for row in report['schedule']] == ['failed', 'missing']
        assert report['schedule'][0]['errors'] == ['fixture failure']
        assert [row['id'] for row in client.get('/api/v1/tournaments?owner=owner').json()] == [saved['id']]
        assert client.get('/api/v1/tournaments/not-found').status_code == 404


def test_sandbox_180_second_pair_is_atomic_recoverable_and_outside_rankings(tmp_path):
    store = Store(tmp_path)
    ids = [store.add_fly('owner', {'name': c, 'color': 'mint'}, {'artifact_id': c*64})['id'] for c in 'ab']
    spec = TournamentRequest(name='long sandbox comparison', fly_ids=ids,
                             duration_seconds=180, sandbox=True).model_dump()
    report = store.add_tournament('owner', spec, 'runtime', 'long-pair')
    assert report['expected_matches'] == 2 and report['verified_matches'] == 0
    first, second = report['matches']
    assert first['request']['fly_ids'] == second['request']['fly_ids'][::-1]
    assert all(m['request']['duration_seconds'] == 180 and m['request']['sandbox'] for m in report['matches'])
    assert store.add_tournament('owner', spec, 'new-runtime', 'long-pair')['id'] == report['id']
    with pytest.raises(ValueError, match='different request'):
        store.add_tournament('owner', dict(spec, duration_seconds=60), 'runtime', 'long-pair')
    restarted = Store(tmp_path)
    assert restarted.tournament(report['id'])['spec']['duration_seconds'] == 180
    # Synthetic verified outcomes exercise membership/accounting, not long-run physics.
    import json
    with restarted.db() as db:
        db.execute("UPDATE matches SET status='verified',result=? WHERE tournament=?",
                   (json.dumps({'winner_slot': 0, 'scores': [2., 1.], 'outcome': 'win'}), report['id']))
    result = restarted.tournament(report['id'])
    assert result['status'] == 'complete'
    assert all(row['wins'] == row['losses'] == 1 for row in result['standings'])
    assert all(row['matches'] == row['points'] == 0 for row in restarted.leaderboard())
