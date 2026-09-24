"""Catalog guidance must not become qualification evidence or simulation input."""
import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from flyarena.api import create_app
from flyarena.auth import AuthConfig
from flyarena.common import digest
from flyarena.scenarios import MAPS, MAP_METADATA, MAZE_LIMITATION, _map_metadata, arena_scene
from flyarena.store import Store


def test_every_map_has_metadata():
    assert set(MAP_METADATA) == set(MAPS)
    for map_id, metadata in MAP_METADATA.items():
        assert metadata["supported_modes"] == MAPS[map_id]["modes"]
        assert set(metadata["supported_modes"]) <= {"forage", "contest", "sumo", "duel"}
        assert metadata["purpose"] and metadata["status_reason"]
        assert metadata["scientific_status"] in {"qualified", "observation-only"}
        horizon = metadata["recommended_horizon_seconds"]
        assert 1 <= horizon["min"] <= horizon["max"] <= 300
    # No map is declared scientifically qualified without supporting evidence.
    assert all(m["scientific_status"] == "observation-only" for m in MAP_METADATA.values())


@pytest.mark.parametrize("map_id", ["maze", "labyrinth", "switchback"])
def test_maze_arrival_is_observation_only(map_id):
    metadata = MAP_METADATA[map_id]
    assert metadata["scientific_status"] == "observation-only"
    assert "issue #82" in metadata["status_reason"]
    assert "inversion" in metadata["status_reason"]
    assert "arrival time is not a valid optimization target yet" in metadata["status_reason"]


def test_registry_copy_has_both_ui_languages():
    source = (Path(__file__).parents[1] / "web/src/shared/messages/maps.ts").read_text()
    messages = json.loads(source.removeprefix("export const mapsMessages = ").removesuffix(" as const\n"))
    for metadata in MAP_METADATA.values():
        for field in ["purpose", "status_reason"]:
            key = metadata[field]
            assert messages[key]["en"] == key
            assert messages[key]["zh-CN"] and messages[key]["zh-CN"] != key


def test_catalog_and_seeded_previews_add_metadata_without_changing_receipts(tmp_path):
    original = copy.deepcopy(MAPS)
    with TestClient(create_app(with_worker=False, store=Store(tmp_path), auth_config=AuthConfig())) as client:
        listing = client.get("/api/v1/maps")
        assert listing.status_code == 200
        assert len(listing.json()) == len(MAPS)
        for entry in listing.json():
            map_id = entry["id"]
            assert entry.pop("metadata") == MAP_METADATA[map_id]
            assert entry == MAPS[map_id]
            for profile in ["legacy-v1", "sensorimotor-research-v2"]:
                for seed in [42, 91]:
                    response = client.get(f"/api/v1/maps/{map_id}/preview", params={"seed": seed, "bridge_profile": profile})
                    assert response.status_code == 200
                    preview = response.json()
                    assert preview.pop("metadata") == MAP_METADATA[map_id]
                    assert preview == arena_scene(map_id, seed, profile)
                    scene_hash = preview.pop("sha256")
                    assert scene_hash == digest(preview)
        assert client.get("/api/v1/matches").json() == []
    assert MAPS == original


def test_guidance_changes_do_not_change_scene_hashes(monkeypatch):
    before = arena_scene("labyrinth", 42)
    monkeypatch.setitem(MAP_METADATA["labyrinth"], "purpose", "Updated observation guidance")
    assert arena_scene("labyrinth", 42) == before


@pytest.mark.parametrize("map_id", list(MAPS))
@pytest.mark.parametrize("reason", ["Revised scientific limitation copy.", MAZE_LIMITATION])
def test_eligibility_is_explicit_and_independent_of_reason(map_id, reason):
    metadata = MAP_METADATA[map_id]
    updated = _map_metadata(map_id, metadata["purpose"], (2, 10), reason,
                            training_eligible=metadata["training_eligible"],
                            competition_eligible=metadata["competition_eligible"])
    assert updated["status_reason"] == reason
    for key in ["training_eligible", "competition_eligible"]:
        assert updated[key] is metadata[key]


def test_frontend_admission_fallback_equals_backend_flags():
    source = (Path(__file__).parents[1] / 'web/src/types.ts').read_text()
    fallback = json.loads(source.split('export const mapEligibilityDefaults = ')[1].split(' as const')[0])
    assert fallback == {map_id: {key: metadata[key] for key in
                               ['training_eligible', 'competition_eligible']}
                        for map_id, metadata in MAP_METADATA.items()}
    for map_id in ['maze', 'switchback', 'labyrinth']:
        assert fallback[map_id] == {'training_eligible': False, 'competition_eligible': False}
    assert fallback['blank'] == {'training_eligible': True, 'competition_eligible': False}


def test_catalog_tolerates_missing_optional_metadata(tmp_path, monkeypatch):
    monkeypatch.delitem(MAP_METADATA, 'orchard')
    with TestClient(create_app(with_worker=False, store=Store(tmp_path), auth_config=AuthConfig())) as client:
        assert next(m for m in client.get('/api/v1/maps').json() if m['id'] == 'orchard')['metadata'] == {}
        assert client.get('/api/v1/maps/orchard/preview').json()['metadata'] == {}
