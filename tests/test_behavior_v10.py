"""Controller/evidence/native-geometry contracts, not physical qualification."""
import json
import pickle
from pathlib import Path
import numpy as np
import pytest
import mujoco as mj
from flygym_demo.complex_terrain.cpg_controller import calculate_ddt
from flygym_demo.complex_terrain.hybrid_controller import HybridControllerObservation
from flygym_demo.complex_terrain.common import apply_locomotion_action
from flyarena.experiments.cadence_v10 import CadenceHybridController
from flyarena.experiments.evidence_v10 import NumericEvidence
from flyarena.experiments.mechanical_v10 import new_body, PROFILE, foot_ids
from flyarena.experiments.verify_v10 import complete_runs, read_stream


def observation():
    return HybridControllerObservation(1.,np.zeros(6),np.zeros((6,3,3)),np.array([1.,0.,0.]))


def test_entire_phase_derivative_and_unscaled_amplitude():
    c=CadenceHybridController(timestep=.0001);c.reset(seed=42)
    n=c.cpg_network
    n.curr_magnitudes[:]=np.linspace(.1,.6,6)
    theta=n.curr_phases.copy();r=n.curr_magnitudes.copy()
    target=np.repeat([.36,.84],3)
    dtheta,dr=calculate_ddt(theta,r,c._base_coupling,n.phase_biases,c._base_intrinsic_freqs,target,np.full(6,20.))
    c.step([.12,.28],observation())
    np.testing.assert_allclose(n.curr_phases,theta+.0001*(.2/.6)*dtheta,rtol=0,atol=1e-15)
    np.testing.assert_array_equal(n.curr_magnitudes,r+.0001*dr)
    np.testing.assert_array_equal(n.convergence_coefs,np.full(6,20.))
    assert n.timestep==.0001


def test_full_silence_reset_resume_and_checkpoint():
    c=CadenceHybridController(timestep=.0001);c.reset(seed=43)
    before=pickle.dumps(c.checkpoint())
    for _ in range(20):
        action=c.step([0,0],None)
        assert pickle.dumps(c.checkpoint())==before
    expected=c.preprogrammed_steps.get_joint_angles_by_dof_order(c.cpg_network.curr_phases,np.zeros(6))
    np.testing.assert_array_equal(action.joint_angles,expected)
    for _ in range(21):c.step([.04,.36],observation())
    state=c.checkpoint();hold=c.step([1e-4,1e-4],None)
    assert pickle.dumps(c.checkpoint())==pickle.dumps(state)
    hold.joint_angles[:]=9;hold.adhesion_onoff[:]=False
    assert pickle.dumps(c.checkpoint())==pickle.dumps(state)
    expected=[]
    for _ in range(40):
        action=c.step([.28,.12],observation());expected.append((action.joint_angles,action.adhesion_onoff))
    final=pickle.dumps(c.checkpoint());c.reset(seed=0);c.restore(state)
    for angles,adhesion in expected:
        action=c.step([.28,.12],observation())
        np.testing.assert_array_equal(action.joint_angles,angles)
        np.testing.assert_array_equal(action.adhesion_onoff,adhesion)
    assert pickle.dumps(c.checkpoint())==final
    # RNG/reset continuation is part of checkpoint even though step is deterministic.
    c.restore(state);c.reset();phases=c.cpg_network.curr_phases.copy()
    c.restore(state);c.reset();np.testing.assert_array_equal(c.cpg_network.curr_phases,phases)


@pytest.mark.parametrize('u',[[1,1],[0,.2],[-.1,.2],[np.nan,0],[np.inf,0],[.2]])
def test_invalid_input_does_not_mutate(u):
    c=CadenceHybridController(timestep=.0001);state=pickle.dumps(c.checkpoint())
    with pytest.raises(ValueError):c.step(u,None)
    assert pickle.dumps(c.checkpoint())==state


def test_exception_prefix_failing_state_optional_snapshot(tmp_path):
    e=NumericEvidence(tmp_path/'run',2,chunk_size=2,metadata={'file':'reserved','allow_pickle':False})
    e.append(0,[1,2]);e.append(1,[3,4]);e.append(2,[5,6])
    def broken():raise RuntimeError('optional snapshot failed')
    term=e.finish(FloatingPointError('primary physical failure'),failing_values=[np.nan,np.inf],snapshot=broken)
    assert not term['complete'] and term['initialized_rows']==3
    assert term['primary_failure']['message']=='primary physical failure'
    assert term['retention_failures'][0]['stage']=='optional-snapshot'
    arrays=[np.load(p,allow_pickle=False) for p in sorted((tmp_path/'run').glob('chunk-*.npz'))]
    np.testing.assert_array_equal(np.concatenate([a['values'] for a in arrays]),[[1,2],[3,4],[5,6]])
    with np.load(tmp_path/'run/failing-state.npz',allow_pickle=False) as a:assert np.isnan(a['values'][0])
    with pytest.raises(FileExistsError):NumericEvidence(tmp_path/'run',2)


