import json
import pytest
from fastapi.testclient import TestClient
from flyarena.api import create_app
from flyarena.auth import AuthConfig
from flyarena.store import Store
from flyarena.morphology import parse_swc


def test_spatial_regions_use_8nm_midpoints_and_keep_outside_unassigned():
    import numpy as np
    from flyarena.morphology import segment_regions
    volume = np.array([[[21]], [[24]]], dtype=np.uint64)
    # Source positions 0, 512, 768 become voxel midpoints 1 and 2.5 at 2048 nm.
    # Use an offset to exercise volume registration, plus a negative coordinate.
    positions = [0,0,0, 512,0,0, 768,0,0, -512,0,0]
    assert segment_regions(positions, [0,1,1,2,0,3], volume, [2048]*3) == [24,0,0]
    assert segment_regions(positions, [0,1,1,2,0,3], volume, [2048]*3, [1,0,0]) == [21,24,0]


def test_swc_preserves_branches_forest_roots_and_source_units():
    shape = parse_swc('# example\n10 1 8 16 24 2 -1\n20 3 9 17 25 1 10\n30 3 8 20 30 0.5 10\n40 0 90 80 70 1 -1')
    assert shape['positions'] == [8,16,24,9,17,25,8,20,30,90,80,70]
    assert shape['edges'] == [0,1,0,2]
    assert shape['radii'] == [2,1,.5,1]
    assert 'activity' not in shape


@pytest.mark.parametrize('text', ['1 0 0 0 0 1 99', '1 0 0 0 0 1 1', '1 0 nan 0 0 1 -1', '1 0 0 0 0 1 -1\n1 0 0 0 0 1 -1'])
def test_invalid_skeletons_do_not_invent_connections(text):
    with pytest.raises(ValueError):parse_swc(text)


def test_morphology_is_optional_static_data_and_does_not_compile_brain(tmp_path, monkeypatch):
    data=tmp_path/'data';folder=data/'connectome';folder.mkdir(parents=True)
    monkeypatch.setattr('flyarena.api.DATA',data)
    monkeypatch.setattr('flyarena.api.Connectome',lambda:pytest.fail('No simulation graph needed'))
    with TestClient(create_app(with_worker=False,store=Store(tmp_path/'var'),auth_config=AuthConfig())) as client:
        assert client.get('/api/v1/connectome/morphology').status_code==404
        value={'schema':'connectome-morphology/v1','connectome_sha256':'a'*64,'neurons':[]}
        (folder/'morphology.json').write_text(json.dumps(value))
        assert client.get('/api/v1/connectome/morphology').json()==value


def test_match_listing_omits_heavy_geometry_but_brain_endpoint_keeps_it(tmp_path, monkeypatch):
    from flyarena.services.training import TrainingService
    store=Store(tmp_path/'var');service=TrainingService(store,None)
    folder=store.root/'research'/'replay-gallery-v1';folder.mkdir(parents=True)
    snapshot={'artifact_id':'weights','connectome_sha256':'a'*64,'circuits':{'x':{'neurons':[],'edges':[]}}}
    participant={'id':'fly','artifact_id':'weights','spec':{'connectome_sha256':'a'*64},'brain_graph':snapshot}
    match={'id':'a'*32,'status':'verified','request':{'fly_ids':['fly']},'participants':[participant]}
    (folder/(match['id']+'-match.json')).write_text(json.dumps(match))
    assert 'brain_graph' not in service.bundled_replay_matches(include_brain=False)[0]['participants'][0]
    assert service.bundled_replay_match(match['id'])['participants'][0]['brain_graph']==snapshot
    with TestClient(create_app(with_worker=False,store=store,auth_config=AuthConfig())) as client:
        assert 'brain_graph' not in client.get('/api/v1/matches').json()[0]['participants'][0]
        assert client.get('/api/v1/matches/'+match['id']+'/brain/0?ids=1').json()==snapshot
