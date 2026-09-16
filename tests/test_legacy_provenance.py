"""Historical fixtures and admission only: no scientific executor is run."""
import json
import uuid

import pytest

from flyarena.common import canonical
from test_research_service import lab


def legacy(lab, source, owner):
    ident = uuid.uuid4().hex
    # Insert the historical shape directly, without ever recording provenance.
    with lab.store.db() as db:
        db.execute('INSERT INTO flies VALUES(?,?,?,?,?,?,?,?)',
                   (ident, owner, source['name'], source['color'], canonical(source['spec']).decode(),
                    source['artifact_id'], canonical(source['report']).decode(), 1.0))
    return ident


def test_missing_provenance_reads_preserve_rows_and_reference_authority(lab):
    refs = lab.service.references()
    ids = [legacy(lab, refs[role], owner) for role in ('wildtype', 'official')
           for owner in ('arena', lab.user['id'])]
    with lab.store.db() as db:
        before = list(map(tuple, db.execute('SELECT * FROM flies ORDER BY id')))
        provenance = list(map(tuple, db.execute('SELECT * FROM fly_provenance ORDER BY fly_id')))
    listed = {f['id']: f for f in lab.client.get('/api/v1/flies').json()}
    for ident in ids:
        detail = lab.client.get('/api/v1/flies/' + ident)
        assert detail.status_code == 200
        assert detail.json() == listed[ident] == lab.store.fly(ident)
        assert all(detail.json()[k] is None for k in ('reference_kind', 'submission_channel', 'release_id'))
    for role, ref in refs.items():
        assert listed[ref['id']]['reference_kind'] == role
        assert listed[ref['id']]['submission_channel'] == 'seed'
        assert listed[ref['id']]['release_id'] == ref['release_id']
    clone = lab.store.add_fly(lab.user['id'], refs['official']['spec'], refs['official']['report'])
    assert clone['artifact_id'] == refs['official']['artifact_id']
    assert (clone['reference_kind'], clone['submission_channel'], clone['release_id']) == ('user', 'web', None)
    with lab.store.db() as db:
        assert list(map(tuple, db.execute('SELECT * FROM flies WHERE id!=? ORDER BY id', (clone['id'],)))) == before
        assert list(map(tuple, db.execute('SELECT * FROM fly_provenance WHERE fly_id!=? ORDER BY fly_id', (clone['id'],)))) == provenance


@pytest.mark.parametrize('historical_snapshot', [False, True])
def test_owned_legacy_admission_freezes_nulls_and_preserves_retries(lab, historical_snapshot):
    refs = lab.service.references()
    source = lab.fly | {'spec': lab.fly['spec'] | {'parent_id': refs['official']['id']}}
    ident = legacy(lab, source, lab.user['id'])
    request = {'fly_id': ident}
    headers = {'Idempotency-Key': 'legacy-snapshot'}
    response = lab.client.post('/api/v1/experiments', json=request, headers=headers)
    assert response.status_code == 202, response.text
    experiment = response.json()
    subject = experiment['subjects'][2]
    assert subject == {'role': 'design', 'fly_id': ident, 'name': source['name'],
                       'artifact_id': source['artifact_id'], 'parent_id': refs['official']['id'],
                       'reference_kind': None, 'submission_channel': None, 'release_id': None}
    for snapshot in experiment['subjects'][:2]:
        ref = refs[snapshot['role']]
        assert snapshot['parent_id'] == ref['spec'].get('parent_id')
        for field in ('reference_kind', 'submission_channel', 'release_id'):
            assert snapshot[field] == ref[field]
    if historical_snapshot:
        # Represent an experiment admitted before snapshot fields existed.
        experiment['subjects'] = [{k: s[k] for k in ('role', 'fly_id', 'name', 'artifact_id')}
                                  for s in experiment['subjects']]
        with lab.store.db() as db:
            db.execute('UPDATE experiments SET subjects=? WHERE id=?',
                       (canonical(experiment['subjects']).decode(), experiment['id']))
    with lab.store.db() as db:
        stored = db.execute('SELECT subjects FROM experiments WHERE id=?', (experiment['id'],)).fetchone()[0]
        assert not db.execute('SELECT 1 FROM fly_provenance WHERE fly_id=?', (ident,)).fetchone()
        # A later live provenance row must not rewrite an admitted snapshot.
        db.execute('INSERT INTO fly_provenance VALUES(?,?,?,?,NULL)', (ident, 'ai', None, 'api'))
    lab.probes.profile = lab.probes.profile | {'ready': False}
    assert lab.client.post('/api/v1/experiments', json=request, headers=headers).json() == experiment
    assert lab.client.get('/api/v1/experiments/' + experiment['id']).json() == experiment
    assert lab.client.get('/api/v1/experiments').json()[0] == experiment
    with lab.store.db() as db:
        assert db.execute('SELECT subjects FROM experiments WHERE id=?', (experiment['id'],)).fetchone()[0] == stored
    assert json.loads(stored) == experiment['subjects']
    assert lab.executor.calls == []


def test_legacy_owner_admission_is_independent_of_provenance(lab):
    ident = legacy(lab, lab.fly, lab.user['id'])
    other = lab.store.identity('Fixture designer')  # display name conveys no ownership
    rejected = lab.client.post('/api/v1/experiments', json={'fly_id': ident},
                               headers={'Authorization': 'Bearer ' + other['token']})
    assert rejected.status_code == 422
    assert 'authenticated owner' in rejected.json()['detail']
    assert lab.client.post('/api/v1/experiments', json={'fly_id': ident}).status_code == 202
    assert lab.executor.calls == []
