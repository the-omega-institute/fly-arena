from __future__ import annotations

import copy
import math
import numpy as np

from .common import digest

VISUAL_OBSERVATION = {
    "id": "raycast_engineered_bilateral_head_v2",
    "origins": "left and right antenna offsets in the head frame",
    "directions": "head-local forward-left and forward-right, 45 degrees from forward",
    "response": "positive cosine of target direction times exp(-distance_mm / 16) times remaining fraction; clipped per channel to [0,1]",
    "occlusion": "MuJoCo ray must first hit the food geom; own body excluded",
    "scope": "Engineering binocular observation, not a calibrated retina or compound-eye model",
}

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
    "terrarium": {
        "id": "terrarium", "name": "腐果林地", "english": "Rotting Fruit Grove",
        "description": "腐叶与果壳之间的缓坡、叶桥和多条觅食路线。", "size": 28,
        "color": "#789c62", "habitat": "forest-floor",
        "spawns": [[-11.5, -.8, 0], [11.5, .8, 3.141592653589793]],
        # The leaf bridge is 0.8 mm high. Two 8 mm ramps meet its edge at
        # the same height (about 5.7 degrees), leaving the upper and lower
        # y lanes open as alternate ground routes.
        "obstacles": [
            {"position": [0, 0, .4], "size": [4, 5, .8], "material": "leaf", "color": "#6f9f58"},
            {"position": [-6, 0, .34], "size": [8.05, 5, .12], "quaternion": [.99875, 0, -.04998, 0], "material": "leaf", "color": "#6f9f58"},
            {"position": [6, 0, .34], "size": [8.05, 5, .12], "quaternion": [.99875, 0, .04998, 0], "material": "leaf", "color": "#6f9f58"},
            {"position": [-4.5, -6, .65], "size": [2.2, 1.6, 1.3], "shape": "ellipsoid", "material": "rock", "color": "#695844"},
            {"position": [4.5, 6, .65], "size": [2.2, 1.6, 1.3], "shape": "ellipsoid", "material": "rock", "color": "#695844"},
            {"position": [-5.5, 6.5, .42], "size": [1.8, 1.5, .8], "shape": "ellipsoid", "material": "fruit", "color": "#b86c3d"},
            {"position": [5.5, -6.5, .42], "size": [1.8, 1.5, .8], "shape": "ellipsoid", "material": "fruit", "color": "#b86c3d"},
        ],
        "food": [[-8, 5], [8, -5], [-10, 8], [10, -8], [-2, 10], [2, -10]],
        "modes": ["forage", "contest"],
    },
    "enclosure": {
        "id": "enclosure", "name": "封闭果园", "english": "Enclosed Orchard",
        "description": "实体围挡保留探索空间；果蝇必须靠自己的神经输出继续觅食，也可能碰壁或停滞。",
        "size": 28, "color": "#90a878", "habitat": "forest-floor",
        "spawns": [[-7, -1, 0], [7, 1, math.pi]],
        # Overlapping tangent segments form a closed physical perimeter.
        # The renderer consumes these same obstacles, including their rotations.
        # No position wrapping, scripted steering or neural reset at the wall.
        "obstacles": [
            {"position": [round(12.5 * math.cos(i * math.pi / 8), 12),
                          round(12.5 * math.sin(i * math.pi / 8), 12), 2.0],
             "size": [5.2, .8, 4.0],
             "quaternion": [math.cos((i * math.pi / 8 + math.pi / 2) / 2), 0, 0,
                            math.sin((i * math.pi / 8 + math.pi / 2) / 2)],
             "material": "rock", "color": "#8b8167"}
            for i in range(16)
        ] + [
            {"position": [-5, 7, .5], "size": [2.4, 1.6, 1], "shape": "ellipsoid", "material": "fruit", "color": "#b86c3d"},
            {"position": [5, -7, .5], "size": [2.4, 1.6, 1], "shape": "ellipsoid", "material": "fruit", "color": "#b86c3d"},
            {"position": [-7, 4, .1], "size": [4, 2, .2], "material": "leaf", "color": "#6f9f58"},
            {"position": [7, -4, .1], "size": [4, 2, .2], "material": "leaf", "color": "#6f9f58"},
        ],
        "food": [[0, 0], [-3, 5], [3, -5], [6, 6], [-6, -6]],
        "modes": ["forage", "contest"],
    },
}

