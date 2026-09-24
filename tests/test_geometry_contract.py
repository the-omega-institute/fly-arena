"""The arena-geometry-v1 envelope is shared without rewriting seeded scenes."""
import copy
import json
import math
import sys
from pathlib import Path

import pytest

# Keep this test tied to the checkout under test even when the developer's
# virtualenv contains an editable install of another fly-arena checkout.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from flyarena.geometry import GeometryError, validate_arena_scene, validate_probe_scene
from flyarena.scenarios import MAPS, arena_scene, scenario
from flyarena.common import digest

FIXTURE = json.loads((Path(__file__).parent / "fixtures/geometry_contract.json").read_text())


def assert_geometry_equal(actual, expected, path="scene"):
    """Tolerate libm rounding only; preserve keys, order, counts and labels."""
    if isinstance(expected, dict):
        assert isinstance(actual, dict), path
        assert actual.keys() == expected.keys(), path
        for key in expected:
            assert_geometry_equal(actual[key], expected[key], f"{path}.{key}")
    elif isinstance(expected, (list, tuple)):
        assert isinstance(actual, (list, tuple)), path
        assert len(actual) == len(expected), path
        for index, (value, reference) in enumerate(zip(actual, expected)):
            assert_geometry_equal(value, reference, f"{path}[{index}]")
    elif isinstance(expected, float):
        assert isinstance(actual, float), path
        assert math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-12), path
    else:
        assert type(actual) is type(expected), path
        assert actual == expected, path


def scene_payload(scene):
    payload = {key: value for key, value in scene.items() if key != "sha256"}
    # Hash the exact bytes for this scene, not another platform's libm output.
    assert scene["sha256"] == digest(payload)
    return payload


def test_contract_fixture_covers_all_maps_and_seeds():
    assert FIXTURE["contract"]["id"] == "arena-geometry-v1"
    assert FIXTURE["pin_platform"] == "darwin"
    assert set(FIXTURE["maps"]) == set(MAPS) and len(FIXTURE["maps"]) == 11
    for map_id, seeds in FIXTURE["maps"].items():
        for seed, expected in seeds.items():
            actual = scenario(map_id, int(seed))
            validate_arena_scene(actual)
            expected_payload = scene_payload(expected)
            assert_geometry_equal(scene_payload(actual), expected_payload)
            for profile in ("legacy-v1", "sensorimotor-research-v2"):
                reference = copy.deepcopy(expected_payload)
                if profile == "sensorimotor-research-v2":
                    reference.update(geometry_version="arena-offaxis-v2", bridge_profile=profile)
                    for spawn in reference["spawns"]:
                        spawn[2] += .65
                # Keep frozen bridge pins exact while comparing generated
                # geometry with the same platform tolerance as the base scene.
                assert digest(reference) == FIXTURE["bridge_digests"][profile][map_id][seed]
                assert_geometry_equal(scene_payload(arena_scene(map_id, int(seed), profile)), reference)


@pytest.mark.skipif(
    sys.platform != "darwin",
    reason="scene digests are pinned on the macOS deployment platform; cross-platform bitwise equality is not promised (docs/OPERATIONS.md)",
)
@pytest.mark.parametrize("profile", ["legacy-v1", "sensorimotor-research-v2"])
@pytest.mark.parametrize("map_id,seed", [
    (map_id, seed) for map_id in sorted(MAPS) for seed in FIXTURE["maps"][map_id]
])
def test_generated_bridge_scene_digest_matches_macos_pin(map_id, seed, profile):
    assert arena_scene(map_id, int(seed), profile)["sha256"] == FIXTURE["bridge_digests"][profile][map_id][seed]


def test_geometry_comparison_accepts_roundoff_and_serialized_tuples():
    assert_geometry_equal(
        {"position": (math.nextafter(.8314696123025453, math.inf), 5e-13, 1e6 + 5e-4)},
        {"position": [.8314696123025453, 0.0, 1e6]},
    )


@pytest.mark.parametrize("actual,expected", [
    ({"id": "other"}, {"id": "food-0"}),
    ({"shape": "box"}, {"shape": "ellipsoid"}),
    ({"extra": 0}, {}),
    ({}, {"missing": 0}),
    ([1, 2], [1]),
    ([2, 1], [1, 2]),
    (1000000001, 1000000000),
    (1.0, 1),
    (True, 1),
    (1.01, 1.0),
    (2e-12, 0.0),
    (float("nan"), 0.0),
    (float("inf"), 0.0),
])
def test_geometry_comparison_rejects_contract_changes(actual, expected):
    with pytest.raises(AssertionError):
        assert_geometry_equal(actual, expected)


def test_platform_roundoff_changes_hash_but_not_geometry_contract():
    reference = FIXTURE["maps"]["enclosure"]["42"]
    changed = copy.deepcopy(reference)
    changed["obstacles"][7]["quaternion"][3] = math.nextafter(
        changed["obstacles"][7]["quaternion"][3], math.inf
    )
    changed["sha256"] = digest({key: value for key, value in changed.items() if key != "sha256"})
    assert changed["sha256"] != reference["sha256"]
    assert_geometry_equal(scene_payload(changed), scene_payload(reference))
    changed["sha256"] = reference["sha256"]
    with pytest.raises(AssertionError):
        scene_payload(changed)


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
