"""Offline summary/API fixtures; payload sizes are not biological or latency evidence."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from flyarena.api import create_app
from flyarena.auth import AuthConfig
from flyarena.common import canonical
from flyarena.research import ExperimentSpec, PhenotypeReport, compare_reports
from flyarena.services.experiments import ExperimentRepository
from flyarena.store import Store
from test_research_service import lab  # Existing admission fixture; no trial is executed.

FIELDS = {'id', 'owner', 'status', 'spec'}
SPEC = ExperimentSpec(fly_id='d' * 32).model_dump()
MEASUREMENTS = Path(__file__).resolve().parents[1] / '.validation' / 'measurements.json'


def record(value):
    MEASUREMENTS.parent.mkdir(exist_ok=True)
    values = json.loads(MEASUREMENTS.read_text()) if MEASUREMENTS.exists() else []
    MEASUREMENTS.write_text(json.dumps([*values, value], indent=2) + '\n')


def insert(store, count):
    with store.db() as db:
        db.executemany(
            'INSERT INTO experiments(id,owner,spec,subjects,conditions,status,created,updated) VALUES(?,?,?,?,?,?,?,?)',
            [(f'{i:032x}', 'alice' if i % 2 == 0 else 'bob', canonical(SPEC).decode(), '[]', '[]',
              ('queued', 'running', 'complete', 'failed')[i % 4], i // 2, i // 2) for i in range(count)])


@pytest.fixture
def repo(tmp_path):
    return ExperimentRepository(Store(tmp_path / 'store'))


def test_empty_order_limit_filter_and_status(repo):
    assert repo.list_summaries() == []
    insert(repo.store, 205)
    for owner in (None, 'alice', 'bob', "alice' OR 1=1 --", 'missing'):
        expected = [{k: e[k] for k in FIELDS} for e in repo.list(owner)]
        assert repo.list_summaries(owner) == expected
    rows = repo.list_summaries()
    assert len(rows) == 100
    assert {r['status'] for r in rows} == {'queued', 'running', 'complete', 'failed'}
    assert all(set(r) == FIELDS and r['spec'] == SPEC for r in rows)
    # Includes tied created values; ordering remains exactly the legacy ordering.
    assert len(repo.list_summaries('alice')) == 100


@pytest.mark.parametrize('count', [1, 100])
@pytest.mark.parametrize('owner', [None, 'alice'])
def test_single_select_and_no_heavy_column_access(repo, monkeypatch, count, owner):
    insert(repo.store, count)
    statements, columns = [], set()
    original_db = repo.store.db

    def authorize(action, table, column, *_):
        if action == sqlite3.SQLITE_READ and table == 'experiments':
            columns.add(column)
            if column not in {'id', 'owner', 'spec', 'status', 'created'}:
                return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    @contextmanager
    def guarded_db():
        with original_db() as db:
            db.set_authorizer(authorize)
            db.set_trace_callback(statements.append)
            yield db

    monkeypatch.setattr(repo.store, 'db', guarded_db)
    def forbidden(*args, **kwargs):
        pytest.fail('Summary used the full list/get path')
    monkeypatch.setattr(repo, 'list', forbidden)
    original_get = repo.get
    monkeypatch.setattr(repo, 'get', forbidden)
    loads = json.loads
    decoded = []
    def decode(value):
        decoded.append(value)
        return loads(value)
    monkeypatch.setattr('flyarena.services.experiments.json.loads', decode)
    rows = repo.list_summaries(owner)
    assert len(rows) == (count if owner is None else (count + 1) // 2)
    assert len(statements) == 1 and statements[0].startswith('SELECT id,owner,spec,status ')
    assert columns == {'id', 'owner', 'spec', 'status', 'created'}
    assert decoded == [canonical(SPEC).decode()] * len(rows)
    observed_columns = sorted(columns)
    # Negative control establishes that the guard actually rejects full reads.
    with pytest.raises(sqlite3.DatabaseError, match='prohibited'):
        original_get('0' * 32)
    record({'check': 'sql', 'stored_rows': count, 'owner': owner, 'returned_rows': len(rows),
            'select_count': 1, 'read_columns': observed_columns,
            'decoded_columns': ['spec'], 'heavy_read_negative_control': 'rejected',
            'query': statements[0]})


def client_for(repo):
    return TestClient(create_app(with_worker=False, store=repo.store, auth_config=AuthConfig(),
                                 research_service=SimpleNamespace(repository=repo)),
                      headers={'Accept-Encoding': 'identity'})


def test_api_legacy_summary_public_scope_and_validation(repo):
    insert(repo.store, 4)
    expected = repo.list()
    with repo.store.db() as db:
        before = [tuple(r) for r in db.execute('SELECT * FROM experiments ORDER BY id')]
    with client_for(repo) as client:
        default = client.get('/api/v1/experiments')
        explicit = client.get('/api/v1/experiments?summary=false')
        assert default.status_code == explicit.status_code == 200
        assert default.json() == explicit.json() == expected
        assert default.content == explicit.content
        summary = client.get('/api/v1/experiments?summary=true')
        assert summary.status_code == 200
        assert summary.json() == [{k: e[k] for k in FIELDS} for e in expected]
        assert {e['owner'] for e in summary.json()} == {'alice', 'bob'}
        viewer = repo.store.identity('Viewer')
        for path in ('/api/v1/experiments', '/api/v1/experiments?summary=true'):
            assert client.get(path, headers={'Authorization': 'Bearer ' + viewer['token']}).json() == client.get(path).json()
        for e in expected:
            assert client.get('/api/v1/experiments/' + e['id']).json() == e
        assert client.get('/api/v1/experiments/missing').status_code == 404
        assert client.get('/api/v1/experiments?summary=invalid').status_code == 422
    with repo.store.db() as db:
        assert [tuple(r) for r in db.execute('SELECT * FROM experiments ORDER BY id')] == before


def test_post_full_response_and_idempotence(lab):
    body = {'fly_id': lab.fly['id']}
    headers = {'Idempotency-Key': 'summary-compatibility'}
    first = lab.client.post('/api/v1/experiments', json=body, headers=headers)
    retry = lab.client.post('/api/v1/experiments', json=body, headers=headers)
    assert first.status_code == retry.status_code == 202
    assert first.json() == retry.json()
    e = first.json()
    assert {'subjects', 'conditions', 'reports', 'comparison', 'created'} <= e.keys()
    assert lab.client.get('/api/v1/experiments/' + e['id']).json() == e
    assert lab.client.get('/api/v1/experiments').json() == [e]
    assert lab.client.get('/api/v1/experiments?summary=false').json() == [e]
    assert lab.client.get('/api/v1/experiments?summary=true').json() == [{k: e[k] for k in FIELDS}]
    assert lab.client.post('/api/v1/experiments', json=body | {'seeds': [43]}, headers=headers).status_code == 422
    assert lab.executor.calls == []


def reports_with_points(count):
    profile = {'id': 'payload-fixture', 'backend_id': 'fixture', 'model_id': 'fixture',
               'sensor_id': 'fixture', 'readout_id': 'fixture', 'embodiment_id': 'fixture',
               'ready': True, 'hashes': {}, 'capabilities': ['fixture']}
    scene = {'id': 'fixture', 'size': 80, 'spawns': [[0, 0, 0]], 'obstacles': [],
             'food': [{'id': 'food', 'position': [1, 1, 0], 'initial': 1}], 'mirror': 1,
             'chemical_policy': 'fixture', 'cue_on_seconds': 0, 'cue_off_seconds': None}
    return [PhenotypeReport.model_validate({
        'schema_version': 'probe-report/v2', 'fly_id': f'{i:032x}', 'artifact_id': f'{i:064x}',
        'condition_key': 'c' * 64, 'probe_id': 'gradient-v2', 'seed': 42, 'duration_seconds': 3,
        'status': 'complete', 'receipt_sha256': 'a' * 64, 'profile': profile, 'scene': scene,
        'metrics': {'path_length_mm': 3, 'food_latency_seconds': None},
        'trajectory': [{'time': 3 * p / (count - 1), 'x': p / (count - 1), 'y': 0, 'yaw': 0} for p in range(count)],
        'neural_trace': [{'time': 3 * p / (count - 1), 'drive_left': 0.1, 'drive_right': 0.2} for p in range(count)]
    }).model_dump() for i in range(3)]


def test_payload_bytes_independent_of_tenfold_report_growth(repo):
    insert(repo.store, 1)
    sizes = []
    with client_for(repo) as client:
        for points in (100, 1000):
            reports = reports_with_points(points)
            comparison = compare_reports(reports).model_dump()
            with repo.store.db() as db:
                db.execute("UPDATE experiments SET status='complete',reports=?,comparison=?",
                           (canonical(reports).decode(), canonical(comparison).decode()))
            full = client.get('/api/v1/experiments')
            summary = client.get('/api/v1/experiments?summary=true')
            assert full.status_code == summary.status_code == 200
            assert 'content-encoding' not in full.headers and 'content-encoding' not in summary.headers
            assert full.json()[0]['reports'] == reports
            assert summary.json() == [{k: full.json()[0][k] for k in FIELDS}]
            sizes.append({'points_per_report': points, 'report_count': 3,
                          'trajectory_points': points * 3, 'neural_trace_points': points * 3,
                          'stored_reports_json_bytes': len(canonical(reports)),
                          'full_response_bytes': len(full.content), 'summary_response_bytes': len(summary.content)})
        assert sizes[0]['summary_response_bytes'] == sizes[1]['summary_response_bytes']
        assert sizes[1]['full_response_bytes'] > sizes[0]['full_response_bytes'] * 8
        reduction = 1 - sizes[1]['summary_response_bytes'] / sizes[1]['full_response_bytes']
        assert reduction >= 0.95
        record({'check': 'payload', 'encoding': 'uncompressed UTF-8 HTTP response body',
                'fixture': 'synthetic schema-validated reports; no simulation or scientific claim',
                'sizes': sizes, 'large_fixture_reduction_fraction': reduction})
