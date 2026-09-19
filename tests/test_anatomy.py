import json

from fastapi.testclient import TestClient

from flyarena.anatomy import build_anatomy
from flyarena.api import create_app
from flyarena.auth import AuthConfig
from flyarena.store import Store


def test_soma_export_preserves_source_coordinates_and_counts_absent_positions(tmp_path):
    (tmp_path / 'manifest.json').write_text(json.dumps({'sha256': 'a' * 64}))
    positions = [[0, 0, 0], [-12, 1.25, 99], None, [1, 2], ['1', 2, 3], [1, True, 3]]
    (tmp_path / 'neurons.json').write_text(json.dumps([
        {'id': str(i), 'position': p} for i, p in enumerate(positions)]))
    result = build_anatomy(tmp_path)
    assert result['connectome_sha256'] == 'a' * 64
    assert result['positions'] == [0, 0, 0, -12, 1.25, 99]
    assert result['neuron_count'] == 6
    assert result['position_count'] == 2
    assert result['missing_position_count'] == 4
    assert 'activity' not in result


def test_anatomy_api_reads_metadata_without_loading_or_simulating_the_brain(tmp_path, monkeypatch):
    data = tmp_path / 'data'
    graph = data / 'connectome'
    graph.mkdir(parents=True)
    (graph / 'manifest.json').write_text(json.dumps({'sha256': 'b' * 64}))
    (graph / 'neurons.json').write_text(json.dumps([{'id': '1', 'position': [10, 20, 30]}]))
    monkeypatch.setattr('flyarena.api.DATA', data)

    def no_brain():
        raise AssertionError('Anatomical display must not load the simulation graph')

    monkeypatch.setattr('flyarena.api.Connectome', no_brain)
    app = create_app(with_worker=False, store=Store(tmp_path / 'var'), auth_config=AuthConfig())
    with TestClient(app) as client:
        response = client.get('/api/v1/connectome/anatomy')
        assert response.status_code == 200
        assert response.json()['connectome_sha256'] == 'b' * 64
        assert response.json()['positions'] == [10, 20, 30]
        # Static anatomy is reused; replay activity never enters this cache.
        (graph / 'neurons.json').unlink()
        assert client.get('/api/v1/connectome/anatomy').json() == response.json()
