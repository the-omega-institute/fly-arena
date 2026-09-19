from __future__ import annotations

import os
os.environ.setdefault("MPLCONFIGDIR", str(__import__("pathlib").Path(__file__).resolve().parents[2] / "var/cache/matplotlib"))

import mujoco as mj
import numpy as np

from flygym.compose.world import FlatGroundWorld
from flygym.anatomy import BodySegment
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
        terrain_geoms = []
        for index, obstacle in enumerate(scene["obstacles"]):
            shape = obstacle.get("shape", "box")
            geom_type = {"box": mj.mjtGeom.mjGEOM_BOX,
                         "ellipsoid": mj.mjtGeom.mjGEOM_ELLIPSOID}.get(shape)
            if geom_type is None:
                raise ValueError(f"Unknown obstacle shape: {shape}")
            rgba = None
            if obstacle.get("color"):
                value = obstacle["color"].lstrip("#")
                if len(value) != 6:
                    raise ValueError("Obstacle color must be a six-digit hex value")
                rgba = tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)) + (1.0,)
            kwargs = dict(name=f"obstacle-{index}", type=geom_type,
                          pos=obstacle["position"], size=np.array(obstacle["size"]) / 2,
                          quat=obstacle.get("quaternion", [1, 0, 0, 0]),
                          contype=4, conaffinity=3, friction=[1, .02, .0001])
            if rgba is not None:
                kwargs["rgba"] = rgba
            terrain_geoms.append(world.mjcf_root.worldbody.add_geom(**kwargs))
        # Food sources are explicit MuJoCo targets. The same sphere is used
        # for ray visibility and for a small, mouth-only contact pair. Food
        # does not collide with legs or terrain: its conaffinity is reserved
        # for the mouth contact geoms added below.
        for food in scene["food"]:
            world.mjcf_root.worldbody.add_geom(
                name=food["id"], type=mj.mjtGeom.mjGEOM_SPHERE,
                pos=food["position"], size=(.45,), contype=8, conaffinity=0,
                rgba=(.92, .42, .16, 1.0))
        contact_sensors = {}
        for index, name in enumerate(self.names):
            fly = make_locomotion_fly(name)
            # Set masks before compilation so MuJoCo builds matching body/BVH
            # broadphase masks. Different flies and obstacles collide; self does not.
            for geoms in fly.bodyseg_to_mjcfgeom.values():
                for geom in geoms:
                    geom.contype = 1 << index
                    geom.conaffinity = (3 ^ (1 << index)) | 4
            head = fly.bodyseg_to_mjcfbody[BodySegment("c_head")]
            head.add_site(name="head_origin", pos=(0, 0, 0), size=(.01,))
            # Registered feeding contact probe. The simplified FlyGym body has
            # no articulated proboscis reaching the ground plane, so this
            # probe is aligned with the existing mouth XY rule and explicitly
            # remains a physical observation rather than a neural input.
            head.add_geom(name="mouth_contact", type=mj.mjtGeom.mjGEOM_SPHERE,
                          # The food radius is 0.45 mm and the game mouth
                          # radius is 1.1 mm, so the massless probe radius is
                          # chosen to make physical contact conserve that
                          # same threshold.
                          pos=(.35, 0, -1.0), size=(.65,),
                          # The probe is an observation sensor.  It may
                          # contact food (contype 8), but must never become
                          # a second foot that collides with the ground.
                          # Including the ground bit here changes locomotion
                          # before a fly has sensed anything.
                          # MuJoCo accepts a pair if EITHER geom's type
                          # matches the other's affinity. Giving the probe
                          # a fly bit lets walls and opponents accept it,
                          # despite its own food-only affinity. Advertise no
                          # type; food's type 8 still matches our affinity.
                          contype=0, conaffinity=8,
                          # A probe must also be massless; MuJoCo otherwise
                          # adds the invisible sphere to the fly's inertia.
                          density=0, rgba=(0, 0, 0, 0), friction=(0, 0, 0))
            x, y, yaw = scene["spawns"][index]
            world.add_fly(fly, (x, y, .25), Rotation3D("quat", (np.cos(yaw / 2), 0, 0, np.sin(yaw / 2))))
            # FlyGym 2.1 creates these sensors on the world root with unscoped
            # names. Namespace each actual sensor before attaching another fly.
            for sensor in world.legpos_to_groundcontactsensors_by_fly[name].values():
                sensor.name = f"{name}/{sensor.name}"
            contact_sensors[name] = world.legpos_to_groundcontactsensors_by_fly[name]
        world.legpos_to_groundcontactsensors_by_fly = contact_sensors
        # The hybrid gait controller filters leg forces through ground_geoms.
        # Register our terrain before Simulation maps those IDs, otherwise
        # physical obstacle collisions are invisible to stumbling correction.
        # Do this after attaching flies: FlatGroundWorld's floor sensors need
        # one ground geom, and existing obstacle contact masks/pairs must stay
        # unchanged. Food probes and other flies are not terrain.
        world.ground_geoms.extend(terrain_geoms)
        self.sim = Simulation(world, timestep=RULES["physics_dt"])
        self.model, self.data = self.sim.mj_model, self.sim.mj_data
        self.controllers = []
        self.body_ids, self.head_ids = [], []
        self.geom_slots, self.food_geom_ids = {}, {}
        self.mouth_contact_geom_ids = {}
        for slot, name in enumerate(self.names):
            c = HybridTurningController(timestep=RULES["physics_dt"])
            # Same initial CPG phases in each slot; independent, no shared state.
            c.reset(seed=seed)
            self.controllers.append(c)
            self.body_ids.append(mj.mj_name2id(self.model, mj.mjtObj.mjOBJ_BODY, f"{name}/c_thorax"))
            self.head_ids.append(mj.mj_name2id(self.model, mj.mjtObj.mjOBJ_SITE, f"{name}/head_origin"))
        for i in range(self.model.ngeom):
            name = mj.mj_id2name(self.model, mj.mjtObj.mjOBJ_GEOM, i) or ""
            if name in {food["id"] for food in scene["food"]}:
                self.food_geom_ids[name] = i
            for slot, fly_name in enumerate(self.names):
                if name.startswith(fly_name + "/"):
                    self.geom_slots[i] = slot
                    if name.endswith("/mouth_contact"):
                        self.mouth_contact_geom_ids[slot] = i
        if min(self.body_ids + self.head_ids) < 0:
            raise ValueError("Body manifest does not match expected thorax/head segments")
        if set(self.mouth_contact_geom_ids) != set(range(count)):
            raise ValueError("Body manifest does not contain one mouth contact geom per fly")
        mj.mj_forward(self.model, self.data)
        self.drives = np.zeros((count, 2))
        self.tick = 0

    def pose(self, slot: int) -> tuple[np.ndarray, np.ndarray]:
        body = self.body_ids[slot]
        return self.data.xpos[body].copy(), self.data.xmat[body].reshape(3, 3).copy()

    def mouth(self, slot: int) -> np.ndarray:
        # Frozen engineered mouth point in the anatomically registered head frame.
        head = self.head_ids[slot]
        return self.data.site_xpos[head] + self.data.site_xmat[head].reshape(3, 3) @ np.array([.35, 0, -.2])

    def antennae(self, slot: int) -> tuple[np.ndarray, np.ndarray]:
        head = self.head_ids[slot]
        rot = self.data.site_xmat[head].reshape(3, 3)
        pos = self.data.site_xpos[head]
        return pos + rot @ np.array([.45, .45, 0]), pos + rot @ np.array([.45, -.45, 0])

    def visual_food(self, slot: int, remaining: np.ndarray | None = None) -> list[float]:
        """Return bilateral, line-of-sight food observations from MuJoCo rays.

        Food is a static scene geom and obstacles are the same geoms used by
        physics. A target contributes only when its ray reaches that target
        before any obstacle or ground geom. This remains an observation until
        a visual neural encoder is independently qualified.
        """
        origins = self.antennae(slot)
        position, rotation = self.pose(slot)
        forward = rotation[:, 0][:2]
        norm = np.linalg.norm(forward)
        if norm:
            forward = forward / norm
        values = [0.0, 0.0]
        for index, (food_id, geom_id) in enumerate(self.food_geom_ids.items()):
            target = self.data.geom_xpos[geom_id].copy()
            amount = 1.0 if remaining is None else max(0.0, float(remaining[index]))
            for side, origin in enumerate(origins):
                delta = target - origin
                distance = float(np.linalg.norm(delta))
                if distance < 1e-6:
                    continue
                direction = delta / distance
                hit = np.full(1, -1, dtype=np.int32)
                ray_distance = mj.mj_ray(
                    self.model, self.data, origin, direction, None, True,
                    int(self.model.body_rootid[self.body_ids[slot]]), hit)
                if ray_distance < 0 or int(hit[0]) != geom_id:
                    continue
                unit = delta[:2] / max(distance, 1e-6)
                front = max(0.0, float(np.dot(forward, unit)))
                lateral = float(forward[0] * unit[1] - forward[1] * unit[0])
                signal = float(np.clip(amount / 10.0, 0, 1) * front * np.exp(-distance / 16.0))
                values[0 if lateral < 0 else 1] += signal
        return [float(np.clip(value, 0, 1)) for value in values]

    def food_contacts(self, slot: int) -> list[str]:
        """Return food IDs with an actual MuJoCo mouth contact."""
        mouth_geom = self.mouth_contact_geom_ids[slot]
        food_by_geom = {geom: food_id for food_id, geom in self.food_geom_ids.items()}
        touched = []
        for contact in self.data.contact:
            if contact.dist > 0:
                continue
            first, second = int(contact.geom1), int(contact.geom2)
            if first != mouth_geom and second != mouth_geom:
                continue
            other = second if first == mouth_geom else first
            if other in food_by_geom:
                touched.append(food_by_geom[other])
        return sorted(set(touched))

    def feeding_eligibility(self) -> np.ndarray:
        """Proximity and height limits with actual mouth-food contact required.

        The registered probe is an engineered feeding sensor, not an
        articulated proboscis. A fly above a patch must not eat merely because
        its XY projection overlaps that patch.
        """
        food_ids = list(self.food_geom_ids)
        targets = np.array([self.data.geom_xpos[self.food_geom_ids[f]][:2]
                            for f in food_ids]).reshape(-1, 2)
        eligible = np.zeros((len(self.names), len(food_ids)), dtype=bool)
        for slot in range(len(self.names)):
            mouth = self.mouth(slot)
            if mouth[2] >= 2.5:
                continue
            nearby = np.linalg.norm(targets - mouth[:2], axis=1) <= RULES["mouth_radius_mm"]
            if nearby.any():
                touched = set(self.food_contacts(slot))
                eligible[slot] = nearby & np.array([f in touched for f in food_ids], dtype=bool)
        return eligible

    def _environment_contacts(self, slot: int):
        """Yield actual anatomical contacts, excluding food probes and ground."""
        probe = self.mouth_contact_geom_ids[slot]
        for contact in self.data.contact:
            if contact.dist > 0:
                continue
            a, b = int(contact.geom1), int(contact.geom2)
            if self.geom_slots.get(a) == slot:
                own, other = a, b
            elif self.geom_slots.get(b) == slot:
                own, other = b, a
            else:
                continue
            if own == probe or other in self.mouth_contact_geom_ids.values():
                continue
            opponent = self.geom_slots.get(other)
            name = mj.mj_id2name(self.model, mj.mjtObj.mjOBJ_GEOM, other) or ""
            if opponent is not None and opponent != slot:
                yield contact, self.names[opponent]
            elif name.startswith("obstacle-"):
                yield contact, name

    def environment_contacts(self, slot: int) -> list[str]:
        return sorted({name for _, name in self._environment_contacts(slot)})

    def is_support_contact(self, slot: int, contact, target: str) -> bool:
        """Experimental foot/support partition; no physics or forces are changed.

        Only a tarsal contact with terrain, below the thorax and with a normal
        towards the fly within 45 degrees of world up, counts as support.
        Side/underside contacts, other body parts and opponents remain tactile.
        """
        if not target.startswith("obstacle-"):
            return False
        first, second = int(contact.geom1), int(contact.geom2)
        own = first if self.geom_slots.get(first) == slot else second
        name = mj.mj_id2name(self.model, mj.mjtObj.mjOBJ_GEOM, own) or ""
        if "_tarsus" not in name:
            return False
        normal_z = float(contact.frame[2]) * (1 if own == second else -1)
        return normal_z >= 2 ** -.5 and float(contact.pos[2]) < float(self.data.xpos[self.body_ids[slot], 2])

    def support_contacts(self, slot: int) -> list[str]:
        return sorted({name for contact, name in self._environment_contacts(slot)
                       if self.is_support_contact(slot, contact, name)})

    def lateral_environment_contacts(self, slot: int, *, exclude_support: bool = False) -> dict[str, list[str]]:
        """Contact side in the current thorax frame, not an inferred receptor.

        Local +Y is left. Points within 0.05 mm of the midline are recorded
        as center; an engineered encoder may send those to both sides.
        """
        position, rotation = self.pose(slot)
        result = {side: set() for side in ('left', 'right', 'center')}
        for contact, name in self._environment_contacts(slot):
            if exclude_support and self.is_support_contact(slot, contact, name):
                continue
            lateral = float((rotation.T @ (contact.pos - position))[1])
            side = 'left' if lateral > .05 else 'right' if lateral < -.05 else 'center'
            result[side].add(name)
        return {side: sorted(names) for side, names in result.items()}

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
        return {"meshes": meshes, "geoms": geoms,
                "food_geoms": [{"id": geom, "food_id": food_id} for food_id, geom in self.food_geom_ids.items()],
                "contact_probes": [{"slot": slot, "id": geom,
                                    "observation": "mujoco_food_contact_observation_v1"}
                                   for slot, geom in sorted(self.mouth_contact_geom_ids.items())],
                "unit": "mm", "up": "Z", "quaternion": "wxyz",
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
