"""Bounded nonphysical tests for the exact v14 feedback intervention."""
import copy
import json
import pickle
from unittest.mock import patch
import numpy as np
import pytest
from flygym_demo.complex_terrain.hybrid_controller import HybridControllerObservation
from flygym_demo.complex_terrain.common import dof_spec_to_jointdof,get_default_locomotion_dof_order
from flyarena.experiments.cadence_v12 import ExcursionHybridController
from flyarena.experiments.cadence_v14 import ClearanceHybridController,ClearanceObservation,PROFILE,CONTROL
from flyarena.experiments import mechanical_v14 as runner
from flyarena.experiments.verify_v14 import verify_phase_law,verify_retraction_and_commands,_validate_restoration_arrays


@pytest.fixture(autouse=True)
def no_physics():
    with patch('mujoco.mj_step',side_effect=AssertionError('unregistered physics forbidden')):
        yield


def observation(height=0.):
    native=HybridControllerObservation(1.,np.zeros(6),np.zeros((6,3,3)),np.array([1.,0.,0.]))
    return ClearanceObservation(native,np.full(6,height),np.arange(6,dtype=np.int64),np.zeros(6,dtype=np.int64))


def controller():
    c=ClearanceHybridController(timestep=runner.DT);c.reset(seed=42)
    c.cpg_network.curr_phases=c.release_end/2
    return c


def test_all_six_simultaneous_not_old_relative_height_selector():
    c=controller();c.step([.2,.2],observation())
    assert np.array_equal(c.last_trigger,np.ones(6,dtype=bool))
    np.testing.assert_array_equal(c.retraction_correction,np.full(6,.08))
    assert c.last_info['retraction_mask'].all()


@pytest.mark.parametrize('boundary',['start','end','height','above','preupdate'])
def test_strict_height_phase_and_preupdate(boundary):
    c=controller();obs=observation()
    if boundary in ('start','preupdate'):c.cpg_network.curr_phases[:]=0
    if boundary=='end':c.cpg_network.curr_phases=c.release_end.copy()
    if boundary in ('height','above'):obs=observation(.05 if boundary=='height' else np.nextafter(.05,np.inf))
    c.step([.2,.2],obs)
    assert not c.last_trigger.any()
    assert not c.retraction_correction.any()
    if boundary=='preupdate':assert np.all(c.cpg_network.curr_phases>0)


@pytest.mark.parametrize('bad',['nan','shape','native_nan','native_type','vertex','none','input'])
def test_malformed_atomic_rejection(bad):
    c=controller();obs=observation();u=[.2,.2]
    if bad=='nan':obs.clearance[0]=np.nan
    if bad=='shape':obs=ClearanceObservation(obs.native,np.zeros(5),obs.minimum_geom,obs.minimum_vertex)
    if bad=='native_nan':obs.native.stumbling_contact_forces[0,0,0]=np.nan
    if bad=='native_type':obs=ClearanceObservation(None,obs.clearance,obs.minimum_geom,obs.minimum_vertex)
    if bad=='vertex':obs.minimum_vertex[0]=-1
    if bad=='none':obs=None
    if bad=='input':u=[np.nan,.2]
    before=pickle.dumps(c.checkpoint(),protocol=5)
    with pytest.raises(ValueError):c.step(u,obs)
    assert pickle.dumps(c.checkpoint(),protocol=5)==before


def test_native_persistence_priority_expiry_and_unclipped_internal_scalar():
    c=controller();obs=observation();obs.native.stumbling_contact_forces[:,:,0]=-2
    c.retraction_correction[:]=100
    c.step([.2,.2],obs)
    np.testing.assert_array_equal(c.retraction_persistence_counter,np.full(6,2))
    np.testing.assert_allclose(c.retraction_correction,100.08,rtol=0,atol=0)
    assert not c.stumbling_correction.any()
    assert np.max(np.abs(c.last_info['net_corrections']))<=80*.8
    c.retraction_persistence_counter[:]=20
    before=c.retraction_correction.copy();c.step([.2,.2],observation(.06))
    assert not c.retraction_persistence_counter.any()
    np.testing.assert_allclose(c.retraction_correction,before-.07,rtol=0,atol=0)


def test_persistence_threshold_is_strict():
    c=controller();c.retraction_correction[:]=20
    c.step([.2,.2],observation());assert not c.retraction_persistence_counter.any()
    c.step([.2,.2],observation());assert np.array_equal(c.retraction_persistence_counter,np.full(6,2))


def test_silence_and_serialized_restoration_hold_all_diagnostics_rng_actions():
    c=controller()
    for _ in range(50):c.step([.2,.2],observation())
    saved=pickle.dumps(c.checkpoint(),protocol=5)
    for _ in range(100):
        a=c.step([0,0],None);assert np.array_equal(a.joint_angles,c._last_angles)
    assert pickle.dumps(c.checkpoint(),protocol=5)==saved
    expected=[c.step([.12,.28],observation(.01)).joint_angles for _ in range(100)]
    c.restore(pickle.loads(saved));actual=[c.step([.12,.28],observation(.01)).joint_angles for _ in range(100)]
    assert np.array_equal(expected,actual)


