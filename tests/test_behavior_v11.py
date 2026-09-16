"""Independent geometric/operational fixtures; no dynamics or controller trials."""
import json,pickle
from pathlib import Path
import numpy as np
import pytest
import mujoco as mj
from flyarena.experiments.realization_io_v11 import NumericChunks,exclusive_json,sha
from flyarena.experiments.realization_parser_v11 import parse_ap,contact_runs,support_envelope
from flyarena.experiments.realization_native_v11 import Native

@pytest.fixture(scope='module')
def native():return Native()

def test_parser_phase_complete_and_pep_ap_definition():
    # Analytic AP=-cos(theta): PEP at phase0, AEP at pi. Straddling
    # observation window ensures only internal cells are complete.
    phase=np.arange(1,49)*np.pi/4;ap=-np.cos(phase)
    result=parse_ap(phase,ap,0)
    complete=[x for x in result['intervals'] if x['complete']]
    assert len(complete)==4
    for s in complete:
        assert s['end_tick_inclusive']-s['start_tick']==8
        assert s['aep_tick']-s['start_tick']==4
        assert s['ambiguities']==[]
    assert result['intervals'][0]['kind']=='prefix' and result['intervals'][-1]['kind']=='suffix'

def test_parser_retains_ties_and_extra_reversals():
    phase=np.arange(40)*np.pi/4+.1
    wave=np.array([-1.,-1.,.3,.2,1.,.5,.6,0.])
    result=parse_ap(phase,np.tile(wave,5),100)
    assert sum(len(c['tie_ticks']) for c in result['cells'])==10
    complete=[s for s in result['intervals'] if s['complete']]
    assert complete and all('tied-PEP' in s['ambiguities'] and 'additional-reversals' in s['ambiguities'] for s in complete)
    assert all(len(s['reversal_ticks'])>=3 for s in complete)

def test_parser_retains_missing_cells_degenerate_and_rejects_nonmonotone():
    phase=np.array([.1,.2,4*np.pi+.1,4*np.pi+.2,6*np.pi+.1])
    p=parse_ap(phase,np.zeros(5),0)
    assert p['cells'][1]['missing']
    assert all(not x['complete'] for x in p['intervals'])
    assert any('degenerate-AP' in x['ambiguities'] for x in p['intervals'])
    with pytest.raises(ValueError):parse_ap([0,1,1],[0,1,2])

def test_contact_runs_preserve_original_and_one_sample():
    c=np.array([0,0,1,1,0,1,0,0,1,1,0]);phase=np.arange(len(c),dtype=float)
    r=contact_runs(c,phase,0)
    assert [(x['start_tick'],x['end_tick_exclusive']) for x in r if x['original_qualifying'] and not x['contact']]==[(6,8)]
    assert len(r)==7 and sum(x['dense_samples'] for x in r)==11
    assert len([x for x in r if x['dense_samples']==1])==3

def test_support_stitches_contact_gaps_without_hiding_motion():
    xyz=np.c_[np.array([0.,.02,.25,.04,.03]),np.zeros((5,2))]
    result=support_envelope(xyz,[1,0,0,0,1],[1,0,0,0,1])
    assert result['supported_displacement_mm']==.25
    assert result['largest_internal_unsupported_gap_ticks']==3
    assert result['positive_support_duty']==.4
    assert support_envelope(xyz,[0]*5,[0]*5)['supported_displacement_mm'] is None
    single=support_envelope(xyz,[0,0,1,0,0],[0]*5)
    assert single['supported_displacement_mm']==0 and single['status']=='single-sample-unresolved'

