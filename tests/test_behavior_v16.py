"""Registered nonphysical v16 law, native equivalence, atomicity and cache checks."""
import copy
from dataclasses import replace
import pickle
from unittest.mock import patch
import numpy as np
import pytest
from flygym_demo.complex_terrain.hybrid_controller import HybridControllerObservation
from flygym_demo.complex_terrain.common import apply_locomotion_action
from flyarena.experiments.cadence_v15 import AllocationHybridController as V15Controller, AllocationObservation as V15Observation, normal_allocation as v15_allocate
from flyarena.experiments.cadence_v16 import AllocationHybridController,AllocationObservation,normal_allocation,PROFILE,CONTROL
from flyarena.experiments import mechanical_v16 as runner
from flyarena.experiments.verify_v16 import verify_allocation_row


@pytest.fixture(autouse=True)
def no_physics():
    with patch('mujoco.mj_step',side_effect=AssertionError('unregistered physics forbidden')):
        yield


def observation(tick=0,height=0.):
    native=HybridControllerObservation(1.,np.zeros(6),np.zeros((6,3,3)),np.array([1.,0.,0.]))
    J=np.zeros((6,3,7));J[:,0,0]=1;J[:,1,1]=1;J[:,2,2]=1
    return AllocationObservation(native,np.full(6,height),np.arange(6,dtype=np.int64),np.zeros(6,dtype=np.int64),
        np.zeros((6,7)),J,np.full((6,7),-np.inf),np.full((6,7),np.inf),tick,'a'*64)


def control_observation(obs):
    return V15Observation(**{**vars(obs),"version":"whole-foot-observation/v15"})


def controller():
    c=AllocationHybridController(timestep=runner.DT);c.reset(seed=42);c.model_hash='a'*64
    c.cpg_network.curr_phases=c.release_end/2
    return c


def test_minimum_norm_tangent_covariance_and_inherited_budget():
    rng=np.random.default_rng(71)
    for norm in (.06,np.sqrt(.001651),.03)*2:
        J=rng.normal(size=(3,7));q=np.zeros(7);b=80*.8*norm
        x,d,_=normal_allocation(J,0,q,q,np.full(7,-np.inf),np.full(7,np.inf),b)
        np.testing.assert_allclose(J[:2]@x,0,atol=1e-14)
        assert J[2]@x>0 and np.linalg.norm(x)<=b
        expected=np.linalg.lstsq(J,np.array([0.,0.,.05]),rcond=None)[0]
        np.testing.assert_allclose(x,expected,atol=1e-14)
        phi=.73;R=np.array([[np.cos(phi),-np.sin(phi),0],[np.sin(phi),np.cos(phi),0],[0,0,1]])
        y,_,_=normal_allocation(R@J,0,q,q,np.full(7,-np.inf),np.full(7,np.inf),b)
        np.testing.assert_allclose(x,y,atol=1e-14)
        # Any null(J) addition leaves the task but increases the norm.
        _,_,v=np.linalg.svd(J,full_matrices=True)
        assert np.linalg.norm(x+.2*v[-1])>np.linalg.norm(x)


@pytest.mark.parametrize('rank',[0,1,2])
def test_rank_and_authority(rank):
    J=np.zeros((3,7));J[2,2]=1
    for i in range(rank):J[i,i]=1
    x,d,_=normal_allocation(J,0,np.zeros(7),np.zeros(7),np.full(7,-np.inf),np.full(7,np.inf),1)
    assert d[6]==rank and x[2]==.05
    J[2]=0
    with pytest.raises(ValueError):normal_allocation(J,0,np.zeros(7),np.zeros(7),np.full(7,-np.inf),np.full(7,np.inf),1)
    x,d,_=normal_allocation(J,.05,np.zeros(7),np.zeros(7),np.full(7,-np.inf),np.full(7,np.inf),1)
    assert not x.any() and d[5]==0