# Additional arenas leave historical layouts unchanged. Every solid is shared
# by MuJoCo collision/raycast observations and the browser renderer.
MAPS.update({
    "canopy": {
        "id":"canopy", "name":"叶桥争食场", "english":"Canopy Crossroads",
        "description":"两侧缓坡通往中央叶台，地面可从南北绕行；中央与外围食物有限，形成抢占与换路的选择。视觉受实体遮挡，气味仍可穿墙。",
        "size":32, "color":"#77ad85", "habitat":"forest-floor",
        "spawns":[[-12,0,0],[12,0,math.pi]],
        "obstacles": copy.deepcopy(MAPS["terrarium"]["obstacles"][:3]) + [
            {"position":[x,y,z],"size":size,"material":material,"shape":shape,"color":color}
            for x,y,z,size,material,shape,color in [
                (-6,5,1.5,[5,1.2,3],"rock","box","#80715b"),
                (6,-5,1.5,[5,1.2,3],"rock","box","#80715b"),
                (-2,-7,.8,[3,2,1.6],"fruit","ellipsoid","#b56f45"),
                (2,7,.8,[3,2,1.6],"fruit","ellipsoid","#b56f45"),
                (-10,9,.65,[2,3,1.3],"rock","ellipsoid","#736e59"),
                (10,-9,.65,[2,3,1.3],"rock","ellipsoid","#736e59"),
                (-7,-9,.1,[5,3,.2],"leaf","box","#6c965b"),
                (7,9,.1,[5,3,.2],"leaf","box","#6c965b"),
            ]
        ],
        "food":[[0,0],[-6,-7],[6,7],[-10,6],[10,-6]],
        "food_heights":[.95,.15,.15,.15,.15],"food_units":4.,
        "modes":["forage","contest"],
    },
    "switchback": {
        "id":"switchback", "name":"果壳回廊", "english":"Husk Switchbacks",
        "description":"错位果壳屏障制造视线遮挡与绕行通路；分散的小食物点会耗尽，需要离开原地继续探索。气味穿墙，不等同真实扩散。",
        "size":32,"color":"#bc9463","habitat":"forest-floor",
        "spawns":[[-12,-4,0],[12,4,math.pi]],
        "obstacles":[
            {"position":[-4,3,1.5],"size":[1.2,12,3],"material":"fruit","color":"#976340"},
            {"position":[4,-3,1.5],"size":[1.2,12,3],"material":"fruit","color":"#976340"},
            {"position":[-8,-8,1.5],"size":[7,1.2,3],"material":"rock","color":"#766b58"},
            {"position":[8,8,1.5],"size":[7,1.2,3],"material":"rock","color":"#766b58"},
            {"position":[0,0,.7],"size":[2,3,1.4],"shape":"ellipsoid","material":"fruit","color":"#bb7945"},
            {"position":[-9,8,.6],"size":[3,2,1.2],"shape":"ellipsoid","material":"rock","color":"#817763"},
            {"position":[9,-8,.6],"size":[3,2,1.2],"shape":"ellipsoid","material":"rock","color":"#817763"},
            {"position":[-1,-10,.1],"size":[5,3,.2],"material":"leaf","color":"#74975e"},
            {"position":[1,10,.1],"size":[5,3,.2],"material":"leaf","color":"#74975e"},
        ],
        "food":[[-9,-3],[9,3],[0,-6],[0,6],[-8,11],[8,-11]],
        "food_units":2.,"modes":["forage","contest"],
    },
    "blank": {
        "id":"blank","name":"WT 无食物对照","english":"WT Blank Control",
        "description":"没有食物和障碍，观察同一模型无食物刺激时的自发活动与运动；不用于觅食得分比较。",
        "size":28,"color":"#93a7ab","spawns":[[-7,-1,0],[7,1,math.pi]],
        "obstacles":[],"food":[],"modes":["forage"],
    },
})

# New task layouts have explicit observation rules; historical maps are frozen.
def _walls(half):
    return [{"position": pos, "size": size, "material": "rock", "color": "#697782"}
            for pos, size in [([-half,0,2.5],[1,2*half+1,5]),
                              ([half,0,2.5],[1,2*half+1,5]),
                              ([0,-half,2.5],[2*half+1,1,5]),
                              ([0,half,2.5],[2*half+1,1,5])]]

MAPS.update({
    "labyrinth": {
        "id":"labyrinth", "name":"折返迷宫 · 单蝇基准", "english":"Labyrinth Benchmark",
        "description":"封闭折返通道与死胡同。单蝇寻找远端食物，以首次实际口部接触计到达；未到达显示未完成。到达后继续记录脑活动与探索。",
        "size":32, "color":"#88acbf", "spawns":[[-11,-10,0],[11,10,math.pi]],
        "obstacles": _walls(14) + [
            {"position":[-5,-4,2.5],"size":[1,19,5],"material":"rock","color":"#7893a0"},
            {"position":[5,4,2.5],"size":[1,19,5],"material":"rock","color":"#7893a0"},
            {"position":[-12,1,2.5],"size":[4,1,5],"material":"rock","color":"#7893a0"},
            {"position":[12,-1,2.5],"size":[4,1,5],"material":"rock","color":"#7893a0"},
        ],
        "food":[[10,10]], "food_units":10., "modes":["forage"],
        "task":{"id":"maze-arrival-v1","goal_food":"food-0", "continue_after_goal":True, "odor_sigma_mm":18.,
                "energy":"unlimited-observation-v1", "metric":"first physical mouth contact; no arrival is null"},
    },
    "duel": {
        "id":"duel", "name":"封闭对抗场 · 领地争夺", "english":"Closed Contact Arena",
        "description":"两只果蝇在同一封闭物理世界接触、推挤并争夺中央区域。记录接触与独占中央时间；当前运动模型不含专门的攻击、抓抱或伤害动作。",
        "size":18, "color":"#cb927f", "spawns":[[-2.8,0,0],[2.8,0,math.pi]],
        "obstacles":_walls(7), "food":[], "modes":["duel"],
        "task":{"id":"contact-territory-v1", "control_radius_mm":3., "control_max_height_mm":3.,
                "energy":"unlimited-observation-v1", "metric":"exclusive center occupancy seconds sampled at 20 Hz",
                "scope":"locomotion and physical pushing; no attack or injury controller"},
    },
})

