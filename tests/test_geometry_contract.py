"""The arena-geometry-v1 envelope is shared without rewriting seeded scenes."""
import hashlib
import json
from pathlib import Path

import pytest

from flyarena.geometry import GeometryError, validate_arena_scene, validate_probe_scene
from flyarena.scenarios import MAPS, arena_scene, scenario
from flyarena.common import digest

FIXTURE = json.loads((Path(__file__).parent / "fixtures/geometry_contract.json").read_text())


def test_contract_fixture_covers_all_maps_and_seeds():
    assert FIXTURE["contract"]["id"] == "arena-geometry-v1"
    assert set(FIXTURE["maps"]) == set(MAPS) and len(FIXTURE["maps"]) == 11
    for map_id, seeds in FIXTURE["maps"].items():
        for seed, expected in seeds.items():
            actual = scenario(map_id, int(seed))
            validate_arena_scene(actual)
            assert actual == expected
            assert actual["sha256"] == digest({k: v for k, v in actual.items() if k != "sha256"})
            for profile in ("legacy-v1", "sensorimotor-research-v2"):
                assert arena_scene(map_id, int(seed), profile)["sha256"] == FIXTURE["bridge_digests"][profile][map_id][seed]


def test_probe_fixture_is_valid_and_digest_pinned():
    for probe, seeds in FIXTURE["probes"].items():
        for seed, scene in seeds.items():
            validate_probe_scene(scene)
            assert digest(scene) == FIXTURE["probe_digests"][probe][seed]


@pytest.mark.parametrize("bad", [
    {"size": 1, "spawns": [[0, 0, 0]], "obstacles": [{"position": [0, 0, 0], "size": [1, 0, 1]}], "food": []},
    {"size": 1, "spawns": [[0, 0, 0]], "obstacles": [{"position": [0, 0, 0], "size": [1, 1, 1], "quaternion": [0, 0, 0, 0]}], "food": []},
    {"size": 1, "spawns": [[0, 0, 0]], "obstacles": [{"position": [0, 0, 0], "size": [1, 1, 1], "shape": "cylinder"}], "food": []},
])
def test_malformed_geometry_is_rejected(bad):
    with pytest.raises((GeometryError, ValueError)):
        validate_arena_scene(bad)


def test_shared_invalid_obstacles():
    from flyarena.geometry import validate_obstacle
    for obstacle in FIXTURE["invalid_obstacles"]:
        with pytest.raises(GeometryError):
            validate_obstacle(obstacle)