def test_exact_rank_threshold():
    tau=64*np.finfo(float).eps
    J=np.zeros((3,7));J[0,0]=tau;J[1,1]=1;J[2,2]=1
    _,d,_=normal_allocation(J,0,np.zeros(7),np.zeros(7),np.full(7,-np.inf),np.full(7,np.inf),1)
    assert d[6]==1
    J[0,0]=np.nextafter(tau,np.inf)
    _,d,_=normal_allocation(J,0,np.zeros(7),np.zeros(7),np.full(7,-np.inf),np.full(7,np.inf),1)
    assert d[6]==2


@pytest.mark.parametrize('sign',[-1,1])
def test_compiled_limit_budget_and_tracking(sign):
    J=np.zeros((3,7));J[2,2]=sign;q=np.zeros(7);q0=q.copy();q0[2]=-.02*sign
    lo=np.full(7,-1.);hi=np.full(7,1.)
    if sign>0:hi[2]=.01
    else:lo[2]=-.01
    x,d,_=normal_allocation(J,0,q,q0,lo,hi,1)
    assert abs(x[2]-.03*sign)<1e-15 and abs(d[5]-.04)<1e-15 and d[7]==2
    x,d,_=normal_allocation(J,0,q,q0,lo,hi,.01)
    assert x[2]==.01*sign and d[7]==1 and d[5]>.04
    with pytest.raises(ValueError):normal_allocation(J,0,q,hi+1,lo,hi,1)


@pytest.mark.parametrize('bad',['nan','shape','native_nan','native_type','vertex','none','input','jacobian','angles','ranges','empty','model','tick','q0','late_rank'])
def test_atomic_rejection_including_late_shadow_failure(bad):
    c=controller();obs=observation();u=[.2,.2]
    if bad=='nan':obs.clearance[0]=np.nan
    if bad=='shape':obs=replace(obs,clearance=np.zeros(5))
    if bad=='native_nan':obs.native.stumbling_contact_forces[0,0,0]=np.nan
    if bad=='native_type':obs=replace(obs,native=None)
    if bad=='vertex':obs.minimum_vertex[0]=-1
    if bad=='none':obs=None
    if bad=='input':u=[np.nan,.2]
    if bad=='jacobian':obs.jacobian[5,2,2]=np.nan
    if bad=='angles':obs.angles[2,1]=np.inf
    if bad=='ranges':obs=replace(obs,lower=np.zeros((6,6)))
    if bad=='empty':obs.lower[0,0]=np.inf
    if bad=='model':obs=replace(obs,model_hash='b'*64)
    if bad=='tick':obs=replace(obs,tick=-1)
    if bad=='q0':
        obs.upper[:]=0;c.compiled_upper[:]=0
    if bad=='late_rank':obs.jacobian[5]=0
    before=pickle.dumps(c.checkpoint(),protocol=5)
    with pytest.raises(ValueError):c.step(u,obs)
    assert pickle.dumps(c.checkpoint(),protocol=5)==before


def test_native_trace_persistence_priority_and_saturation_equivalence():
    c=controller();v=V15Controller(timestep=runner.DT);v.reset(seed=42);v.model_hash="a"*64
    v.cpg_network.curr_phases=c.cpg_network.curr_phases.copy()
    c.retraction_correction[:]=v.retraction_correction[:]=100
    for tick in range(60):
        obs=observation(tick,.01 if tick<30 else .06);obs.native.stumbling_contact_forces[:,:,0]=-2
        c.step([.12,.28],obs)
        v.step([.12,.28],control_observation(obs))
        for name in ('retraction_correction','stumbling_correction','retraction_persistence_counter','_last_adhesion','last_trigger'):
            np.testing.assert_array_equal(getattr(c,name),getattr(v,name))
        for name in ('curr_phases','curr_magnitudes','intrinsic_freqs','coupling_weights','intrinsic_amps'):
            np.testing.assert_array_equal(getattr(c.cpg_network,name),getattr(v.cpg_network,name))
        assert np.all(np.linalg.norm(c.last_allocation,axis=1)<=np.array([3.84,80*.8*np.sqrt(.001651),1.92]*2)+1e-15)
    assert c.retraction_correction.max()>80


