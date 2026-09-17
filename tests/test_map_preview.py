"""The visible setup is the same seeded layout used by the match runner."""
import pytest
from fastapi.testclient import TestClient
from flyarena.api import create_app
from flyarena.auth import AuthConfig
from flyarena.scenarios import MAPS, arena_scene
from flyarena.store import Store

@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(with_worker=False, store=Store(tmp_path), auth_config=AuthConfig())) as client:
        yield client

@pytest.mark.parametrize('map_id', list(MAPS))
@pytest.mark.parametrize('profile', ['legacy-v1', 'sensorimotor-research-v2'])
def test_preview_matches_runner_layout_without_loading_a_brain(client, map_id, profile):
    response=client.get(f'/api/v1/maps/{map_id}/preview',params={'seed':91,'bridge_profile':profile})
    assert response.status_code==200
    assert response.json()==arena_scene(map_id,91,profile)
    assert response.json()['food']!=client.get(f'/api/v1/maps/{map_id}/preview?seed=92').json()['food']
    assert client.get('/api/v1/matches').json()==[]

@pytest.mark.parametrize('path,status',[
    ('unknown/preview',404),('orchard/preview?seed=-1',422),
    ('orchard/preview?seed=2147483648',422),('orchard/preview?seed=1.5',422),
    ('orchard/preview?bridge_profile=unknown',422),
])
def test_invalid_layout_inputs(client,path,status):
    assert client.get('/api/v1/maps/'+path).status_code==status


def test_scarce_food_is_shared_finite_and_available_to_contests(client):
    from flyarena.contracts import MatchRequest, TournamentRequest
    layout=client.get('/api/v1/maps/scarcity/preview?seed=42').json()
    orchard=client.get('/api/v1/maps/orchard/preview?seed=42').json()
    assert sum(f['initial'] for f in layout['food'])==2
    assert sum(f['initial'] for f in orchard['food'])==50
    assert len(layout['food'])==1 and len(layout['spawns'])==2
    assert layout['spawns'][0][:2]==[-v for v in layout['spawns'][1][:2]]
    ids=['a'*32,'b'*32]
    assert MatchRequest(map_id='scarcity',fly_ids=ids).mode=='contest'
    assert TournamentRequest(name='Oasis',map_id='scarcity',fly_ids=ids).map_id=='scarcity'
    with pytest.raises(ValueError,match='ring'):
        MatchRequest(map_id='scarcity',mode='sumo',fly_ids=ids)
