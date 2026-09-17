"""Source-only call ledger generator; imports no scientific package."""
import ast,hashlib,json,pathlib,sys
sys.dont_write_bytecode=True
ROOT=pathlib.Path(__file__).resolve().parents[2]
BUDGET=ROOT/'src/flyarena/experiments/contact_mechanics_v1/budget.py'
tree=ast.parse(BUDGET.read_text());nodes=[]
for node in tree.body:
    if isinstance(node,ast.Assign):nodes.append(node)
    elif isinstance(node,ast.Expr) and isinstance(node.value,ast.Call) and ast.unparse(node.value.func)=='LEAF_CAPS.update':nodes.append(node)
scope={};exec(compile(ast.Module(body=nodes,type_ignores=[]),str(BUDGET),'exec'),scope)
site=pathlib.Path('/Users/lexa/Desktop/lexa/omega/fly-arena/.venv/lib/python3.12/site-packages')
external=[site/'flygym'/p for p in ('compose/base.py','compose/fly/base_fly.py','compose/fly/neuromechfly.py','compose/world/base_world.py','compose/world/flat_ground.py','simulation.py','utils/mjcf.py')]
external += [site/'flygym_demo/complex_terrain'/p for p in ('common.py','preprogrammed.py','cpg_controller.py','hybrid_controller.py','turning_controller.py')]
local=[ROOT/'src/flyarena/body.py']+[ROOT/'src/flyarena/experiments'/p for p in ('mechanical_v16.py','cadence_v16.py','verify_v16.py','mechanical_v10.py','contact_v1/native.py','contact_v1/law.py')]+list(BUDGET.parent.glob('*.py'))
records={}
for p in sorted(set(external+local)):
    data=p.read_bytes();calls=[]
    for node in ast.walk(ast.parse(data)):
        if isinstance(node,ast.Call):
            name=ast.unparse(node.func)
            if any(word in name for word in ('mj.','_mj()','compile','MjData','MjSpec','get_joint_angles','CPGNetwork','copyData','checkpoint','restore','regularized_velocity','shared_twist','from_sim','get_bodysegment_contact_forces')):
                calls.append({'line':node.lineno,'callee':name})
    records[str(p)]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'source_call_sites':sorted(calls,key=lambda x:x['line'])}