@pytest.mark.parametrize('phase',['start','end','stance','swing'])
def test_updated_strict_phase_and_stumbling_branch(phase):
    c=controller();v=V15Controller(timestep=runner.DT);v.reset(seed=42);v.model_hash="a"*64
    p={'start':np.zeros(6),'end':c.release_end.copy(),'stance':np.full(6,5.),'swing':c.release_end/2}[phase]
    c.cpg_network.curr_phases=p.copy();v.cpg_network.curr_phases=p.copy()
    c.retraction_correction[:]=30
    with patch.object(type(c.cpg_network),'step',lambda self:None):c.step([.2,.2],observation())
    if phase!='swing':assert not c.last_allocation.any()
    # Zero retraction: literal native stumbling and right signs, even in stance.
    c=controller();c.cpg_network.curr_phases=p.copy();obs=observation(height=.06);obs.native.stumbling_contact_forces[:,:,0]=-2
    with patch.object(type(c.cpg_network),'step',lambda self:None):
        actual=c.step([.2,.2],obs)
        expected=v.step([.2,.2],control_observation(obs))
    np.testing.assert_array_equal(actual.joint_angles,expected.joint_angles)


def test_silence_checkpoint_diagnostics_and_rng():
    c=controller()
    for tick in range(20):c.step([.2,.2],observation(tick))
    saved=pickle.dumps(c.checkpoint(),protocol=5)
    with patch('numpy.linalg.svd',side_effect=AssertionError('SVD in silence')):
        for _ in range(10):c.step([0,0],None)
    assert pickle.dumps(c.checkpoint(),protocol=5)==saved
    expected=[c.step([.12,.28],observation(tick)).joint_angles for tick in range(20,120)]
    c.restore(pickle.loads(saved));actual=[c.step([.12,.28],observation(tick)).joint_angles for tick in range(20,120)]
    np.testing.assert_array_equal(actual,expected)


def test_detached_geometry_mapping_independent_formula_and_cache_restore(tmp_path):
    b=runner.new_body(42,PROFILE);v=runner.new_body(42,CONTROL);sensor=b.clearance_sensor
    assert b.tick==0 and b.data.time==0 and np.array_equal(runner.integration(b),runner.integration(v))
    before=runner._numeric_cache(b.data);state=runner.integration(b)
    h,g,i=sensor.read(b.data.qpos)
    native=HybridControllerObservation.from_sim(b.sim,'fly-0')
    obs=sensor.observation(native,b.data.qpos,0,h,g,i)
    assert before==runner._numeric_cache(b.data) and np.array_equal(state,runner.integration(b))
    recorder=runner.NativeRecorder(b);pre,_,_=recorder.row(np.zeros(2))
    action=b.controllers[0].step([.2,.2],obs);apply_locomotion_action(b.sim,'fly-0',action)
    post,_,_=recorder.row(np.array([.2,.2]))
    c=b.controllers[0]
    reg={'controller':{'allocation_joint_map':sensor.indices.tolist(),'release_end':c.release_end.tolist(),'swing_periods_strict_modulo':{leg:[0,float(c.release_end[j])] for j,leg in enumerate(c.legs)}}}
    minima=list(zip(h,g,i));verify_allocation_row(b.model,sensor.data,pre,post,minima,reg)
    bad=post.copy();bad[runner._slices(runner.CORE)['allocation']]+=1
    with pytest.raises(ValueError):verify_allocation_row(b.model,sensor.data,pre,bad,minima,reg)
    (tmp_path/'registration.json').write_text('{}');reg={'model_sha256':'test','sources_sha256':'test'}
    b.tick=10000;checkpoint=runner.capture_active_checkpoint(tmp_path,b,reg);before=runner._numeric_cache(b.data);state=runner.integration(b)
    b.data.qpos[0]+=1;b.controllers[0].last_allocation[:]=77;b.tick=7
    runner.restore_active_checkpoint(tmp_path,b,checkpoint,reg)
    assert b.tick==10000 and before==runner._numeric_cache(b.data) and np.array_equal(state,runner.integration(b))
    assert not np.all(b.controllers[0].last_allocation==77)


