from __future__ import annotations

import copy
import numpy as np

from .common import digest

MAPS = {
    "orchard": {
        "id": "orchard", "name": "琥珀果园", "english": "Amber Orchard",
        "description": "开放地形，双侧气味，争夺散落的食物。", "size": 28,
        "color": "#eebd70", "spawns": [[-7, -1, 0], [7, 1, 3.141592653589793]],
        "obstacles": [], "food": [[0, 0], [-3, 5], [3, -5], [6, 6], [-6, -6]],
        "modes": ["forage", "contest"],
    },
    "maze": {
        "id": "maze", "name": "分岔花园", "english": "Forking Garden",
        "description": "静态障碍改变路线；气味采用公开的解析扩散场。", "size": 28,
        "color": "#aca5d8", "spawns": [[-8, 0, 0], [8, 0, 3.141592653589793]],
        "obstacles": [{"position": [-3, 3, 1.5], "size": [1, 7, 3]},
                      {"position": [3, -3, 1.5], "size": [1, 7, 3]}],
        "food": [[0, 0], [0, 7], [0, -7], [8, 6], [-8, -6]],
        "modes": ["forage", "contest"],
    },
    "scarcity": {
        "id": "scarcity", "name": "最后的绿洲", "english": "Last Oasis",
        "description": "只有一个共享食物点，共 2 单位；吃完不再补充，气味随剩余食物减弱。", "size": 18,
        "color": "#d49a79", "spawns": [[-4, -.6, 0], [4, .6, 3.141592653589793]],
        "obstacles": [], "food": [[0, 0]], "food_units": 2.0,
        "modes": ["forage", "contest"],
    },
    "ring": {
        "id": "ring", "name": "微观擂台", "english": "Micro Sumo",
        "description": "共同物理世界中的接触推挤；胸部越过圆环边界即离台。", "size": 24,
        "color": "#8fcdba", "spawns": [[-5, .6, 0], [5, -.6, 3.141592653589793]],
        "obstacles": [], "food": [[0, 0]], "ring_radius": 10,
        "modes": ["forage", "contest", "sumo"],
    },
}

RULES = {
    "id": "arena-ground-v1", "physics_dt": .0001, "neural_dt_ms": .1,
    "sense_ticks": 100, "snapshot_ticks": 500, "food_initial_units": 10.0,
    "food_intake_per_second": 8.0, "mouth_radius_mm": 1.1,
    "odor_sigma_mm": 5.0, "odor_policy": "analytic Gaussian, penetrates walls",
    "resource_tie": "equal division among eligible mouths each integer physics tick",
    "sumo": "simultaneous thorax boundary exits are draw; no exit at time limit is draw",
    "energy": "game reserve: starts 100, drive costs 2 units/s, feeding adds intake units; zero reserve closes motor output",
}


def scenario(map_id: str, seed: int) -> dict:
    result = copy.deepcopy(MAPS[map_id])
    rng = np.random.default_rng(seed)
    # Only food is jittered; valid spawn geometry is identical across paired slots.
    result["food"] = [dict(id=f"food-{i}", position=[float(x + rng.uniform(-.25, .25)),
                        float(y + rng.uniform(-.25, .25)), .15], initial=result.get("food_units", 10.0))
                      for i, (x, y) in enumerate(result["food"])]
    result["sha256"] = digest(result)
    return result


def arena_scene(map_id: str, seed: int, bridge_profile: str = "legacy-v1") -> dict:
    if bridge_profile == "legacy-v1":
        return scenario(map_id, seed)
    if bridge_profile != "sensorimotor-research-v2":
        raise ValueError("Unknown arena bridge profile")
    result = scenario(map_id, seed)
    result.pop("sha256")
    result["geometry_version"] = "arena-offaxis-v2"
    result["bridge_profile"] = bridge_profile
    # Fixed mirrored headings are independent of targets and contestant identity.
    for spawn in result["spawns"]:
        spawn[2] += .65
    result["sha256"] = digest(result)
    return result


def receipt_scene(map_id: str, seed: int, bridge_profile: str, source_sha256: str | None) -> dict:
    result = arena_scene(map_id, seed, bridge_profile)
    # Pinned historical source at commit 73d1472, before the ring spawn offset.
    # No arbitrary receipt geometry is accepted as a substitute for reconstruction.
    if (bridge_profile == "legacy-v1" and map_id == "ring" and source_sha256 ==
            "a6da0a58972be8789340fe542f77aeefaa56c682d275cc43f7fae720d21957b2"):
        result.pop("sha256")
        result["spawns"] = [[-5, 0, 0], [5, 0, 3.141592653589793]]
        result["sha256"] = digest(result)
    return result