def test_emergency_prefix_and_terminal_on_flush_failure(tmp_path,monkeypatch):
    e=NumericEvidence(tmp_path/'run',2);e.append(0,[1,2])
    def broken():raise OSError('chunk disk error')
    monkeypatch.setattr(e,'flush',broken)
    term=e.finish(RuntimeError('budget exceeded'),snapshot=lambda:np.array([1,2]))
    assert term['primary_failure']['message']=='budget exceeded'
    assert term['retention_failures'][0]['stage']=='prefix'
    with np.load(tmp_path/'run/emergency-prefix.npz',allow_pickle=False) as a:
        np.testing.assert_array_equal(a['values'],[[1,2]])
    assert (tmp_path/'run/terminal.json').is_file()


def test_archive_validation_and_no_uninitialized_tail(tmp_path):
    e=NumericEvidence(tmp_path/'run',2);e.append(0,[1,2]);e.append(1,[3,4]);e.finish()
    t,v=read_stream(tmp_path/'run',2,2,1)
    assert v.shape==(2,2)
    with pytest.raises(ValueError):read_stream(tmp_path/'run',3,2,1)
    with pytest.raises(ValueError):e.append(2,[np.nan,0])


def test_cycle_boundaries_exclude_partial_and_keep_flicker():
    contact=np.array([0,0,1,1,0,1,0,0,1,1,0])
    phase=np.arange(len(contact),dtype=float)
    assert complete_runs(contact,phase,False,0,10)==[(6,8)]
    # A one-tick contact-free interval has no phase advance; its missing geometry
    # does not become a complete cycle. Multi-tick flickers remain included.
    assert complete_runs(contact,phase,True,0,10)==[(2,4),(8,10)]


def test_native_transmissions_axes_and_exact_single_sign_conversion():
    b=new_body(42,PROFILE);m=b.model;d=b.data;c=b.controllers[0]
    assert m.nu==48 and np.count_nonzero(m.jnt_limited)==0
    action=c.step([0,0],None);apply_locomotion_action(b.sim,'fly-0',action)
    np.testing.assert_array_equal(d.ctrl[:42],action.joint_angles)
    np.testing.assert_array_equal(d.ctrl[42:],action.adhesion_onoff)
    # Independent geometry derivative: named native joint axis agrees with the
    # actual displaced distal body Jacobian. Both sides and all 42 axes tested.
    foot=foot_ids(m);q0=d.qpos.copy()
    for actuator in range(42):
        jid=int(m.actuator_trnid[actuator,0]);assert int(m.actuator_trntype[actuator])==0
        name=mj.mj_id2name(m,mj.mjtObj.mjOBJ_JOINT,jid)
        assert name and '-position' not in name
        leg=actuator//7;bid=int(m.geom_bodyid[foot[leg*5+4]])
        d.qpos[:]=q0;mj.mj_forward(m,d)
        jac=np.zeros((3,m.nv));jr=np.zeros((3,m.nv));mj.mj_jacBody(m,d,jac,jr,bid)
        prior=d.xpos[bid].copy();adr=int(m.jnt_qposadr[jid]);d.qpos[adr]+=1e-7;mj.mj_forward(m,d)
        np.testing.assert_allclose((d.xpos[bid]-prior)/1e-7,jac[:,m.jnt_dofadr[jid]],atol=2e-6,rtol=2e-5)
    asset=Path(__import__('flygym_demo.complex_terrain',fromlist=['x']).__file__).parent/'assets/single_steps_untethered.pkl'
    with asset.open('rb') as f:raw=pickle.load(f)
    legacy=['Coxa','Coxa_roll','Coxa_yaw','Femur','Femur_roll','Tibia','Tarsus1']
    for leg in c.legs:
        expected=np.array([raw[f'joint_{leg.upper()}{joint}'][0] for joint in legacy])
        if leg.startswith('r'):expected[[1,2,4]]*=-1
        np.testing.assert_allclose(c.preprogrammed_steps.get_joint_angles(leg,0,1),expected,rtol=0,atol=1e-15)