def test_exact_sensor_ties():
    b=runner.new_body(42,PROFILE);s=b.clearance_sensor
    s.vertices=[np.zeros((2,3)) for _ in s.foot]
    s.data.geom_xpos[:]=0;s.data.geom_xmat[:]=np.eye(3).ravel()
    with patch('mujoco.mj_kinematics'):
        h,g,i=s.read(b.data.qpos)
    assert not h.any() and not i.any()
    np.testing.assert_array_equal(g,s.foot.reshape(6,5).min(axis=1))


def test_panel_count_and_no_source_control_substitution():
    assert CONTROL=='minimum-vertex-normal-retraction-v15'
    assert len(runner.panel('development'))==32 and len(runner.panel('evaluation'))==16
    assert (32+16+1)*4+100*runner.DT==196.01
    expected=[(p,s,list(case)) for s in (42,43) for case in runner.CASES for p in (CONTROL,PROFILE)]
    assert runner.panel('development')==expected


def test_immutable_golden_v14_native_state_and_adhesion():
    from flyarena.experiments.mechanical_v14 import CORE as OLD_CORE,_slices
    cs=_slices(OLD_CORE)
    with np.load(runner.GOLDEN,allow_pickle=False) as archive:
        rows=archive['values'][:101];ticks=archive['ticks'][:101]
    assert ticks[0]==3000
    c=AllocationHybridController(timestep=runner.DT);c.reset(seed=42);c.model_hash='a'*64
    for k in range(1,len(rows)):
        native=rows[k-1,cs['native_observation']]
        native=HybridControllerObservation(native[0],native[1:7],native[7:61].reshape(6,3,3),native[61:64])
        obs=replace(observation(int(ticks[k-1])),native=native,clearance=rows[k,cs['sensed_clearance']].copy(),
            minimum_geom=rows[k,cs['minimum_geom']].astype(np.int64),minimum_vertex=rows[k,cs['minimum_vertex']].astype(np.int64))
        action=c.step(rows[k,cs['input']],obs)
        for field,attr in [('retraction','retraction_correction'),('stumbling','stumbling_correction'),('persistence','retraction_persistence_counter'),('trigger_mask','last_trigger')]:
            np.testing.assert_array_equal(getattr(c,attr),rows[k,cs[field]])
        np.testing.assert_array_equal(c.cpg_network.curr_phases,rows[k,cs['phases']])
        np.testing.assert_array_equal(c.cpg_network.curr_magnitudes,rows[k,cs['magnitudes']])
        np.testing.assert_array_equal(action.adhesion_onoff,rows[k,cs['adhesion']])


def test_unchanged_tickzero_partial_and_invalid_cycle_semantics():
    from test_behavior_v12_correction import (
        test_tick_zero_interval_index_is_unowned,
        test_partition_distinguishes_boundary_partial_and_complete_run,
        test_invalid_interior_phase_fails_cycle_gates_closed,
        test_bad_increment_in_boundary_partial_is_invalid_not_partial,
        test_registered_zero_control_keeps_phase_semantics_separate,
    )
    for check in (test_tick_zero_interval_index_is_unowned,
                  test_partition_distinguishes_boundary_partial_and_complete_run,
                  test_invalid_interior_phase_fails_cycle_gates_closed,
                  test_bad_increment_in_boundary_partial_is_invalid_not_partial,
                  test_registered_zero_control_keeps_phase_semantics_separate):check()


def test_compiled_range_intersection_and_missing_map_rejection():
    b=runner.new_body(42,PROFILE);m=b.model;c=b.controllers[0]
    j=int(m.actuator_trnid[0,0]);m.jnt_limited[j]=1;m.jnt_range[j]=[-1,2]
    m.actuator_ctrllimited[0]=1;m.actuator_ctrlrange[0]=[-.5,3]
    sensor=runner.AllocationSensor(m,c)
    where=np.argwhere(sensor.indices==0)[0]
    assert sensor.lower[tuple(where)]==-.5 and sensor.upper[tuple(where)]==2
    m.actuator_trnid[0,0]=m.actuator_trnid[1,0]
    with pytest.raises(ValueError):runner.AllocationSensor(m,c)