def test_reference_knots_single_conversion_and_native_order(native):
    with (native.raw/'sources/0114-single_steps_untethered.pkl').open('rb') as f:raw=pickle.load(f)
    names=['Coxa_yaw','Coxa','Coxa_roll','Femur','Femur_roll','Tibia','Tarsus1']
    length=len(raw['joint_LFCoxa']);indices=np.array([0,length//4,length//2,length-1])
    phase=indices/(length-1)*2*np.pi;actual=native.unit_targets(np.tile(phase[:,None],(1,6)))
    for l,leg in enumerate(['LF','LM','LH','RF','RM','RH']):
        expected=np.array([raw[f'joint_{leg}{name}'][indices] for name in names]).T
        if leg.startswith('R'):expected[:,[0,2,4]]*=-1
        np.testing.assert_allclose(actual[:,l*7:(l+1)*7],expected,rtol=0,atol=3e-15)
        if leg.startswith('R'):assert np.max(np.abs(expected[:,[0,2,4]]))>.01

def test_reference_transmission_is_force_zero(native):
    # Algebraic command substitution must yield zero native servo force without
    # integrating. This catches gear, order, bias and sign mistakes.
    m=native.model;d=mj.MjData(m);targets=np.linspace(-.2,.2,42)
    d.qpos[native.qadr]=native.targets_to_qpos(targets);d.ctrl[native.active]=targets
    mj.mj_forward(m,d)
    np.testing.assert_allclose(d.actuator_force[native.active],0,atol=2e-14)
    np.testing.assert_allclose(d.actuator_length[native.active],d.qpos[native.qadr]*m.actuator_gear[native.active,0],atol=1e-15)

def test_material_point_jacobians_all_native_active_passive_root_axes(native):
    m=native.model;d=mj.MjData(m);d.qpos[7:]=np.linspace(-.08,.08,66);mj.mj_forward(m,d)
    original=d.qpos.copy();epsilon=1e-6
    for leg in range(6):
        gid=native.foot[leg*5+4];bid=int(m.geom_bodyid[gid]);local=native.centroids[leg]
        point=d.geom_xmat[gid].reshape(3,3)@local+d.geom_xpos[gid]
        jac=np.zeros((3,m.nv));mj.mj_jac(m,d,jac,None,point,bid)
        # Include root and the leg's 11 DOFs; all42 active and24 passive across legs.
        dofs=list(range(6))+list(range(6+11*leg,6+11*(leg+1)))
        for dof in dofs:
            positions=[]
            for sign in [-1,1]:
                dd=mj.MjData(m);dd.qpos[:]=original
                if dof<3:dd.qpos[dof]+=sign*epsilon
                elif dof<6:
                    dd.qpos[3:7]=0;dd.qpos[3]=np.cos(epsilon/2);dd.qpos[4+dof-3]=sign*np.sin(epsilon/2)
                else:dd.qpos[7+dof-6]+=sign*epsilon
                mj.mj_kinematics(m,dd)
                positions.append(dd.geom_xmat[gid].reshape(3,3)@local+dd.geom_xpos[gid])
            np.testing.assert_allclose((positions[1]-positions[0])/(2*epsilon),jac[:,dof],rtol=1e-6,atol=2e-9)

def test_whole_mesh_clearance_against_explicit_world_vertices(native):
    m=native.model;d=mj.MjData(m);d.qpos[7:]=np.linspace(.1,-.1,66);mj.mj_kinematics(m,d)
    gp=np.tile(d.geom_xpos[native.foot],(2,3,1,1));gr=np.tile(d.geom_xmat[native.foot].reshape(30,3,3),(2,3,1,1,1))
    tp=np.tile(d.xpos[native.thorax],(2,1));tr=np.tile(d.xmat[native.thorax].reshape(3,3),(2,1,1))
    low,world,body=native.geometry(gp,gr,tp,tr)
    for j,v in enumerate(native.vertices):
        explicit=np.array([gr[0,0,j]@vertex+gp[0,0,j] for vertex in v])
        assert low[0,0,j//5,j%5]==pytest.approx(explicit[:,2].min(),abs=1e-14)
        if j%5==4:np.testing.assert_allclose(world[0,0,j//5],explicit.mean(axis=0),atol=2e-14)
    np.testing.assert_allclose(np.einsum('nkd,nrld->nrlk',tr,body)+tp[:,None,None,:],world,atol=1e-14)

def test_native_normal_support_balance_without_integration(native):
    m=native.model;d=mj.MjData(m)
    # Fixed neutral state is not a trial; mj_forward only evaluates forces.
    flags,forces,penetrating,residual=native.observe(d.qpos,d.qvel,d.ctrl,0,True)
    assert np.isfinite(forces).all() and (forces>=0).all() and residual<1e-6
    assert (penetrating<=forces.reshape(6,5).sum(axis=1)+1e-12).all()

def test_incremental_fixed_schema_exclusive_and_nonfinite(tmp_path):
    w=NumericChunks(tmp_path/'x',2,{'file':'reserved','allow_pickle':'metadata only'},chunk_size=2)
    w.append(0,[1.,2.]);w.append(1,[3.,4.]);w.append(2,[5.,6.])
    with pytest.raises(ValueError):w.append(3,[np.nan,0])
    term=w.finish({'type':'fixture','message':'invalid row'})
    assert term['initialized_rows']==3 and term['committed_rows']==3 and not term['complete']
    with np.load(tmp_path/'x/chunk-00001.npz',allow_pickle=False) as z:
        assert set(z.files)=={'ticks','values'};np.testing.assert_array_equal(z['values'],[[5,6]])
    with pytest.raises(FileExistsError):NumericChunks(tmp_path/'x',2,{})

def test_flush_failure_keeps_primary_and_emergency(tmp_path,monkeypatch):
    w=NumericChunks(tmp_path/'x',1,{});w.append(6000,[2.])
    def fail():raise OSError('simulated full disk')
    monkeypatch.setattr(w,'flush',fail)
    term=w.finish({'type':'primary','message':'source mismatch'})
    assert term['primary_failure']['type']=='primary' and not term['complete']
    with np.load(tmp_path/'x/emergency-prefix.npz',allow_pickle=False) as z:np.testing.assert_array_equal(z['ticks'],[6000])
    assert term['retention_failures'][0]['stage']=='flush'

def test_terminal_failure_retained_in_fallback(tmp_path,monkeypatch):
    import flyarena.experiments.realization_io_v11 as io
    monkeypatch.setattr(io,'SCRATCH',tmp_path/'scratch')
    original=io.exclusive_json
    def fail(path,value):
        if path.name=='terminal.json':raise OSError('terminal fault')
        return original(path,value)
    w=NumericChunks(tmp_path/'x',1,{});w.append(0,[1.]);monkeypatch.setattr(io,'exclusive_json',fail)
    term=w.finish()
    assert not term['complete'] and len(list((tmp_path/'scratch').glob('*.json')))==1

def test_total_filesystem_failure_explicit(tmp_path,monkeypatch,capsys):
    import flyarena.experiments.realization_io_v11 as io
    w=NumericChunks(tmp_path/'x',1,{})
    def fail(*args,**kwargs):raise OSError('all receipts fail')
    monkeypatch.setattr(io,'exclusive_json',fail)
    result=w.finish({'message':'original failure'})
    assert not result['complete'] and 'TOTAL FILESYSTEM FAILURE' in capsys.readouterr().err

def test_json_nan_cannot_leave_empty_artifact(tmp_path):
    p=tmp_path/'x.json'
    with pytest.raises(ValueError):exclusive_json(p,{'bad':float('nan')})
    assert not p.exists()

def test_trial_input_failure_retains_initialized_case(tmp_path,monkeypatch):
    import flyarena.experiments.realization_v11 as audit
    out=tmp_path/'evidence';(out/'cases'/'fixture').mkdir(parents=True)
    exclusive_json(out/'registration.json',{'fixture':True})
    monkeypatch.setattr(audit,'OUT',out)
    def broken(*args,**kwargs):raise ValueError('registered raw hash mismatch')
    monkeypatch.setattr(audit,'read_raw',broken)
    class Budget:
        def check(self):return {}
    with pytest.raises(RuntimeError,match='raw hash mismatch'):
        audit.run_trial({'id':'fixture','raw':str(tmp_path)}, {'core_schema':[['x',1]]}, {}, {}, Budget())
    terminal=json.loads((out/'cases/fixture/dense/terminal.json').read_text())
    assert terminal['initialized_rows']==0 and not terminal['complete']
    assert terminal['primary_failure']['type']=='ValueError'

def test_audit_sources_contain_no_stepping_reset_or_controller_construction():
    import ast
    import flyarena.experiments.realization_v11 as audit
    source=Path(audit.__file__).parent
    forbidden={'mj_step','mj_step1','mj_step2','mj_resetData','reset','step','HybridController','HybridTurningController','CadenceHybridController','Bodies'}
    for p in source.glob('realization*_v11.py'):
        tree=ast.parse(p.read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.Call):
                called=node.func.attr if isinstance(node.func,ast.Attribute) else node.func.id if isinstance(node.func,ast.Name) else ''
                assert called not in forbidden,(p,called)
