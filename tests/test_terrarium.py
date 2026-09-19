import math

import mujoco as mj
import numpy as np

from flyarena.body import Bodies
from flyarena.scenarios import MAPS, scenario


def _obstacle_geoms(bodies):
    return [i for i in range(bodies.model.ngeom)
            if (mj.mj_id2name(bodies.model, mj.mjtObj.mjOBJ_GEOM, i) or "").startswith("obstacle-")]


def test_terrarium_schema_is_symmetric_and_food_stays_on_ground():
    scene = scenario("terrarium", 19)
    assert scene["size"] == 28
    assert scene["habitat"] == "forest-floor"
    assert all(f["position"][2] == .15 for f in scene["food"])
    assert all(o["position"][0] or o["position"][1] for o in scene["obstacles"] if o["material"] != "leaf")
    assert any(o.get("shape") == "ellipsoid" for o in scene["obstacles"])
    assert any(o.get("shape", "box") == "box" for o in scene["obstacles"])
    # The obstacle set is mirrored under a half-turn; material and dimensions
    # remain paired so either contestant sees equivalent geometry.
    obstacles = scene["obstacles"]
    keys = {(round(o["position"][0], 4), round(o["position"][1], 4),
             tuple(o["size"]), o.get("shape", "box"), o["material"])
            for o in obstacles}
    for o in obstacles:
        assert (-o["position"][0], -o["position"][1], tuple(o["size"]),
                o.get("shape", "box"), o["material"]) in keys


def test_terrarium_compiles_fullsize_quats_colors_and_masks():
    bodies = Bodies(scenario("terrarium", 3), 2, 3)
    obstacle_ids = _obstacle_geoms(bodies)
    assert len(obstacle_ids) == len(MAPS["terrarium"]["obstacles"])
    for geom_id, obstacle in zip(obstacle_ids, MAPS["terrarium"]["obstacles"]):
        np.testing.assert_allclose(bodies.model.geom_size[geom_id], np.asarray(obstacle["size"]) / 2)
        np.testing.assert_allclose(bodies.model.geom_quat[geom_id], obstacle.get("quaternion", [1, 0, 0, 0]), atol=2e-4)
        assert bodies.model.geom_contype[geom_id] == 4
        assert bodies.model.geom_conaffinity[geom_id] == 3
        assert bodies.model.geom_rgba[geom_id, 3] == 1
    assert sum(bodies.model.geom_type[i] == mj.mjtGeom.mjGEOM_ELLIPSOID for i in obstacle_ids) >= 2
    fly_geoms = [i for i in range(bodies.model.ngeom)
                 if i not in obstacle_ids and
                 (mj.mj_id2name(bodies.model, mj.mjtObj.mjOBJ_GEOM, i) or "").startswith("fly-")]
    # Locomotion geoms collide with terrain; the feeding probe is a
    # food-only sensor and must not add a ground reaction force.
    assert all(bodies.model.geom_conaffinity[i] & 4 for i in fly_geoms
               if not (mj.mj_id2name(bodies.model, mj.mjtObj.mjOBJ_GEOM, i) or "").endswith("/mouth_contact"))
    assert all(not (bodies.model.geom_conaffinity[i] & 4) for i in fly_geoms
               if (mj.mj_id2name(bodies.model, mj.mjtObj.mjOBJ_GEOM, i) or "").endswith("/mouth_contact"))