@pytest.mark.parametrize('profile',[CONTROL,PROFILE])
def test_recorded_controller_equations_and_tamper_detection(profile):
    from flyarena.experiments.verify_v16 import verify_phase_law,verify_retraction_and_commands
    c=controller() if profile==PROFILE else V15Controller(timestep=runner.DT)
    if profile==CONTROL:c.reset(seed=42);c.model_hash="a"*64
    cs=runner._slices(runner.CORE);rows=np.zeros((31,runner._width(runner.CORE)))
    def record(k,obs):
        n=obs.native
        rows[k,cs['native_observation']]=np.r_[n.thorax_z,n.tarsus5_z,n.stumbling_contact_forces.ravel(),n.fly_heading]
        for field,attr in [('phases','curr_phases'),('magnitudes','curr_magnitudes'),('targets','intrinsic_amps')]:rows[k,cs[field]]=getattr(c.cpg_network,attr)
        for field,attr in [('retraction','retraction_correction'),('stumbling','stumbling_correction'),('persistence','retraction_persistence_counter'),('sensed_clearance','last_clearance'),('trigger_mask','last_trigger'),('minimum_geom','last_minimum_geom'),('minimum_vertex','last_minimum_vertex')]:rows[k,cs[field]]=getattr(c,attr)
        rows[k,cs['net_correction']]=c.last_info.get('net_corrections',np.zeros(6))
        rows[k,cs['ctrl']]=np.r_[c._last_angles,c._last_adhesion];rows[k,cs['adhesion']]=c._last_adhesion
        rows[k,cs['native_template']]=c.preprogrammed_steps.get_joint_angles_by_dof_order(c.cpg_network.curr_phases,c.cpg_network.curr_magnitudes)
        rows[k,cs['allocation']]=getattr(c,'last_allocation',np.zeros((6,7))).ravel()
        rows[k,cs['allocation_diagnostics']]=getattr(c,'last_allocation_diagnostics',np.zeros((6,8))).ravel()
        rows[k,cs['observation_tick']]=getattr(c,'last_observation_tick',-1)
        rows[k,cs['relaxation_diagnostics']]=getattr(c,'last_relaxation_diagnostics',np.zeros((6,5))).ravel()
    c._last_adhesion=np.array([c._get_adhesion_onoff(l,p) for l,p in zip(c.legs,c.cpg_network.curr_phases)])
    record(0,observation())
    for k in range(1,31):
        obs=observation(k-1)
        c.step([.2,.2],obs if profile==PROFILE else control_observation(obs))
        record(k,obs);rows[k,cs['input']]=[.2,.2]
    reg={'controller':{'coupling':c._base_coupling.tolist(),'phase_biases':c.cpg_network.phase_biases.tolist(),'release_end':c.release_end.tolist()}}
    verify_phase_law(rows,profile,reg);verify_retraction_and_commands(rows,profile,reg)
    bad=rows.copy();bad[10,cs['retraction']]+=1
    with pytest.raises(ValueError):verify_retraction_and_commands(bad,profile,reg)


@pytest.mark.parametrize('height,budget,branch',[(0.,.1,0),(0.,.04,1),(0.,.01,2),(.05,.1,0)])
def test_closedform_branches_budget_and_normal_feasibility(height,budget,branch):
    J=np.zeros((3,7));J[0,0]=J[1,1]=1;J[2,:3]=1
    q=np.zeros(7);lo=np.full(7,-np.inf);hi=-lo
    delta,d,r=normal_allocation(J,height,q,q,lo,hi,budget)
    assert r[0]==branch and np.linalg.norm(delta)<=budget+1e-15
    if branch==0:
        expected,old=v15_allocate(J,height,q,q,lo,hi,budget)
        np.testing.assert_array_equal(delta,expected);np.testing.assert_array_equal(d,old)
    elif branch==1:
        assert abs(height+J[2]@delta-.05)<1e-14
        # Any smaller nonnegative row-space coordinate in the fixed plane
        # cannot achieve D, even at the largest remaining null component.
        x,y,c=r[1:4];a=d[1];D=.05-height
        for smaller in (0.,y*.5,np.nextafter(y,0)):
            assert a*np.sqrt(max(0,budget**2-smaller**2))+c*smaller<=D+1e-14
        assert np.linalg.norm(J[:2]@delta)>0
    else:
        assert abs(J[2]@delta-budget*np.linalg.norm(J[2]))<1e-14 and d[5]>0