def test_exact_native_vector_right_sign_once_and_uniform_phase():
    c=controller();v=ExcursionHybridController(timestep=runner.DT);v.reset(seed=42)
    v.cpg_network.curr_phases=c.cpg_network.curr_phases.copy()
    a=c.step([.04,.36],observation());v.step([.04,.36],observation().native)
    np.testing.assert_array_equal(c.cpg_network.curr_phases,v.cpg_network.curr_phases)
    np.testing.assert_array_equal(c.cpg_network.curr_magnitudes,v.cpg_network.curr_magnitudes)
    order=get_default_locomotion_dof_order()
    vectors={'f':[-.03,0,0,-.03,0,.03,.03],'m':[-.015,.001,.025,-.02,0,-.02,0],'h':[0,0,0,-.02,0,.01,-.02]}
    native=c.preprogrammed_steps.get_joint_angles_by_dof_order(c.cpg_network.curr_phases,c.cpg_network.curr_magnitudes)
    expected=native.copy()
    for i,leg in enumerate(c.legs):
        vec=np.array(vectors[leg[1]])*(np.array([1,-1,-1,1,-1,1,1]) if leg.startswith('r') else 1)
        for j,spec in enumerate(c.preprogrammed_steps.dofs_per_leg):expected[order.index(dof_spec_to_jointdof(leg,spec))]+=vec[j]*c.last_info['net_corrections'][i]
    np.testing.assert_array_equal(a.joint_angles,expected)


def test_detached_sensor_does_not_touch_authoritative_cache_and_full_restore(tmp_path):
    b=runner.new_body(42,PROFILE);v=runner.new_body(42,CONTROL)
    assert b.tick==0 and b.data.time==0
    assert np.array_equal(runner.integration(b),runner.integration(v))
    before=runner._numeric_cache(b.data);state=runner.integration(b)
    h,g,i=b.clearance_sensor.read(b.data.qpos)
    assert np.isfinite(h).all() and np.all(g>=0) and np.all(i>=0)
    assert before==runner._numeric_cache(b.data) and np.array_equal(state,runner.integration(b))
    (tmp_path/'registration.json').write_text('{}')
    reg={'model_sha256':'test-only-model','sources_sha256':'test-only-source'}
    b.tick=10000 # Static checkpoint unit fixture, not elapsed integration.
    checkpoint=runner.capture_active_checkpoint(tmp_path,b,reg)
    b.data.qpos[0]+=1;b.data.qvel[0]+=1;b.data.ctrl[0]+=1;b.controllers[0].last_clearance[:]=77;b.tick=7
    runner.restore_active_checkpoint(tmp_path,b,checkpoint,reg)
    assert b.tick==10000 and before==runner._numeric_cache(b.data)
    assert np.array_equal(state,runner.integration(b)) and np.all(b.controllers[0].last_clearance==0)


def test_exact_panel_and_budget():
    expected=[(p,s,list(case)) for s in (42,43) for case in runner.CASES for p in (CONTROL,PROFILE)]
    assert runner.panel('development')==expected and len(expected)==32
    assert len(runner.panel('evaluation'))==16 and runner.panel('repeat')==[(PROFILE,31042,list(runner.CASES[2]))]
    assert (32+16+1)*4+100*runner.DT==196.01


def test_independent_state_equations_detect_mask_and_scalar_tampering():
    c=controller();cs=runner._slices(runner.CORE);rows=np.zeros((31,runner._width(runner.CORE)))
    def record(k):
        obs=observation();rows[k,cs['native_observation']]=np.r_[obs.native.thorax_z,obs.native.tarsus5_z,obs.native.stumbling_contact_forces.ravel(),obs.native.fly_heading]
        for field,attr in [('phases','curr_phases'),('magnitudes','curr_magnitudes'),('targets','intrinsic_amps')]:rows[k,cs[field]]=getattr(c.cpg_network,attr)
        for field,attr in [('retraction','retraction_correction'),('stumbling','stumbling_correction'),('persistence','retraction_persistence_counter'),('sensed_clearance','last_clearance'),('trigger_mask','last_trigger'),('minimum_geom','last_minimum_geom'),('minimum_vertex','last_minimum_vertex')]:rows[k,cs[field]]=getattr(c,attr)
        rows[k,cs['net_correction']]=c.last_info.get('net_corrections',np.zeros(6))
        rows[k,cs['ctrl']]=np.r_[c._last_angles,c._last_adhesion];rows[k,cs['adhesion']]=c._last_adhesion
        rows[k,cs['native_template']]=c.preprogrammed_steps.get_joint_angles_by_dof_order(c.cpg_network.curr_phases,c.cpg_network.curr_magnitudes)
    # Align initialization adhesion with this deliberately supplied nonphysical phase.
    c._last_adhesion=np.array([c._get_adhesion_onoff(l,p) for l,p in zip(c.legs,c.cpg_network.curr_phases)])
    record(0)
    for k in range(1,31):c.step([.2,.2],observation());record(k);rows[k,cs['input']]=[.2,.2]
    reg={'controller':{'coupling':c._base_coupling.tolist(),'phase_biases':c.cpg_network.phase_biases.tolist(),'release_end':c.release_end.tolist()}}
    assert verify_phase_law(rows,PROFILE,reg)['max_phase_equation_error']<5e-12
    verify_retraction_and_commands(rows,PROFILE,reg)
    changed=rows.copy();changed[10,cs['trigger_mask']]=0
    with pytest.raises(ValueError):verify_retraction_and_commands(changed,PROFILE,reg)
    changed=rows.copy();changed[10,cs['retraction']]+=1
    with pytest.raises(ValueError):verify_retraction_and_commands(changed,PROFILE,reg)


def test_expanded_restore_schema_rejects_legacy_width():
    arrays={'core':np.zeros((100,runner._width(runner.CORE))),'dense':np.zeros((100,runner._width(runner.DENSE))),'contacts':np.zeros((0,runner._width(runner.CONTACT))),'integration':np.zeros((100,752)),'contact_offsets':np.zeros(101,dtype=np.int64)}
    _validate_restoration_arrays(arrays,752)
    arrays['core']=np.zeros((100,303))
    with pytest.raises(ValueError):_validate_restoration_arrays(arrays,752)
