"""Nonphysical v13 controller, source, schedule and paired-data contracts."""
import copy
import pickle
from unittest.mock import patch
import numpy as np
import pytest
from flygym_demo.complex_terrain.cpg_controller import calculate_ddt
from flygym_demo.complex_terrain.hybrid_controller import HybridControllerObservation
from flygym_demo.complex_terrain.turning_controller import HybridTurningController
from flyarena.experiments.cadence_v12 import ExcursionHybridController
from flyarena.experiments.cadence_v13 import StanceTimingHybridController, phase_gains, PROFILE, CONTROL, NATIVE
from flyarena.experiments import mechanical_v13 as runner
from flyarena.experiments.verify_v13 import verify_phase_law


def observation():
    return HybridControllerObservation(1.,np.zeros(6),np.zeros((6,3,3)),np.array([1.,0.,0.]))


@pytest.mark.parametrize('common,asymmetry',[(.08,0),(.2,0),(.4,0),(.2,-.8),(.2,.8)])
def test_preupdate_complete_phase_derivative_and_physical_time_amplitude(common,asymmetry):
    c=StanceTimingHybridController(timestep=runner.DT);c.reset(seed=42)
    for _ in range(40):
        theta=c.cpg_network.curr_phases.copy();r=c.cpg_network.curr_magnitudes.copy()
        desired=np.repeat([1-asymmetry,1+asymmetry],3)
        derivative,amplitude=calculate_ddt(theta,r,c._base_coupling,c.cpg_network.phase_biases,c._base_intrinsic_freqs,desired,np.full(6,20.))
        wrapped=theta%(2*np.pi);end=c.release_end
        gain=np.where((wrapped>0)&(wrapped<end),1.,(2*np.pi-end)/(2*np.pi/(common/.6)-end))
        action=c.step([common*(1-asymmetry),common*(1+asymmetry)],observation())
        np.testing.assert_allclose(c.cpg_network.curr_phases,theta+runner.DT*gain*derivative,rtol=0,atol=2e-15)
        np.testing.assert_allclose(c.cpg_network.curr_magnitudes,r+runner.DT*amplitude,rtol=0,atol=2e-15)
        assert np.array_equal(action.adhesion_onoff,[c._get_adhesion_onoff(leg,p) for leg,p in zip(c.legs,c.cpg_network.curr_phases)])


def test_strict_release_boundaries_and_native_algebra():
    c=StanceTimingHybridController(timestep=runner.DT);end=c.release_end
    for theta in [np.zeros(6),end.copy(),np.full(6,2*np.pi)]:
        np.testing.assert_allclose(phase_gains(theta,end,1/3),(2*np.pi-end)/(6*np.pi-end),rtol=0,atol=0)
    assert np.array_equal(phase_gains(end/2,end,1/3),np.ones(6))
    assert np.array_equal(phase_gains(np.arange(6.),end,1),np.ones(6))
    swing=end/(2*np.pi*12);stance=(2*np.pi/(1/3)-end)/(2*np.pi*12)
    np.testing.assert_allclose(swing+stance,np.full(6,1/4),rtol=0,atol=1e-16)


@pytest.mark.parametrize('bad',[[1,1],[0,.2],[-.1,.2],[np.nan,0],[.2]])
def test_input_rejection_is_atomic(bad):
    c=StanceTimingHybridController(timestep=runner.DT);before=pickle.dumps(c.checkpoint(),protocol=5)
    with pytest.raises(ValueError):c.step(bad,None)
    assert pickle.dumps(c.checkpoint(),protocol=5)==before


def test_silence_holds_entire_state_rng_actions_and_restore_exact():
    c=StanceTimingHybridController(timestep=runner.DT);c.reset(seed=43)
    for _ in range(100):c.step([.2,.2],observation())
    checkpoint=c.checkpoint();before=pickle.dumps(checkpoint,protocol=5)
    for _ in range(100):
        action=c.step([0,0],None)
        assert np.array_equal(action.joint_angles,c._last_angles)
    assert pickle.dumps(c.checkpoint(),protocol=5)==before
    expected=[c.step([.12,.28],observation()).joint_angles for _ in range(100)]
    c.restore(checkpoint)
    actual=[c.step([.12,.28],observation()).joint_angles for _ in range(100)]
    assert np.array_equal(expected,actual)


