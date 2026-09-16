"""Registered single-worker v10 mechanical experiment; no production toggle."""
from __future__ import annotations
import argparse
from copy import deepcopy
import importlib.metadata
import json
import os
from pathlib import Path
import resource
import shutil
import sys
import time
import traceback
import numpy as np
import mujoco as mj
from flygym.anatomy import LEGS
from flygym.compose import ActuatorType
from flygym_demo.complex_terrain.common import apply_locomotion_action, get_default_locomotion_dof_order
from flygym_demo.complex_terrain.hybrid_controller import HybridControllerObservation
from ..body import Bodies
from ..common import ROOT, file_sha, write_json
from .cadence_v10 import CadenceHybridController, PROFILE
from .evidence_v10 import NumericEvidence

ORIGINAL = Path('/Users/lexa/Desktop/lexa/omega/fly-arena')
APPROVAL = ORIGINAL / 'var/sshx/behavior-v10/approved-plan.json'
SUBJECTS = ORIGINAL / 'var/sshx/sensorimotor-v7/subjects.json'
DT = .0001
SCENE = {'size': 100, 'obstacles': [], 'spawns': [[0, 0, 0]]}
CASES = [('zero',0.,0.), ('straight-008',.08,0.), ('straight-02',.2,0.),
         ('straight-04',.4,0.), ('turn-negative-04',.2,-.4), ('turn-positive-04',.2,.4),
         ('turn-negative-08',.2,-.8), ('turn-positive-08',.2,.8)]
CORE = [('qpos',73), ('qvel',72), ('thorax_position',3), ('thorax_rotation',9),
        ('input',2), ('ctrl',48), ('actuator_force',48), ('phases',6), ('magnitudes',6),
        ('retraction',6), ('stumbling',6), ('persistence',6), ('net_correction',6),
        ('foot_contact',6)]
GEOMETRY = [('geom_position',90), ('geom_rotation',270)]


def slices(schema):
    out = {}; offset = 0
    for name, count in schema:
        out[name] = slice(offset, offset+count); offset += count
    return out


def new_body(seed, profile):
    b = Bodies(deepcopy(SCENE), 1, seed)
    if profile == PROFILE:
        c = CadenceHybridController(timestep=DT)
        c.reset(seed=seed)
        b.controllers[0] = c
        apply_locomotion_action(b.sim, 'fly-0', c.step(np.zeros(2), None))
    elif profile != 'historical':
        raise ValueError(profile)
    return b


def foot_ids(model):
    return np.array([mj.mj_name2id(model, mj.mjtObj.mjOBJ_GEOM, f'fly-0/{leg}_tarsus{i}')
                     for leg in LEGS for i in range(1,6)], dtype=int)


