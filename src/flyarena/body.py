from __future__ import annotations

import os
os.environ.setdefault("MPLCONFIGDIR", str(__import__("pathlib").Path(__file__).resolve().parents[2] / "var/cache/matplotlib"))

import mujoco as mj
import numpy as np

from flygym.compose.world import FlatGroundWorld
from flygym.simulation import Simulation
from flygym.utils.math import Rotation3D
from flygym_demo.complex_terrain.common import make_locomotion_fly, apply_locomotion_action
from flygym_demo.complex_terrain.hybrid_controller import HybridControllerObservation
from flygym_demo.complex_terrain.turning_controller import HybridTurningController

from .scenarios import RULES


class Bodies:
    """All contestants share exactly one authoritative MuJoCo model and data."""
    def __init__(self, scene: dict, count: int, seed: int):
        self.names = [f"fly-{i}" for i in range(count)]
        world = FlatGroundWorld(half_size=scene["size"])
        for index, obstacle in enumerate(scene["obstacles"]):
            world.mjcf_root.worldbody.add_geom(name=f"obstacle-{index}", type=mj.mjtGeom.mjGEOM_BOX,
                pos=obstacle["position"], size=np.array(obstacle["size"]) / 2,
                contype=4, conaffinity=3, friction=[1, .02, .0001])
        for index, name in enumerate(self.names):
            fly = make_locomotion_fly(name)
            x, y, yaw = scene["spawns"][index]
            world.add_fly(fly, (x, y, .25), Rotation3D("quat", (np.cos(yaw / 2), 0, 0, np.sin(yaw / 2))))
        self.sim = Simulation(world, timestep=RULES["physics_dt"])
        self.model, self.data = self.sim.mj_model, self.sim.mj_data
        self.controllers = []
        self.body_ids, self.head_ids, self.geom_slots = [], [], {}
        for slot, name in enumerate(self.names):
            c = HybridTurningController(timestep=RULES["physics_dt"])
            # Same initial CPG phases in each slot; independent, no shared state.
            c.reset(seed=seed)
            self.controllers.append(c)
            self.body_ids.append(mj.mj_name2id(self.model, mj.mjtObj.mjOBJ_BODY, f"{name}/c_thorax"))
            self.head_ids.append(mj.mj_name2id(self.model, mj.mjtObj.mjOBJ_BODY, f"{name}/c_head"))
        for i in range(self.model.ngeom):
            name = mj.mj_id2name(self.model, mj.mjtObj.mjOBJ_GEOM, i) or ""
            for slot, fly_name in enumerate(self.names):
                if name.startswith(fly_name + "/"):
                    self.geom_slots[i] = slot
                    self.model.geom_contype[i] = 1 << slot
                    self.model.geom_conaffinity[i] = (3 ^ (1 << slot)) | 4
        if min(self.body_ids + self.head_ids) < 0:
            raise ValueError("Body manifest does not match expected thorax/head segments")
        mj.mj_forward(self.model, self.data)
        self.drives = np.zeros((count, 2))
        self.tick = 0

    def pose(self, slot: int) -> tuple[np.ndarray, np.ndarray]:
        body = self.body_ids[slot]
        return self.data.xpos[body].copy(), self.data.xmat[body].reshape(3, 3).copy()

    def mouth(self, slot: int) -> np.ndarray:
        # Frozen engineered mouth point in the anatomically registered head frame.
        head = self.head_ids[slot]
        return self.data.xpos[head] + self.data.xmat[head].reshape(3, 3) @ np.array([.35, 0, -.2])

    def antennae(self, slot: int) -> tuple[np.ndarray, np.ndarray]:
        head = self.head_ids[slot]
        rot = self.data.xmat[head].reshape(3, 3)
        pos = self.data.xpos[head]
        return pos + rot @ np.array([.45, .45, 0]), pos + rot @ np.array([.45, -.45, 0])

    def step(self, drives: np.ndarray):
        # Observe all flies before writing any controls; advance the shared world once.
        observations = [HybridControllerObservation.from_sim(self.sim, name) for name in self.names]
        for slot, name in enumerate(self.names):
            self.drives[slot] = np.clip(drives[slot], 0, 1.5)
            action = self.controllers[slot].step(self.drives[slot], observations[slot])
            apply_locomotion_action(self.sim, name, action)
        self.sim.step()
        self.tick += 1
        if self.tick % 100 == 0 and (not np.isfinite(self.data.qpos).all() or
                not np.isfinite(self.data.qvel).all() or np.max(np.abs(self.data.qvel)) > 1e6):
            raise FloatingPointError("Unstable or non-finite physical state")

    def contact_between_flies(self) -> bool:
        for contact in self.data.contact:
            a, b = self.geom_slots.get(int(contact.geom1)), self.geom_slots.get(int(contact.geom2))
            if a is not None and b is not None and a != b and contact.dist <= 0:
                return True
        return False

    def rendering_manifest(self) -> dict:
        # MuJoCo's compiled mesh frame is used with actual geom_xpos/xmat poses.
        # The viewer never synthesizes leg animation from a fly's center position.
        meshes, geoms = {}, []
        for geom, slot in self.geom_slots.items():
            mesh = int(self.model.geom_dataid[geom])
            if self.model.geom_type[geom] != mj.mjtGeom.mjGEOM_MESH or mesh < 0:
                continue
            key = str(mesh)
            if key not in meshes:
                va, vn = self.model.mesh_vertadr[mesh], self.model.mesh_vertnum[mesh]
                fa, fn = self.model.mesh_faceadr[mesh], self.model.mesh_facenum[mesh]
                meshes[key] = {"vertices": self.model.mesh_vert[va:va+vn].round(6).flatten().tolist(),
                               "faces": self.model.mesh_face[fa:fa+fn].flatten().tolist()}
            name = mj.mj_id2name(self.model, mj.mjtObj.mjOBJ_GEOM, geom)
            geoms.append({"id": geom, "slot": slot, "name": name, "mesh": key})
        self.replay_geoms = np.array([g["id"] for g in geoms])
        return {"meshes": meshes, "geoms": geoms, "unit": "mm", "up": "Z", "quaternion": "wxyz",
                "source": "FlyGym 2.1.0 NeuroMechFly simplified anatomical mesh"}

    def snapshot(self) -> dict:
        poses = []
        q = np.empty(4)
        for geom in self.replay_geoms:
            mj.mju_mat2Quat(q, self.data.geom_xmat[geom])
            poses.append([*self.data.geom_xpos[geom].round(5).tolist(), *q.round(6).tolist()])
        return {"tick": self.tick, "time": round(self.tick * RULES["physics_dt"], 6),
                "poses": poses, "positions": [self.pose(i)[0].round(5).tolist() for i in range(len(self.names))]}

    def checkpoint(self) -> dict:
        signature = mj.mjtState.mjSTATE_INTEGRATION
        state = np.empty(mj.mj_stateSize(self.model, signature))
        mj.mj_getState(self.model, self.data, state, signature)
        result = {"integration": state, "tick": np.array(self.tick), "drives": self.drives.copy()}
        for i, c in enumerate(self.controllers):
            for name in ["retraction_correction", "stumbling_correction", "retraction_persistence_counter"]:
                result[f"{i}_{name}"] = getattr(c, name).copy()
            result[f"{i}_phases"] = c.cpg_network.curr_phases.copy()
            result[f"{i}_magnitudes"] = c.cpg_network.curr_magnitudes.copy()
        return result