def test_native_reference_has_no_wrapper_and_common_seeded_reset_without_physics():
    def forbidden(*args,**kwargs):raise AssertionError('unregistered physical integration')
    with patch('mujoco.mj_step',side_effect=forbidden):
        bodies=[runner.new_body(42,profile) for profile in (CONTROL,PROFILE,NATIVE)]
    control,candidate,native=[body.controllers[0] for body in bodies]
    assert type(control) is ExcursionHybridController
    assert type(native) is HybridTurningController
    for body in bodies:
        assert body.tick==0 and body.data.time==0
        assert np.array_equal(body.data.qpos,bodies[0].data.qpos)
        assert np.array_equal(runner.integration(body),runner.integration(bodies[0]))
        assert np.array_equal(body.controllers[0].cpg_network.curr_phases,control.cpg_network.curr_phases)
        assert np.array_equal(body.controllers[0].cpg_network.curr_magnitudes,np.zeros(6))
    phase=native.cpg_network.curr_phases.copy();native.step([0,0],observation())
    assert np.all(native.cpg_network.curr_phases>phase)
    candidate.step([0,0],None);assert np.array_equal(candidate.cpg_network.curr_phases,phase)


def test_native_body_and_reflex_constants_unchanged():
    c=StanceTimingHybridController(timestep=runner.DT);v=ExcursionHybridController(timestep=runner.DT)
    for key in ('retraction_rates','stumbling_rates','max_correction','swing_extension','retraction_persistence_steps','retraction_persistence_initiation_threshold','enable_adhesion','stumbling_force_threshold','retraction_height_threshold'):
        assert getattr(c,key)==getattr(v,key)
    assert np.array_equal(c.cpg_network.phase_biases,v.cpg_network.phase_biases)
    for leg in c.legs:
        assert c.preprogrammed_steps.swing_period[leg][0]==0
        assert 0<c.preprogrammed_steps.swing_period[leg][1]+np.pi/4<2*np.pi


def test_exact_prospective_order_and_physical_budget():
    plan=runner.panel('development')
    assert len(plan)==34
    for seed in (42,43):
        part=plan[(seed-42)*16:(seed-41)*16]
        assert part==[(profile,seed,list(case)) for case in runner.CASES for profile in (CONTROL,PROFILE)]
    assert plan[-2:]==[(NATIVE,42,['native-nominal',1.,0.]),(NATIVE,43,['native-nominal',1.,0.])]
    assert len(runner.panel('evaluation'))==16 and len(runner.panel('repeat'))==1
    assert 34*4==136
    assert (34+16+1)*4+runner.CONTINUATION_TICKS*runner.DT==204.01


def test_recorded_phase_equation_verifier_rejects_hidden_uniform_gain():
    c=StanceTimingHybridController(timestep=runner.DT);c.reset(seed=42)
    cs=runner._slices(runner.CORE);rows=np.zeros((101,runner._width(runner.CORE)))
    fields={'phases':'curr_phases','magnitudes':'curr_magnitudes','targets':'intrinsic_amps'}
    for index in range(101):
        if index:c.step([.2,.2],observation())
        rows[index,cs['input']]=[.2,.2]
        for field,attr in fields.items():rows[index,cs[field]]=getattr(c.cpg_network,attr)
    registration={'controller':{'coupling':c._base_coupling.tolist(),'phase_biases':c.cpg_network.phase_biases.tolist(),'release_end':c.release_end.tolist()}}
    assert verify_phase_law(rows,PROFILE,registration)['max_phase_equation_error']<5e-12
    with pytest.raises(ValueError):verify_phase_law(rows,CONTROL,registration)