def test_terrarium_ramps_have_real_gentle_ground_to_leaf_profile():
    bodies = Bodies(scenario("terrarium", 7), 1, 7)
    obstacle_ids = _obstacle_geoms(bodies)
    ramp_ids = obstacle_ids[1:3]
    leaf_id = obstacle_ids[0]
    leaf_top = bodies.data.geom_xpos[leaf_id, 2] + bodies.model.geom_size[leaf_id, 2]
    assert .5 < leaf_top <= 1.0
    for ramp_id in ramp_ids:
        quat = bodies.data.geom_xmat[ramp_id].reshape(3, 3)
        angle = math.degrees(math.atan2(abs(quat[2, 0]), abs(quat[0, 0])))
        assert 4.0 < angle < 7.0
        # Query the compiled ramp's actual top surface at both ends. This
        # catches an identity quaternion or wrong size convention.
        axis = quat[:, 0]
        half_length = bodies.model.geom_size[ramp_id, 0]
        center = bodies.data.geom_xpos[ramp_id]
        # Stay just inside each end so the downward ray intersects the ramp
        # top rather than the coplanar ground or adjacent leaf edge.
        ends = [center - axis * (half_length - .2), center + axis * (half_length - .2)]
        heights = []
        for point in ends:
            origin = point + np.array([0, 0, 2.0])
            direction = np.array([0, 0, -1.0])
            geomid = np.array([-1], dtype=np.int32)
            distance = mj.mj_ray(bodies.model, bodies.data, origin, direction, None, 1, -1, geomid)
            assert distance >= 0
            assert geomid[0] == ramp_id
            heights.append(origin[2] - distance)
        inward = min(range(2), key=lambda i: abs(ends[i][0]))
        assert heights[inward] > heights[1-inward]
        assert min(heights) < .05
        assert max(heights) > .55
        assert max(heights) <= 1.0
        assert abs(max(heights) - leaf_top) < .05


def test_terrarium_ramp_contact_and_finite_rollout():
    scene = scenario("terrarium", 11)
    scene["spawns"] = [[-8, 0, 0], [8, 0, math.pi]]
    bodies = Bodies(scene, 2, 11)
    ramp_contacts = 0
    for _ in range(1000):
        bodies.step(np.zeros((2, 2)))
        for contact in bodies.data.contact:
            names = [mj.mj_id2name(bodies.model, mj.mjtObj.mjOBJ_GEOM, int(g)) or ""
                     for g in (contact.geom1, contact.geom2)]
            if any(name in ("obstacle-1", "obstacle-2") for name in names):
                ramp_contacts += 1
    assert np.isfinite(bodies.data.qpos).all()
    assert np.isfinite(bodies.data.qvel).all()
    assert ramp_contacts > 0


def test_default_spawn_and_food_are_clear_of_terrain():
    bodies = Bodies(scenario('terrarium', 42), 2, 42)
    obstacles = set(_obstacle_geoms(bodies))
    assert not any(int(c.geom1) in obstacles or int(c.geom2) in obstacles for c in bodies.data.contact)
    for patch in scenario('terrarium', 42)['food']:
        x, y, _ = patch['position']
        hit = np.array([-1], dtype=np.int32)
        distance = mj.mj_ray(bodies.model, bodies.data, np.array([x,y,4.]), np.array([0.,0.,-1.]), None, 1, -1, hit)
        assert distance >= 0
        assert hit[0] not in obstacles


def test_food_is_a_raycast_target_and_obstacles_occlude_visual_observation():
    clear = scenario("orchard", 42)
    clear["spawns"] = [[-7, 0, 0]]
    clear["food"] = [clear["food"][0]]
    clear["obstacles"] = []
    visible = Bodies(clear, 1, 42)
    clear_signal = visible.visual_food(0, np.array([10.0]))
    assert max(clear_signal) > 0
    assert len(visible.food_geom_ids) == 1
    assert visible.model.geom_contype[next(iter(visible.food_geom_ids.values()))] == 8
    assert len(visible.rendering_manifest()["food_geoms"]) == 1
    assert visible.rendering_manifest()["contact_probes"][0]["observation"] == "mujoco_food_contact_observation_v1"
    assert set(visible.mouth_contact_geom_ids) == {0}
    mouth_geom = visible.mouth_contact_geom_ids[0]
    assert visible.model.geom_conaffinity[mouth_geom] == 8
    np.testing.assert_allclose(visible.model.geom_size[mouth_geom, 0], .65)

    blocked_scene = scenario("orchard", 42)
    blocked_scene["spawns"] = [[-7, 0, 0]]
    blocked_scene["food"] = [blocked_scene["food"][0]]
    blocked_scene["obstacles"] = [{"position": [-3.5, 0, 1.5], "size": [1, 4, 3]}]
    blocked = Bodies(blocked_scene, 1, 42)
    assert max(blocked.visual_food(0, np.array([10.0]))) == 0