formula={
 'mj_step':'N = 32*40000 + 16*40000 + 40000 + 100',
 'mj_forward':'53 constructor-only Bodies forwards; forbidden in runtime loops',
 'mj_resetDataKeyframe':'53 Simulation constructor resets',
 'mj_saveModel':'1 at seed42 preflight',
 'mj_kinematics':'4 Ac + 4 L + R + Av + 16; conservative shared runtime/reconstruction bound, static14 plus restoration setup2',
 'mj_comPos':'same as mj_kinematics',
 'mj_fwdVelocity':'R endpoint traversal + 2 static + 2 restoration setup',
 'mj_jac':'2*(36+2*512)*Ac + 12*Av + 2*E + 72; producer+independent candidate, both control sensor/verifier, per-contact material velocities, static reserve',
 'mj_jacBody':'2*Ac + 1 static',
 'mj_jacBodyCom':'2*B*Ac + B static',
 'mj_objectVelocity':'2*E + 36 static foot + B static COM + 1 static thorax',
 'mj_contactForce':'E + 512*(CONTROL_ENDPOINTS + Av): recorded owned completed contacts once;16*(40000+1) row0/endpoint control observations;Av active pre-action observations. from_sim selects ground contacts through get_bodysegment_contact_forces. Constructors and failure exports do not call from_sim; native control step path does not use Bodies.step or old NativeRecorder.row.',
 'control_observation':'CONTROL_ENDPOINTS + Av =16*40001+308000; each from_sim invocation charged before its reader, <=512 ground contacts checked before leaf calls',
 'MjData':'4*Ac + 4*L +512 constructor/static/checkpoint/verifier allowance',
 'model_build':'4 static preflight +49 scheduled trial factories; never a restoration factory',
 'model_load':'one reusable binary verification model',
 'bind_native':'4 preflight + 33 candidate trials',
 'checkpoint':'initial seed42 + development candidate42 straight02 poststep10000',
 'restore':'initial same-state + conditional cross-seed destination',
 'MjSpec.compile':'4*53: fly.add_joints keyframe + fly.add_actuators keyframe + world.add_fly keyframe + Simulation.__init__',
 'MjSpec.copy':'one per source compile boundary, charged before boundary invocation',
 'MjSpec.construct':'2*53: BaseWorld and BaseFly',
 'cpg_init_reset':'8*53 upper bound including __init__ nested reset and two controller constructions/resets',
 'cpg_step':'Av; observed CPGNetwork.step, never during preflight',
 'reference_construct':'2*53 factory controllers +1 shared verifier +16 unchanged v16 full-trial verifier constructors',
 'get_joint_angles':'24 Ac + 4 L + 24 Av + 48*53 +24; conservative scalar/batch API invocation bound including two candidate references, independent references, excursion, initialization and unchanged v16 verification',
 'candidate_solve':'6 Ac production regularized_velocity boundary',
 'candidate_shared_fit':'Ac production shared_twist boundary',
 'candidate_active':'Ac runtime attempted active steps',
 'candidate_propose':'Ac runtime prepare/propose reservation',
 'control_active':'Av runtime active actions',
 'independent_candidate':'Ac complete independent transitions including100 restore actions',
 'mj_copyData':'32 fixed cap:2 checkpoints +2 restores staging/backup/commit/possible rollback <=10; unused allowance does not permit extra scientific calls',
 'mj_getState':'512 fixed cap for reset snapshots, checkpoints, restore stages,200 samples and bounded failure exports',
 'mj_stateSize':'512 same call sites as mj_getState',
 'native_cache_manifest':'512 fixed cap, initial/captured cache checks,2 restores,200 samples and bounded failure exports',
 'mj_name2id':'250000 hard bound; bounded constructors/name maps <=53*(model lookup capacity)+37 adapter maps',
 'mj_id2name':'250000 hard bound; frozen69 bodies/70 geoms, constructor and adapter maps',
 'static_prepare':'2 actual-reset detached preparations only at seed42',
 'static_excursion':'6 accepted native calls =12 detached poses only at seed42',
 'static_neutral':'one6-leg angle conversion at each of4 seeds',
}
for name,count in scope['SPEC_PER_BUILD'].items():formula[name]=f'53*{count}; source frozen one-fly flat-ground composition; method wrapper charges actual invocation before call'
missing=set(scope['LEAF_CAPS'])-set(formula)
if missing:raise ValueError('missing ledger derivations: '+str(missing))
value={'schema':'contact-mechanics-source-leaf-ledger/v1','scientific_calls_to_generate':0,
 'constants':{k:scope[k] for k in ('AC','AV','N','R','L','B','E','CONTROL_ENDPOINTS','CONTROL_OBSERVATIONS')},
 'data_allocation_provenance':{'header':str(site/'mujoco/include/mujoco/mjxmacro.h'),'header_sha256':hashlib.sha256((site/'mujoco/include/mujoco/mjxmacro.h').read_bytes()).hexdigest(),'MJDATA_POINTERS_arrays':92,'element_multipliers':scope['DATA_ELEMENT_MULTIPLIERS'],'reservation':'2*(8*sum(model_dimension*multiplier)+92*64+1MiB+model.narena), before MjData constructor; all types <=8bytes; no native plugins'},
 'body_bound_provenance':'compact accepted model locator body_mass shape69, one world body; actual fly body count B must be positive<=68 and sealed at preflight; nbody69 checked',
 'composition_bound_provenance':'compact original metadata mesh_count69, geom_count70, nq73/nv72 and67 joints; fixed source one fly/one plane; no cameras/colorization/obstacles',
 'leaves':{k:{'maximum_attempts':v,'derivation':formula[k]} for k,v in scope['LEAF_CAPS'].items()},
 'instrumentation':{'mj_and_mju':'all module functions wrapped; any absent allowlist name stops before invocation','composition_methods':'named MjSpec/MjsBody methods wrapped directly','spec_copy_compile_construct':'exact immutable Python boundaries reserve before native constructor/copy/compile; failed boundary remains attempted and incomplete','model_binary_load':'only explicit budget.call model_load site','control_observation':'classmethod descriptor preserved; each source reader reserved and owned ground contacts capped before native call', 'field_reads_writes':'frozen source array/property accesses; not additional native dynamics operations'},
 'unknown_costs':['active proposals/solves until first prescribed100 active ticks','native compilation until static preflight','chunk byte rate until actual retained data','class monkeypatch compatibility until finite preflight'],
 'no_extra_allowance':'Hard maxima do not authorize additional calls/trials or retries; scheduled count remains1960100, emergency2600000 never used as allowance.',
 'source_files':records,'ready':False}
out=ROOT/'docs/contact-mechanics-v1/leaf-call-table.json';out.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n');print(json.dumps({'path':str(out),'leaves':len(value['leaves']),'source_files':len(records),'sha256':hashlib.sha256(out.read_bytes()).hexdigest()}))
