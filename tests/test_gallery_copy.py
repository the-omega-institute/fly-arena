"""A portable public genome can become an owned founder without source accounts."""
import copy
import json
import pytest
from fastapi.testclient import TestClient
from flyarena.api import create_app
from flyarena.auth import AuthConfig
from flyarena.services.life import LifeLedger, LifeNote
from flyarena.services.training import TrainingService, TrainingSpec
from flyarena.store import Store
from test_training import lab, create, complete_next


def publish_bundle(lab, tmp_path):
    source, service, user, _ = lab
    run = create(lab)
    for _ in range(30):
        service.tick()
        if any(m['status'] == 'queued' for m in source.matches()):
            complete_next(source, [1.0])
        if service.get(run['id'])['status'] == 'complete':
            break
    public = service.publish(run['id'], user['id'])
    destination = Store(tmp_path / 'destination')
    folder = destination.root / 'research' / 'evolution-gallery-v038'
    folder.mkdir(parents=True)
    path = folder / 'specimens-public.json'
    path.write_text(json.dumps(public))
    return destination, TrainingService(destination, service.compiler), public, path


def test_copy_retains_genome_lineage_and_admits_training_without_importing_accounts(lab, tmp_path):
    store, service, run, _ = publish_bundle(lab, tmp_path)
    user = store.identity('Visitor')
    member = run['members'][-1]
    source_id = member['fly_id']
    ledger = LifeLedger(store)
    public = ledger.get(source_id)
    assert public['can_annotate'] is False
    assert public['origin']['run_id'] == run['id']
    assert len(public['experiences']) == 1
    assert public['ancestors'][0]['id'] == member['fly']['spec']['parent_id']
    for owner in [None, user['id']]:
        with pytest.raises(ValueError, match='Only the designer'):
            ledger.annotate(source_id, owner, LifeNote(action='retain', reason='sample'), 'note')
    clone = service.copy_published(run['id'], source_id, user['id'])
    assert clone['id'] != source_id and clone['owner'] == user['id']
    assert clone['reference_kind'] == 'user'
    assert clone['artifact_id'] == member['fly']['artifact_id']
    assert clone['spec'] == {**member['fly']['spec'], 'parent_id': source_id}
    assert service.copy_published(run['id'], source_id, user['id'])['id'] == clone['id']
    other = store.identity('Other visitor')
    assert service.copy_published(run['id'], source_id, other['id'])['id'] != clone['id']
    assert ledger.get(clone['id'], user['id'])['ancestors'][0]['id'] == source_id
    with store.db() as db:
        assert db.execute('SELECT count(*) FROM identities').fetchone()[0] == 2
        assert db.execute('SELECT count(*) FROM flies').fetchone()[0] == 2
        assert db.execute('SELECT count(*) FROM matches').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM training_runs').fetchone()[0] == 0
    plan = TrainingSpec(founder_id=clone['id'], circuits=['olfactory'])
    admitted = service.create(user['id'], plan, 'fixture-runtime')
    assert admitted['spec']['founder_id'] == clone['id']
    assert admitted['evaluations_started'] == 0


def test_copy_api_requires_login_and_checks_public_source(lab, tmp_path, monkeypatch):
    store, service, run, path = publish_bundle(lab, tmp_path)
    monkeypatch.setattr('flyarena.api.Connectome', lambda: service.compiler().graph)
    user = store.identity('Visitor'); source_id = run['members'][0]['fly_id']
    endpoint = f"/api/v1/training-showcase/{run['id']}/flies/{source_id}/copy"
    with TestClient(create_app(with_worker=False, store=store, auth_config=AuthConfig())) as client:
        assert client.post(endpoint).status_code == 401
        client.headers['Authorization'] = 'Bearer ' + user['token']
        response = client.post(endpoint)
        assert response.status_code == 201, response.text
        assert response.json()['spec']['parent_id'] == source_id
        assert client.post(endpoint).json()['id'] == response.json()['id']
        assert client.post(endpoint.replace(run['id'], 'absent')).status_code == 422
        assert client.post(endpoint.replace(source_id, '0' * 32)).status_code == 422
    # A shipped design compiled with incompatible weights must fail, not silently change.
    bad = copy.deepcopy(run)
    bad['members'][1]['fly']['artifact_id'] = '0' * 64
    path.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match='incompatible'):
        service.copy_published(run['id'], bad['members'][1]['fly_id'], user['id'])


def test_private_database_ids_cannot_be_exposed_by_bundle_collision(lab):
    store, service, user, _ = lab
    run = create(lab); service.tick()
    member = service.get(run['id'])['members'][0]
    ledger = LifeLedger(store)
    assert ledger.get(member['fly_id']) is None
    public = {'id': 'public-copy', 'status': 'complete', 'spec': run['spec'], 'members': [copy.deepcopy(member)]}
    public['members'][0]['fly']['spec']['name'] = 'Conflicting public genome'
    folder = store.root / 'research' / 'evolution-gallery-v038'; folder.mkdir(parents=True)
    (folder / 'collision-public.json').write_text(json.dumps(public))
    assert ledger.get(member['fly_id']) is None
    assert ledger.get(member['fly_id'], user['id']) is not None
    with pytest.raises(ValueError, match='does not match'):
        service.copy_published(public['id'], member['fly_id'], user['id'])


def test_published_life_observations_read_bundled_evidence(lab, tmp_path):
    store, service, run, path = publish_bundle(lab, tmp_path)
    member = run['members'][0]; mid = member['matches'][0]['id']
    data = {
        'frames': [{'time': 0, 'positions': [[0, 0, 1]], 'energy': [100]},
                   {'time': 1, 'positions': [[3, 4, 1]], 'energy': [101], 'traces': [{'descending': 12}]}],
        'events': [{'type': 'intake', 'slot': 0, 'tick': 100, 'amount': .25}],
        'receipt': {'runtime': {'rules': {'physics_dt': .0001}}, 'total_spikes': [1000]},
    }
    for name, value in data.items():
        (path.parent / f'{mid}-{name}.json').write_text(json.dumps(value))
    detail = LifeLedger(store).observation(member['fly_id'], mid)
    assert detail['status'] == 'recorded'
    assert detail['observations'][0]['food_consumed'] == .25
    assert detail['observations'][0]['sampled_path_mm'] == 5
    assert detail['observations'][0]['first_intake_record_seconds'] == .01
