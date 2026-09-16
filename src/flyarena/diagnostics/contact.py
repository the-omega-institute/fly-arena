"""Read-only development instrumentation for existing engineered sensing geometry.

No production imports, emitter changes, control signals, resource updates or physics
changes. Coordinates are observation outputs and must never be probe/controller inputs.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import time
import numpy as np
from flyarena.common import ROOT, file_sha, write_json
from flyarena.scenarios import RULES

INSTRUMENT_ID = 'development-exact-head-contact-v1'


def contact_geometry(mouth, food_xy, remaining):
    mouth=np.asarray(mouth,dtype=float); food_xy=np.asarray(food_xy,dtype=float).reshape(-1,2)
    remaining=np.asarray(remaining,dtype=float)
    if remaining.shape!=(len(food_xy),):raise ValueError('One remaining amount per food patch required')
    distance=np.linalg.norm(food_xy-mouth[:2],axis=1)
    horizontal=distance<=RULES['mouth_radius_mm']
    height=bool(mouth[2]<2.5)
    return dict(horizontal_distance_mm=distance,radial_clearance_mm=distance-RULES['mouth_radius_mm'],
                height_clearance_mm=float(mouth[2]-2.5),horizontal_eligible=horizontal,
                height_eligible=height,geometry_eligible=horizontal & height,
                resource_available=remaining>0,feeding_eligible=horizontal & height & (remaining>0))


def sample_contact(body,slot,food_xy,remaining,*,actual_intake_delta=0.,actual_intake_total=0.):
    """Sample after caller's normal 10ms feeding update; actual intake is caller-supplied.

    Head is the live registered MuJoCo head site. Mouth/antennae are exactly the
    existing engine's head-frame points, not claimed anatomical mouth/antenna meshes.
    The engine defines no orientation for point sensors; head rotation is provided.
    """
    h=body.head_ids[slot]
    head_position=body.data.site_xpos[h].copy()
    head_rotation=body.data.site_xmat[h].reshape(3,3).copy()
    mouth=body.mouth(slot).copy(); antennae=np.array(body.antennae(slot))
    position,rotation=body.pose(slot)
    return dict(instrument_id=INSTRUMENT_ID,physics_tick=int(body.tick),
        time_seconds=float(body.tick*RULES['physics_dt']),slot=slot,
        head_position_mm=head_position,head_rotation=head_rotation,
        mouth_position_mm=mouth,antenna_positions_mm=antennae,
        thorax_position_mm=position,thorax_rotation=rotation,
        actual_intake_delta=float(actual_intake_delta),actual_intake_total=float(actual_intake_total),
        **contact_geometry(mouth,food_xy,remaining))


def static_sanity():
    from flyarena.body import Bodies
    start=time.perf_counter(); out=ROOT/'var/diagnostic-v5'
    scene={'size':20,'obstacles':[],'spawns':[[0.,0.,0.]],
           'food':[{'id':'static-only','position':[0.,0.,.15],'initial':10.}]}
    body=Bodies(scene,1,0)
    before=body.checkpoint()
    first=sample_contact(body,0,[[0.,0.]],[10.])
    h=first['head_position_mm'];r=first['head_rotation']
    assert np.array_equal(first['mouth_position_mm'],h+r@np.array([.35,0.,-.2]))
    assert np.array_equal(first['antenna_positions_mm'],np.array([h+r@np.array([.45,.45,0.]),h+r@np.array([.45,-.45,0.])]))
    mouth=first['mouth_position_mm']
    # Static observation fixtures; no scene, model, qpos, or resource mutations.
    foods=np.array([mouth[:2],mouth[:2]+[1.1-1e-9,0.],mouth[:2]+[1.1+1e-9,0.]])
    second=sample_contact(body,0,foods,[10.,10.,10.])
    assert second['horizontal_eligible'].tolist()==[True,True,False]
    after=body.checkpoint()
    assert all(np.array_equal(before[k],after[k]) for k in before)
    assert body.tick==0
    def serial(record):
        return {k:v.tolist() if isinstance(v,np.ndarray) else v for k,v in record.items()}
    np.savez_compressed(out/'static-body-checkpoint.npz',**before)
    write_json(out/'static-contact-sanity.json',dict(instrument_id=INSTRUMENT_ID,
        diagnostic_only=True,physical_seconds=0.,physics_steps=0,scene=scene,
        actual_pose=serial(first),boundary_fixture=serial(second),
        mutation_free=True,head_transform_exact=True,
        source_sha256=file_sha(Path(__file__)),body_source_sha256=file_sha(ROOT/'src/flyarena/body.py'),
        checkpoint_sha256=file_sha(out/'static-body-checkpoint.npz'),wall_seconds=time.perf_counter()-start,
        limitation='Static engine point geometry only, not a feeding/capture/retention trial. No geometry or scoring change.'))
    print('STATIC_CONTACT_PASS zero physics steps; exact head-frame points and unchanged complete checkpoint',flush=True)

if __name__=='__main__':static_sanity()
