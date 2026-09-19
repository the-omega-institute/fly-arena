"""Physical support is recorded without triggering the new avoidance channel."""
import numpy as np
import mujoco as mj
from flyarena.body import Bodies
from flyarena.scenarios import scenario


def test_settled_feet_on_terrain_are_support_not_lateral_obstacles():
    scene = scenario('orchard', 42)
    # Thick platform isolates top support; the next test covers thin-slab trapping.
    scene.update(food=[], spawns=[[0,0,0]], obstacles=[{'position':[0,0,-.8], 'size':[20,20,2.]}])
    body = Bodies(scene, 1, 42)
    body.data.qpos[2] += .4
    mj.mj_forward(body.model, body.data)
    for _ in range(500):
        body.step(np.array([[0.,0.]]))
    assert body.support_contacts(0) == ['obstacle-0']
    assert body.environment_contacts(0) == ['obstacle-0']
    assert any(body.lateral_environment_contacts(0).values())
    assert body.lateral_environment_contacts(0, exclude_support=True) == dict(left=[], right=[], center=[])


def test_wall_and_underside_contacts_remain_tactile():
    scene = scenario('enclosure', 42); scene['spawns'] = [[11.8,0,0]]
    body = Bodies(scene, 1, 42)
    assert any(body.lateral_environment_contacts(0, exclude_support=True).values())
    scene = scenario('orchard',42)
    scene.update(food=[], spawns=[[0,0,0]], obstacles=[{'position':[0,0,.1],'size':[20,20,.2]}])
    body = Bodies(scene,1,42)
    # This deliberately intersecting fixture includes real underside contacts;
    # it must not be reclassified as ordinary upright support.
    for _ in range(100):body.step(np.array([[0.,0.]]))
    supports = []; remaining = []
    for contact, target in body._environment_contacts(0):
        own = int(contact.geom1) if body.geom_slots.get(int(contact.geom1)) == 0 else int(contact.geom2)
        normal_z = float(contact.frame[2]) * (1 if own == int(contact.geom2) else -1)
        if normal_z < -.7:
            assert not body.is_support_contact(0,contact,target)
            remaining.append(target)
        if body.is_support_contact(0,contact,target):supports.append(target)
    assert supports and remaining
    assert any(body.lateral_environment_contacts(0,exclude_support=True).values())


def test_opponent_contacts_are_never_terrain_support():
    scene=scenario('orchard',42);scene.update(food=[],obstacles=[],spawns=[[0,0,0],[0,0,np.pi]])
    body=Bodies(scene,2,42)
    for slot in (0,1):
        assert body.support_contacts(slot)==[]
        assert body.lateral_environment_contacts(slot,exclude_support=True)==body.lateral_environment_contacts(slot)