# Catalog guidance is deliberately separate from MAPS: it is not simulation
# input and must not change seeded geometry or historical receipt hashes.
# Horizons are suggested observation windows, not validated performance claims
# or admission limits. Profile readiness remains independently enforced.
MAZE_LIMITATION = (
    "Long-horizon locomotion inversion remains unresolved (issue #82); "
    "arrival time is not a valid optimization target yet."
)
MODEL_LIMITATION = (
    "Engineered sensory and locomotion models; reliable navigation and biological behavior are not qualified."
)


def _map_metadata(map_id: str, purpose: str, horizon: tuple[int, int], reason: str, *,
                  training_eligible: bool, competition_eligible: bool) -> dict:
    return {
        "supported_modes": list(MAPS[map_id]["modes"]),
        "training_eligible": training_eligible,
        "competition_eligible": competition_eligible,
        "recommended_horizon_seconds": {"min": horizon[0], "max": horizon[1]},
        "purpose": purpose,
        "scientific_status": "observation-only",
        "status_reason": reason,
    }


MAP_METADATA = {
    "orchard": _map_metadata("orchard", "Open-ground foraging and shared food consumption.", (2, 10), MODEL_LIMITATION,
                             training_eligible=True, competition_eligible=True),
    "maze": _map_metadata("maze", "Navigation around barriers and food contact along alternate routes.", (5, 30), MAZE_LIMITATION,
                          training_eligible=False, competition_eligible=False),
    "scarcity": _map_metadata("scarcity", "Resource competition for one finite shared food patch.", (2, 10), MODEL_LIMITATION,
                              training_eligible=True, competition_eligible=True),
    "ring": _map_metadata("ring", "Physical pushing, ring exits and shared food consumption.", (2, 10),
                          "Contact and ring exits are modeled contests; natural aggression is not qualified.",
                          training_eligible=True, competition_eligible=True),
    "terrarium": _map_metadata("terrarium", "Locomotion over ramps and a leaf bridge with dispersed food.", (5, 30), MODEL_LIMITATION,
                               training_eligible=True, competition_eligible=True),
    "enclosure": _map_metadata("enclosure", "Foraging and wall contact within a physical perimeter.", (5, 30), MODEL_LIMITATION,
                               training_eligible=True, competition_eligible=True),
    "canopy": _map_metadata("canopy", "Resource competition across a raised platform and ground detours.", (5, 30), MODEL_LIMITATION,
                            training_eligible=True, competition_eligible=True),
    "switchback": _map_metadata("switchback", "Navigation around staggered barriers and depletion of small food patches.", (5, 30), MAZE_LIMITATION,
                                training_eligible=False, competition_eligible=False),
    "blank": _map_metadata("blank", "Spontaneous model activity and locomotion without food input.", (2, 10),
                           "No food is present; this control cannot establish foraging performance.",
                           training_eligible=True, competition_eligible=False),
    "labyrinth": _map_metadata("labyrinth", "Exploratory maze traversal and first physical mouth contact with the goal food.", (30, 180), MAZE_LIMITATION,
                               training_eligible=False, competition_eligible=False),
    "duel": _map_metadata("duel", "Body contact and exclusive center occupancy in a shared enclosed arena.", (10, 60),
                          "Contact and territory are locomotion observations; attack, grappling and injury actions are not modeled.",
                          training_eligible=False, competition_eligible=True),
}


RULES = {
    "id": "arena-ground-contact-v2", "physics_dt": .0001, "neural_dt_ms": .1,
    "sense_ticks": 100, "snapshot_ticks": 500, "food_initial_units": 10.0,
    "food_intake_per_second": 8.0, "mouth_radius_mm": 1.1,
    "feeding_contact": "mujoco-mouth-probe-required-v1",
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
                        float(y + rng.uniform(-.25, .25)), result.get("food_heights", [.15]*len(result["food"]))[i]], initial=result.get("food_units", 10.0))
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