@pytest.mark.parametrize('boundary',[1.,3**.5])
def test_piecewise_boundary_continuity(boundary):
    J=np.zeros((3,7));J[0,0]=J[1,1]=1;J[2,:3]=1
    q=np.zeros(7);lo=np.full(7,-np.inf);b=.04;D=boundary*b
    values=[normal_allocation(J,.05-(D+e),q,q,lo,-lo,b)[0] for e in (-1e-12,0,1e-12)]
    # The circle-line tangent intersection has square-root continuity at
    # maximum authority, so no unjustified differentiability is asserted.
    assert np.linalg.norm(values[0]-values[1])<1e-6
    assert np.linalg.norm(values[2]-values[1])<1e-6


@pytest.mark.parametrize('sign',[-1,1])
def test_relaxed_signed_ray_clipping_and_mirrored_mapping(sign):
    J=np.zeros((3,7));J[0,0]=J[1,1]=1;J[2,:3]=1
    signs=np.array([sign,1,sign,1,1,1,1]);J=J*signs
    q=np.zeros(7);lo=np.full(7,-np.inf);hi=-lo;b=.04
    full,d,r=normal_allocation(J,0,q,q,lo,hi,b)
    index=int(np.argmax(abs(full)))
    if full[index]>0:hi[index]=full[index]/2
    else:lo[index]=full[index]/2
    clipped,d,r=normal_allocation(J,0,q,q,lo,hi,b)
    np.testing.assert_allclose(clipped,full/2,rtol=0,atol=1e-15)
    assert r[4]==.5 and int(d[7])&2 and d[5]>0
    assert np.all(q+clipped>=lo) and np.all(q+clipped<=hi)


def test_relaxed_tangent_basis_covariance_and_late_nonfinite_atomicity():
    J=np.zeros((3,7));J[0,0]=J[1,1]=1;J[2,:3]=1
    phi=.73;R=np.array([[np.cos(phi),-np.sin(phi),0],[np.sin(phi),np.cos(phi),0],[0,0,1]])
    q=np.zeros(7);lo=np.full(7,-np.inf)
    left=normal_allocation(J,0,q,q,lo,-lo,.04)[0]
    right=normal_allocation(R@J,0,q,q,lo,-lo,.04)[0]
    np.testing.assert_allclose(left,right,rtol=0,atol=1e-14)
    c=controller();obs=observation();before=pickle.dumps(c.checkpoint(),protocol=5)
    obs.jacobian[5]=np.finfo(float).max
    with np.errstate(over='ignore',invalid='ignore'):
        with pytest.raises(ValueError):c.step([.2,.2],obs)
    assert pickle.dumps(c.checkpoint(),protocol=5)==before


def test_feasible_and_budgetlimited_control_allocation_verifier():
    # Both actual model profiles are checked without integrating; controller
    # calls are these registered synthetic fixtures only.
    for profile in (CONTROL,PROFILE):
        body=runner.new_body(43,profile);sensor=body.clearance_sensor;c=body.controllers[0]
        recorder=runner.NativeRecorder(body);pre,_,_=recorder.row(np.zeros(2))
        h,g,i=sensor.read(body.data.qpos);native=HybridControllerObservation.from_sim(body.sim,'fly-0')
        obs=sensor.observation(native,body.data.qpos,0,h,g,i)
        action=c.step([.2,.2],obs);apply_locomotion_action(body.sim,'fly-0',action)
        post,_,_=recorder.row(np.array([.2,.2]));reg={'controller':{'allocation_joint_map':sensor.indices.tolist(),'release_end':c.release_end.tolist()}}
        verify_allocation_row(body.model,sensor.data,pre,post,list(zip(h,g,i)),reg,profile)
