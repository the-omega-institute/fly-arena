"""Discovery fixtures are DB records, not claims of simulated biological results."""
import json

from fastapi.testclient import TestClient
from flyarena.api import create_app
from flyarena.auth import AuthConfig
from flyarena.services.life import LifeLedger
from test_life_ledger import finish
from test_life_lineage import _child
from test_training import lab, create


def test_search_filters_before_pagination_and_finds_old_designs(lab):
    store, _, user, parent = lab
    with store.db() as db:
        for i in range(215):
            ident = f'{i:032x}'
            spec = parent['spec'] | {'name': f'Fixture {i}', 'parent_id': None}
            db.execute('INSERT INTO flies VALUES(?,?,?,?,?,?,?,?)',
                       (ident, user['id'], spec['name'], parent['color'], json.dumps(spec),
                        parent['artifact_id'], json.dumps(parent['report']), parent['created'] + i + 1))
    ledger = LifeLedger(store)
    assert parent['id'] not in [card['id'] for card in ledger.listing()]
    page = ledger.discover(query='ANCESTOR')
    assert page['total'] == 1 and page['items'][0]['id'] == parent['id']
    assert ledger.discover(query=parent['id'][:12])['items'][0]['id'] == parent['id']
    assert ledger.discover(query='%')['total'] == 0
    assert ledger.discover(query="' OR 1=1 --")['total'] == 0
    first = ledger.discover(limit=100)
    second = ledger.discover(limit=100, offset=first['next_offset'])
    third = ledger.discover(limit=100, offset=second['next_offset'])
    ids = [item['id'] for page in (first, second, third) for item in page['items']]
    assert len(ids) == len(set(ids)) == 216 and ids[-1] == parent['id']
    assert third['next_offset'] is None
    assert ledger.discover(offset=999)['items'] == []


def test_discovery_privacy_counts_descendants_and_reference_provenance(lab):
    store, service, user, parent = lab
    run = create(lab)
    private = _child(lab, parent, training=(run['id'], 0, 0))
    public = _child(lab, private)
    ledger = LifeLedger(store)
    assert ledger.discover(query=private['id'])['total'] == 0
    # Even authenticated public discovery excludes private candidates and edges.
    assert ledger.discover(user['id'], query=private['id'])['total'] == 0
    assert ledger.discover(has_descendants=True)['total'] == 0
    assert ledger.discover(query=public['id'])['items'][0]['parent_id'] is None
    assert ledger.discover('stranger', scope='accessible', query=private['id'])['total'] == 0
    owned = ledger.discover(user['id'], scope='accessible', has_descendants=True)
    assert {item['id'] for item in owned['items']} == {parent['id'], private['id']}
    assert ledger.discover(reference_kind='user')['total'] == 2
    assert ledger.discover(reference_kind='official')['total'] == 0
    # Model the publication flag directly; this fixture has no simulated fitness.
    with store.db() as db:
        db.execute('UPDATE training_members SET saved=1 WHERE fly_id=?', (private['id'],))
    assert ledger.discover(has_descendants=True)['total'] == 2
    assert ledger.discover(has_descendants=False)['items'][0]['id'] == public['id']


def test_continuation_exposes_only_accessible_actual_evaluation_context(lab):
    store, service, user, _ = lab
    run = finish(lab)
    candidate = run['members'][-1]
    ident = candidate['fly_id']
    ledger = LifeLedger(store)
    own = ledger.get(ident, user['id'])['continuation']
    assert own['requires_copy'] is False
    assert len(own['conditions']) == 1
    condition = own['conditions'][0]
    request = candidate['matches'][0]['request']
    for key in ('map_id', 'seed', 'mode', 'bridge_profile', 'sensory_profile', 'duration_seconds'):
        assert condition[key] == request[key]
    assert condition['fitness_objective'] == run['spec']['fitness_objective']
    service.save(run['id'], user['id'], ident)
    assert ledger.get(ident)['continuation']['conditions'] == []
    service.publish(run['id'], user['id'])
    assert ledger.get(ident)['continuation'] == own
    with store.db() as db:
        db.execute("UPDATE matches SET status='failed',result=NULL WHERE id=?", (condition['match_id'],))
    failed = ledger.get(ident)['continuation']['conditions'][0]
    assert failed['status'] == 'failed'
    assert failed['map_id'] == condition['map_id']


def test_missing_context_is_not_filled_with_current_defaults(lab):
    store, _, _, parent = lab
    folder = store.root / 'research' / 'replay-gallery-v1'
    folder.mkdir(parents=True)
    match = {'id': 'b' * 32, 'status': 'failed', 'request': {'fly_ids': [parent['id']], 'map_id': 'orchard', 'seed': 0}}
    (folder / f'{match["id"]}-match.json').write_text(json.dumps(match))
    condition = LifeLedger(store).get(parent['id'])['continuation']['conditions'][0]
    assert condition == {'match_id': match['id'], 'status': 'failed', 'map_id': 'orchard', 'seed': 0}


def test_bundled_objective_is_bound_to_its_match_not_another_experience(lab):
    store, _, _, parent = lab
    folder = store.root / 'research' / 'evolution-gallery-v038'
    folder.mkdir(parents=True)
    match = {'id': 'b' * 32, 'status': 'failed', 'request': {'fly_ids': [parent['id']], 'map_id': 'orchard', 'seed': 0}}
    run = {'id': 'f' * 32, 'status': 'complete', 'spec': {'fitness_objective': 'sustained-foraging-v1'},
           'members': [{'matches': [match]}]}
    (folder / 'fixture-public.json').write_text(json.dumps(run))
    standalone = store.root / 'research' / 'replay-gallery-v1'
    standalone.mkdir(parents=True)
    other = match | {'id': 'c' * 32}
    (standalone / f'{other["id"]}-match.json').write_text(json.dumps(other))
    conditions = {c['match_id']: c for c in LifeLedger(store).get(parent['id'])['continuation']['conditions']}
    assert conditions[match['id']]['fitness_objective'] == 'sustained-foraging-v1'
    assert 'fitness_objective' not in conditions[other['id']]


def test_discovery_api_validates_bounds_and_keeps_legacy_list(lab, monkeypatch):
    store, service, user, parent = lab
    monkeypatch.setattr('flyarena.api.Connectome', lambda: service.compiler().graph)
    with TestClient(create_app(with_worker=False, store=store, auth_config=AuthConfig())) as client:
        assert isinstance(client.get('/api/v1/lives').json(), list)
        route = '/api/v1/lives/discover'
        page = client.get(route, params={'query': 'Ancestor', 'reference_kind': 'user', 'has_descendants': False}).json()
        assert page['total'] == 1 and page['items'][0]['id'] == parent['id']
        assert 'owner' not in json.dumps(page)
        for params in ({'offset': -1}, {'limit': 0}, {'limit': 101}, {'reference_kind': 'invented'}, {'scope': 'private'}, {'query': 'x' * 201}):
            assert client.get(route, params=params).status_code == 422
        client.headers['Authorization'] = 'Bearer ' + user['token']
        assert client.get(route).json()['items'][0]['can_annotate'] is True