def test_food_touch_is_read_from_mujoco_contact_buffer():
    scene = scenario("orchard", 42)
    scene["food"] = [scene["food"][0]]
    x, y, _ = scene["food"][0]["position"]
    scene["spawns"] = [[x - .2, y, 0]]
    bodies = Bodies(scene, 1, 42)
    assert bodies.food_contacts(0) == ["food-0"]
    mouth = bodies.mouth_contact_geom_ids[0]
    food = bodies.food_geom_ids["food-0"]
    assert any({int(c.geom1), int(c.geom2)} == {mouth, food} and c.dist <= 0
               for c in bodies.data.contact)


def test_enclosure_has_a_continuous_physical_perimeter_and_clear_spawns():
    scene = scenario('enclosure', 42)
    bodies = Bodies(scene, 2, 42)
    obstacle_ids = _obstacle_geoms(bodies)
    walls = set(obstacle_ids[:16])
    # Rays in all directions must hit the actual compiled wall, including
    # segment joints. Use a height above the small interior terrain.
    for angle in np.linspace(0, 2 * math.pi, 128, endpoint=False):
        hit = np.array([-1], dtype=np.int32)
        distance = mj.mj_ray(bodies.model, bodies.data, np.array([0., 0., 3.]),
                            np.array([math.cos(angle), math.sin(angle), 0.]), None, 1, -1, hit)
        assert int(hit[0]) in walls
        assert 11 < distance < 14
    # The simulator's collision masks include both contestants.
    assert all(bodies.model.geom_contype[i] == 4 and bodies.model.geom_conaffinity[i] == 3 for i in walls)
    assert not any(int(c.geom1) in obstacle_ids or int(c.geom2) in obstacle_ids for c in bodies.data.contact)
    assert [f['position'] for f in scene['food']] == [f['position'] for f in scenario('orchard', 42)['food']]


def test_enclosure_wall_collides_with_body():
    scene = scenario('enclosure', 42)
    scene['spawns'] = [[11.8, 0, 0]]
    bodies = Bodies(scene, 1, 42)
    walls = set(_obstacle_geoms(bodies)[:16])
    mouth = bodies.mouth_contact_geom_ids[0]
    contacts = 0
    sensed = set()
    for _ in range(500):
        bodies.step(np.array([[1., 1.]]))
        sensed.update(bodies.environment_contacts(0))
        assert not any(mouth in (int(c.geom1), int(c.geom2)) and
                       (int(c.geom1) in walls or int(c.geom2) in walls)
                       for c in bodies.data.contact if c.dist <= 0)
        contacts += sum((int(c.geom1) in walls and int(c.geom2) in bodies.geom_slots) or
                        (int(c.geom2) in walls and int(c.geom1) in bodies.geom_slots) for c in bodies.data.contact)
    assert contacts > 0
    assert sensed and all(name.startswith("obstacle-") for name in sensed)
    assert np.isfinite(bodies.data.qpos).all()


def test_feeding_probes_do_not_push_another_fly():
    scene = scenario('orchard', 42)
    # Deliberately overlap anatomical bodies to exercise actual collision pairs.
    # No integration or behavioral claim is made for this geometry fixture.
    scene['spawns'] = [[0, 0, 0], [0, 0, math.pi]]
    scene['food'] = []
    bodies = Bodies(scene, 2, 42)
    probes = set(bodies.mouth_contact_geom_ids.values())
    assert bodies.contact_between_flies()
    assert bodies.environment_contacts(0) == ["fly-1"]
    assert bodies.environment_contacts(1) == ["fly-0"]
    assert not any(probes.intersection((int(c.geom1), int(c.geom2)))
                   for c in bodies.data.contact if c.dist <= 0)


def test_ground_support_and_food_probe_do_not_become_environment_touch():
    scene = scenario('orchard', 42)
    scene['obstacles'] = []
    scene['food'] = [scene['food'][0]]
    x, y, _ = scene['food'][0]['position']
    scene['spawns'] = [[x - .2, y, 0]]
    bodies = Bodies(scene, 1, 42)
    assert bodies.food_contacts(0)
    assert bodies.environment_contacts(0) == []
    ground_contacts = 0
    for _ in range(500):
        bodies.step(np.zeros((1, 2)))
        assert bodies.environment_contacts(0) == []
        ground_contacts += sum(any(bodies.model.geom_type[int(g)] == mj.mjtGeom.mjGEOM_PLANE
                                   for g in (c.geom1, c.geom2)) for c in bodies.data.contact)
    assert ground_contacts > 0