def source_files():
    paths = list((ROOT/'src').rglob('*.py')) + list((ROOT/'scripts').glob('*v10*')) + list((ROOT/'tests').glob('*v10*'))
    site = ORIGINAL/'.venv/lib/python3.12/site-packages'
    for package in ['flygym', 'flygym_demo']:
        paths += [p for p in (site/package).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc']
    # Exact MuJoCo extension/shared library and metadata, in addition to Python source.
    paths += [p for p in (site/'mujoco').rglob('*') if p.is_file() and p.suffix in ('.so','.dylib','.py')]
    return sorted(set(paths))


def freeze(root):
    root.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(APPROVAL, root/'approved-plan.json')
    shutil.copyfile(SUBJECTS, root/'subjects.json')
    sources = {}
    for i, p in enumerate(source_files()):
        dest = root/'sources'/f'{i:04d}-{p.name}'
        dest.parent.mkdir(exist_ok=True)
        shutil.copyfile(p,dest)
        sources[str(p)] = {'sha256':file_sha(p), 'archive':str(dest.relative_to(root))}
    write_json(root/'sources.json',sources)
    subjects = json.loads(SUBJECTS.read_text())
    artifacts = {}
    for s in subjects:
        p = ORIGINAL/'var/artifacts'/s['artifact_id']
        artifacts[s['id']] = {str(f):file_sha(f) for f in sorted(p.iterdir()) if f.is_file()}
    # Hash canonical graph/readout data once, without modifying or loading a brain.
    graph = {str(p):file_sha(p) for p in sorted((ORIGINAL/'data/connectome').glob('*')) if p.is_file()}
    graph.update({str(p):file_sha(p) for p in sorted((ORIGINAL/'data/connectome/research-v2').glob('*')) if p.is_file()})
    b = new_body(42,PROFILE); m=b.model
    mj.mj_saveModel(m,str(root/'model.mjb'))
    foot = foot_ids(m)
    if len(set(foot.tolist())) != 30 or np.any(foot < 0):
        raise ValueError('missing native foot collision geometries')
    if list(b.controllers[0].legs) != list(LEGS):
        raise ValueError('controller leg order mismatch')
    native_order = b.sim.world.fly_lookup['fly-0'].get_actuated_jointdofs_order(ActuatorType.POSITION)
    if list(native_order) != get_default_locomotion_dof_order():
        raise ValueError('native actuator order mismatch')
    arrays = {}
    for attr in ['jnt_axis','jnt_pos','jnt_type','jnt_limited','jnt_range','jnt_qposadr','jnt_dofadr',
                 'actuator_trntype','actuator_trnid','actuator_gear','actuator_gainprm','actuator_biasprm',
                 'actuator_forcerange','actuator_forcelimited','actuator_ctrlrange','actuator_ctrllimited',
                 'geom_type','geom_dataid','geom_bodyid','geom_contype','geom_conaffinity','geom_friction',
                 'mesh_vert','mesh_vertadr','mesh_vertnum','mesh_face','mesh_faceadr','mesh_facenum',
                 'body_mass','body_inertia','dof_damping','qpos0']:
        a=np.asarray(getattr(m,attr)); p=root/f'model-{attr}.npy'; np.save(p,a,allow_pickle=False)
        arrays[attr]={'sha256':file_sha(p),'shape':list(a.shape),'dtype':str(a.dtype)}
    names = {kind:[mj.mj_id2name(m,obj,i) for i in range(n)] for kind,obj,n in [
        ('joint',mj.mjtObj.mjOBJ_JOINT,m.njnt),('actuator',mj.mjtObj.mjOBJ_ACTUATOR,m.nu),
        ('geom',mj.mjtObj.mjOBJ_GEOM,m.ngeom),('body',mj.mjtObj.mjOBJ_BODY,m.nbody)]}
    write_json(root/'model-names.json',names)
    c=b.controllers[0]
    registration = {
      'schema':'mechanical-registration/v10', 'candidate':PROFILE, 'approved_plan_sha256':file_sha(APPROVAL),
      'source_base':'064fa96bc5438986b9aa7aa4f92354484a5cd7b2',
      'sources_sha256':file_sha(root/'sources.json'),'model_sha256':file_sha(root/'model.mjb'),
      'subjects_sha256':file_sha(SUBJECTS),'artifacts':artifacts,'graph':graph,'compiled_arrays':arrays,
      'native_names_sha256':file_sha(root/'model-names.json'),
      'dependencies':{p:importlib.metadata.version(p) for p in ['numpy','scipy','mujoco','flygym']},
      'scene':SCENE,'dt':DT,'ticks':40000,'active_input_ticks':[3000,25000], 'steady_state_ticks':[6000,25000],
      'stop_state_ticks':[30000,40000], 'core_schema':CORE,'geometry_schema':GEOMETRY,
      'core_stride':1,'geometry_stride':10,'chunk_rows':1000,
      'profiles':['historical',PROFILE], 'development_seeds':[42,43], 'evaluation_seeds':[31042,31043],
      'cases':CASES,'repeat':[PROFILE,'straight-02',31042],
      'controller':{'nominal':.6,'silent_common_max':1e-4,'domain':'u finite nonnegative shape(2); mean<=.4; abs(asymmetry)<=.8 (convex outer v4 domain); validation tolerance1e-12',
         'active':'u=c*[1-a,1+a]; target amplitudes .6*[1-a]*3+.6*[1+a]*3; both native frequency and coupling multiplied by c/.6; timestep unchanged',
         'frequency':c._base_intrinsic_freqs.tolist(),'coupling':c._base_coupling.tolist(),
         'convergence':c.cpg_network.convergence_coefs.tolist(),'bias':c.cpg_network.phase_biases.tolist(),
         'silent':'hold entire controller state and exact last angles AND adhesion; seeded zero magnitude reset uses native hybrid adhesion including swing extension; no silent RNG consumption',
         'checkpoint':'versioned deep copy all controller members including CPG, reset bases, RNG, spline assets and last command; MuJoCo mjSTATE_INTEGRATION plus tick/drives; continuation 100 ticks bitwise'},
      'measurement':{
         'time':'row k is state after k integrations; row0 initial; force is actual force used by completed integration k (zero for initial); control row k drove interval k-1..k',
         'geometry':'diagnostic-only MjData receives qpos/qvel then mj_forward each tick; actual controller observation path untouched; transforms/contacts at exact row time',
         'foot_geom_ids':foot.tolist(),'foot_links':'all tarsus1..5 collision meshes per named leg, ground plane z=0',
         'contact':'any foot tarsus1..5 has actual MuJoCo ground contact distance<=0; no force threshold/debounce',
         'cycles':'maximal constant contact/noncontact runs bounded by opposite contact samples within inclusive steady window; phase at end>phase at start; every run included, no duration filter. Swing=bounded noncontact run; stance=bounded contact run. Require >=1 of each per leg for nonzero cases; zero is exempt from locomotion cycle/speed/turn gates',
         'clearance':'min z over ALL vertices of all five tarsal collision meshes at each 1ms recorded transform; peak of those minima per complete swing; cycle with no geometry samples fails',
         'slip':'max 3D world displacement from first sampled tarsus5 mesh centroid within each complete stance; no samples fails; per-time thorax transform also retained/reconstructed for AP/lateral/vertical diagnostics',
         'forward_speed':'mean(diff(thorax world position)/dt dot prior-sample thorax forward x-axis) over steady intervals',
         'yaw':'unwrap atan2(thorax_R[1,0],thorax_R[0,0]); straight mean rate=(yaw25000-yaw6000)/1.9; turn net=yaw25000-yaw3000; sign must equal asymmetry',
         'stop':'Euclidean endpoint displacement positions40000-30000 <.25; mean 3D chord speed over all 10000 final-second intervals <.1',
         'finite':'all raw core/geometry arrays finite; additionally every physics tick checks qacc/qfrc_actuator/forces/controller mutable numeric state before retaining valid row; exact failing state separately retained',
         'native_units':{'length':'mm','time':'s','angle':'rad','linear_velocity':'mm/s','angular_velocity':'rad/s','force':'native MuJoCo force/torque units as compiled, no SI/muscle conversion claimed','phase':'rad'},
         'limits':'no native joint-angle limits; position force range[-65,65], adhesion native gain40; clamps reported, never used to waive gates'},
      'gates':json.loads(APPROVAL.read_text())['commissioning']['gates'],
      'restoration':{'seed':42,'cases':['zero','straight-008'],'checkpoint_tick':1000,'continuation_ticks':100,
         'physical_seconds':0,'criteria':'100 exact continuation ticks reused from the common silent prefix of candidate seed42 zero/straight-008; no extra physics; active controller restoration separately contract-tested'},
      'geometry_contract':'compiled names/order/transmission axes; actual qpos perturbations and world Jacobian agreement in tests before physics; unchanged model byte hash each run',
      'decisions':'complete both fixed development profiles unless unsafe(nonfinite, qvel>1e6) or cap; any candidate gate false forbids untouched evaluation/neural; baseline never waives failure; same-source evaluation then exact repeat; conditional neural sequence is unchanged approved-plan.json',
      'resource_caps':{'mechanical_seconds':260,'neural_seconds':259,'wall_seconds':28800,'rss_bytes':16*1024**3,'evidence_bytes':8*1024**3,'workers':1},
      'safety_stop':'nonfinite or abs(qvel)>1e6 stops run and remaining physics; behavioral gate failures alone do not stop safe development',
    }
    write_json(root/'registration.json',registration)
    return registration


def validate_freeze(root):
    reg=json.loads((root/'registration.json').read_text())
    if file_sha(root/'sources.json')!=reg['sources_sha256']:
        raise ValueError('source manifest changed')
    for name,entry in json.loads((root/'sources.json').read_text()).items():
        if file_sha(Path(name))!=entry['sha256'] or file_sha(root/entry['archive'])!=entry['sha256']:
            raise ValueError(f'stage source changed: {name}')
    if file_sha(root/'model.mjb')!=reg['model_sha256']:
        raise ValueError('model changed')
    return reg


class Observer:
    def __init__(self,b):
        self.b=b; self.d=mj.MjData(b.model); self.foot=foot_ids(b.model)
        self.foot_leg={int(g):i//5 for i,g in enumerate(self.foot)}
        self.ground=mj.mj_name2id(b.model,mj.mjtObj.mjOBJ_GEOM,'ground_plane')

    def row(self,u):
        b=self.b; d=self.d; c=b.controllers[0]
        d.qpos[:]=b.data.qpos; d.qvel[:]=b.data.qvel; d.ctrl[:]=b.data.ctrl
        d.time=b.data.time
        mj.mj_forward(b.model,d)
        contacts=np.zeros(6)
        for contact in d.contact:
            g1,g2=int(contact.geom1),int(contact.geom2)
            foot=g2 if g1==self.ground else g1 if g2==self.ground else -1
            if foot in self.foot_leg and contact.dist<=0:
                contacts[self.foot_leg[foot]]=1
        core=np.concatenate([b.data.qpos,b.data.qvel,d.xpos[b.body_ids[0]],d.xmat[b.body_ids[0]],
          u,b.data.ctrl,b.data.actuator_force,c.cpg_network.curr_phases,c.cpg_network.curr_magnitudes,
          c.retraction_correction,c.stumbling_correction,c.retraction_persistence_counter,
          c.last_info.get('net_corrections',np.zeros(6)),contacts])
        geometry=np.concatenate([d.geom_xpos[self.foot].ravel(),d.geom_xmat[self.foot].ravel()])
        return core,geometry


def integration(b):
    sig=mj.mjtState.mjSTATE_INTEGRATION
    a=np.empty(mj.mj_stateSize(b.model,sig));mj.mj_getState(b.model,b.data,a,sig);return a


def step(b,u):
    obs=HybridControllerObservation.from_sim(b.sim,'fly-0')
    act=b.controllers[0].step(u,obs)
    apply_locomotion_action(b.sim,'fly-0',act)
    b.drives[0]=u
    b.sim.step();b.tick+=1


def state_finite(b):
    c=b.controllers[0]
    arrays=[b.data.qpos,b.data.qvel,b.data.qacc,b.data.qfrc_actuator,b.data.actuator_force,
            b.data.ctrl,c.cpg_network.curr_phases,c.cpg_network.curr_magnitudes,
            c.retraction_correction,c.stumbling_correction,c.retraction_persistence_counter]
    if not all(np.isfinite(a).all() for a in arrays) or np.max(np.abs(b.data.qvel))>1e6:
        raise FloatingPointError('unsafe/nonfinite physical or controller state')


class Budget:
    def __init__(self,root):
        self.root=root;self.start=time.monotonic();self.steps=0;self.peak=0;self.size=0
    def check(self):
        self.peak=max(self.peak,resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        # macOS reports bytes; Linux reports KiB.
        rss=self.peak if sys.platform=='darwin' else self.peak*1024
        if self.steps>2600000 or time.monotonic()-self.start>28800 or rss>16*1024**3:
            raise RuntimeError('registered resource cap exceeded')
        self.size=sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file())
        if self.size>8*1024**3:
            raise RuntimeError('registered evidence cap exceeded')
    def report(self):
        usage=resource.getrusage(resource.RUSAGE_SELF)
        return {'mechanical_seconds':self.steps*DT,'full_network_seconds':0,
          'wall_seconds':time.monotonic()-self.start,'user_cpu_seconds':usage.ru_utime,
          'system_cpu_seconds':usage.ru_stime,'peak_rss_bytes':usage.ru_maxrss if sys.platform=='darwin' else usage.ru_maxrss*1024,
          'evidence_bytes':sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file()),'workers':1}


def failure_record(error):
    return None if error is None else {'type':type(error).__name__, 'message':str(error),
        'traceback':''.join(traceback.format_exception(error))}


def retention_attempt(stage, operation, failures):
    """One failed retention operation must not skip independent finalizations."""
    try:
        return operation()
    except BaseException as exc:
        failures.append({'stage':stage, **failure_record(exc)})
        return None


def raise_failure(error, failures):
    if error is None and not failures:
        return
    primary = getattr(error,'primary_failure',failure_record(error))
    if error is None:
        error = RuntimeError('evidence finalization failed')
    error.primary_failure = primary
    error.retention_failures = failures
    if failures:
        error.add_note('Secondary retention failures: '+json.dumps(failures))
    raise error


def finish_stream(stream, writer, error, failures, **options):
    terminal=writer.finish(error,**options)
    if terminal is None or terminal.get('complete') is not True or terminal.get('retention_failures'):
        failures.append({'stage':stream+'-terminal','terminal':terminal})
    return terminal


def run_trial(root,stage,profile,seed,case,budget,restoration):
    name,c,a=case; dest=root/stage/f'{profile}--{seed}--{name}'
    b=new_body(seed,profile); observer=Observer(b)
    # Native model is immutable across every trial; compare compiled numeric arrays,
    # as MJB serialization includes no run-specific controller seed.
    reg=json.loads((root/'registration.json').read_text())
    for key,entry in reg['compiled_arrays'].items():
        if not np.array_equal(getattr(b.model,key),np.load(root/f'model-{key}.npy',allow_pickle=False)):
            raise ValueError(f'compiled array changed: {key}')
    meta={'stage':stage,'profile':profile,'seed':seed,'case':case,
          'registration_sha256':file_sha(root/'registration.json'),'sources_sha256':reg['sources_sha256']}
    dest.mkdir(parents=True,exist_ok=False)
    core=geo=None
    error=None; failing=None; failures=[]
    try:
        core=NumericEvidence(dest/'core',sum(n for _,n in CORE),metadata=meta)
        geo=NumericEvidence(dest/'geometry',360,metadata=meta)
        row,g=observer.row(np.zeros(2));core.append(0,row);geo.append(0,g)
        for k in range(40000):
            u=np.array([c*(1-a),c*(1+a)]) if 3000<=k<25000 else np.zeros(2)
            budget.steps+=1
            step(b,u)
            state_finite(b)
            row,g=observer.row(u);core.append(k+1,row)
            if (k+1)%10==0:geo.append(k+1,g)
            if stage=='development' and profile==PROFILE and seed==42 and name in ('zero','straight-008'):
                if k+1==1000:
                    if name=='zero':
                        saved=mj.MjData(b.model);mj.mj_copyData(saved,b.model,b.data)
                        restoration.update(data=saved,controller=b.controllers[0].checkpoint(),
                            tick=b.tick,drives=b.drives.copy(),a=[],b=[])
                    else:
                        # Deliberately damage destination state before exact restoration.
                        b.data.qpos[0]+=1
                        b.controllers[0].cpg_network.curr_phases[:]+=1
                        mj.mj_copyData(b.data,b.model,restoration['data'])
                        b.controllers[0].restore(restoration['controller'])
                        b.tick=restoration['tick'];b.drives[:]=restoration['drives']
                if 1001<=k+1<=1100:
                    branch='a' if name=='zero' else 'b'
                    restoration[branch].append((row.copy(),g.copy(),integration(b)))
                    if name=='straight-008' and k+1==1100:
                        save_restoration(root,restoration)
            if (k+1)%1000==0:budget.check()
    except BaseException as exc:
        error=exc
        failing=retention_attempt('failing-state',lambda:np.concatenate([
                                np.array([b.tick]),b.data.qpos,b.data.qvel,b.data.qacc,b.data.ctrl,
                                b.data.actuator_force,b.controllers[0].cpg_network.curr_phases,
                                b.controllers[0].cpg_network.curr_magnitudes]),failures)
    extra={'physics_tick':b.tick,
           'resources':retention_attempt('trial-resources',budget.report,failures)}
    terminals={}
    for stream,writer in [('core',core),('geometry',geo)]:
        if writer is None:
            continue
        options={'failing_values':failing,'snapshot':lambda:integration(b)} if stream=='core' else {}
        terminals[stream]=retention_attempt(stream+'-finish',
            lambda:finish_stream(stream,writer,error,failures,extra=extra,**options),failures)
    retention_attempt('trial-terminal',lambda:write_json(dest/'trial-terminal.json',{
        'complete':error is None and not failures,'primary_failure':failure_record(error),
        'retention_failures':failures,'streams':terminals,'extra':extra}),failures)
    raise_failure(error,failures)
    print(json.dumps({'completed':str(dest.relative_to(root)),'wall_seconds':terminals['core']['wall_seconds'],
                      'total_physical_seconds':budget.steps*DT}),flush=True)


def save_restoration(root,restoration):
    dest=root/'restoration';dest.mkdir(exist_ok=False)
    a=restoration['a'];b=restoration['b']
    arrays_a=[np.array([r[i] for r in a]) for i in range(3)]
    arrays_b=[np.array([r[i] for r in b]) for i in range(3)]
    with (dest/'continuations.npz').open('xb') as f:
        np.savez_compressed(f,core_a=arrays_a[0],core_b=arrays_b[0],
            geometry_a=arrays_a[1],geometry_b=arrays_b[1],physical_a=arrays_a[2],physical_b=arrays_b[2])
    write_json(dest/'result.json',{'passed':all(np.array_equal(x,y) for x,y in zip(arrays_a,arrays_b)),
        'ticks':[1001,1100],'condition':'shared silent prefix of candidate seed42 zero and straight-008',
        'scope':'real physics full-state restore during silence; active controller continuation covered by contract fixture',
        'registration_sha256':file_sha(root/'registration.json')})


def run(root):
    validate_freeze(root)
    if (root/'execution-start.json').exists():raise ValueError('exclusive experiment already started')
    budget=Budget(root);write_json(root/'execution-start.json',{'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())})
    error=None;decision=None;failures=[];primary=None
    try:
        restoration={}
        for profile in ['historical',PROFILE]:
            for seed in [42,43]:
                for case in CASES:run_trial(root,'development',profile,seed,case,budget,restoration)
        from .verify_v10 import verify_panel
        decision=verify_panel(root,'development')
        write_json(root/'development-decision.json',decision)
        if decision['candidate_passed']:
            validate_freeze(root)
            for profile in ['historical',PROFILE]:
                for seed in [31042,31043]:
                    for case in CASES:run_trial(root,'evaluation',profile,seed,case,budget,restoration)
            run_trial(root,'repeat',PROFILE,31042,CASES[2],budget,restoration)
            decision=verify_panel(root,'evaluation')
            write_json(root/'evaluation-decision.json',decision)
    except BaseException as exc:
        error=exc
        primary=getattr(exc,'primary_failure',failure_record(exc))
        failures.extend(getattr(exc,'retention_failures',[]))
    resources=retention_attempt('execution-resources',budget.report,failures)
    registration_sha=retention_attempt('execution-registration',lambda:file_sha(root/'registration.json'),failures)
    retention_attempt('execution-terminal',lambda:write_json(root/'execution-terminal.json',{
        'outcome':'failed' if error is not None or failures else 'completed',
        'error':failure_record(error),'primary_failure':primary,'retention_failures':failures,
        'decision':decision,'resources':resources,'registration_sha256':registration_sha}),failures)
    raise_failure(error,failures)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('operation',choices=['register','run']);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.operation=='register':freeze(args.output)
    else:run(args.output)

if __name__=='__main__':main()
