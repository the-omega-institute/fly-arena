"""Exclusive frozen registration and bounded 96+3 actual-subject executor.

Writes incomplete records even on integrity failure. Existing trials are never
resumed, replaced or silently re-registered. No scientific null stops this panel.
"""
from pathlib import Path
import sys,json,hashlib,importlib.metadata as metadata,traceback,time
import numpy as np
import mujoco as mj
from flyarena.common import file_sha
from flyarena.connectome import Connectome
from flyarena.compiler import Compiler
from flyarena.neural import Brain
from flyarena.backend import CPUBrainBackend
from flyarena.experiments.contact_v6 import LEGS
from flyarena.experiments.contact_presence_v8 import ContactPresenceBridge,RMAX
from flyarena.experiments.binary_fixture_v8 import BinaryFixture,penetration
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'var/contact-v8';INPUTS=OUT/'inputs'
ORIGINAL=Path('/Users/lexa/Desktop/lexa/omega/fly-arena')
CAP=1500000000

def write_new(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')

def evidence_size():return sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file())

def check_hashes(reg):
    for section in ['source_hashes','input_hashes','dependency_hashes','external_hashes']:
        for p,h in reg[section].items():
            if file_sha(Path(p))!=h:raise ValueError('registered hash mismatch '+p)

def conditions(subjects):
    result=[]
    for s in subjects:
        for context in (['neutral','off'] if s['role']=='wildtype' else ['neutral']):
            for leg in ('LF','RM','RF'):
                for state in (42,43):
                    for control in ('intact','tactilezero','motorzero','noprobe'):
                        result.append({'subject':s['role'],'leg':leg,'state':state,'context':context,'control':control,'repeat':False})
    for s in subjects:result.append({'subject':s['role'],'leg':'LF','state':42,'context':'neutral','control':'intact','repeat':True})
    for c in result:c['id']='-'.join(str(c[k]) for k in ('subject','leg','state','context','control'))+('-repeat' if c['repeat'] else '')
    assert len(result)==99
    return result

def freeze():
    if (OUT/'registration.json').exists():raise ValueError('registration exists; no overwrite or implicit restart')
    pre=json.loads((OUT/'preflight.json').read_text())
    plan=json.loads((INPUTS/'approved-plan.json').read_text())
    sources=list((ROOT/'src/flyarena').rglob('*.py'))+[ROOT/'scripts'/n for n in ['env-v8.sh','preflight_contact_v8.py','run_contact_v8.py','verify_contact_v8.py','report_contact_v8.py']]+[ROOT/'tests/test_contact_v8.py',ROOT/'docs/CONTACT_PRESENCE_V8.md']
    archive=OUT/'source'
    for p in sources:
        dest=archive/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(p.read_bytes())
    deps={}
    # Freeze installed distribution RECORDs plus all installed executable Python/native
    # files for numerical/model dependencies, without changing dependency directories.
    for name in pre['versions']:
        dist=metadata.distribution(name)
        for item in dist.files or []:
            p=Path(dist.locate_file(item))
            if p.is_file() and (p.suffix in ('.py','.so','.dylib') or p.name in ['RECORD','METADATA']):deps[str(p)]=file_sha(p)
    external={}
    old=json.loads((INPUTS/'v7-contact-registration.json').read_text())
    for p in [ORIGINAL/'data/raw/body-annotations.feather',ORIGINAL/'data/connectome/manifest.json']:
        external[str(p)]=file_sha(p)
    manifest=json.loads((ORIGINAL/'data/connectome/manifest.json').read_text())
    for n,h in manifest['files'].items():external[str(ORIGINAL/'data/connectome'/n)]=h
    for s in pre['subjects']:
        for n in ['manifest.json','mutations.npz']:
            p=ORIGINAL/'var/artifacts'/s['artifact_id']/n;external[str(p)]=file_sha(p)
    reg={'schema':'contact-presence48-tethered-v8/registration-1','approved_plan':plan,'subjects':pre['subjects'],
        'conditions':conditions(pre['subjects']),'source_hashes':{str(p):file_sha(p) for p in sources},
        'source_archive_hashes':{str(p):file_sha(p) for p in archive.rglob('*') if p.is_file()},
        'input_hashes':{str(p):file_sha(p) for p in INPUTS.rglob('*') if p.is_file()},'dependency_hashes':deps,'external_hashes':external,
        'preflight_sha256':file_sha(OUT/'preflight.json'),'probe_geometry':old['probe_geometry'],
        'input_start_ticks':list(range(0,10000,100)),'output_end_ticks':list(range(100,10001,100)),
        'full_neural_checkpoint_ticks':[0,2000,5000,10000], 'physical_checkpoint_ticks':[0,2000,5000,10000],
        'force_clock':pre['clock_assumption'],'rmax_hz':RMAX,'cap_bytes':CAP,
        'duration_convention':'whole 10ms intervals with both endpoints strictly above threshold and same sign; overlapping causal/mechanical masks with same direction',
        'causal_convention':'first differential afferent bin end >= first positive sensor read; own MN pool and next command same/later endpoint bin; body difference first endpoint strictly after first nonzero applied-command bin start. Precontact paired selected rates/spikes/commands/knees equal.',
        'mean_convention':'trapezoid on 101 endpoint grid [0,1]; signed own-knee and antagonist-rate differences; all6 traces retained',
        'source_corrections':'any subsequent correction requires separate version and report; original registration and failed records never overwritten',
        'stop':'source/identity/binary mismatch; nonfinite/range/clock; missing/corrupt evidence; sham/contact inconsistency; cap. Scientific null is not stop.',
        'deviations':[]}
    check_hashes(reg)
    write_new(OUT/'registration.json',reg)
    (OUT/'registration.json').chmod(0o444)
    write_new(OUT/'registration.sha256.json',{'sha256':file_sha(OUT/'registration.json')})
    return reg

def contact_rows(f):
    rows=[]
    for ci in range(f.data.ncon):
        c=f.data.contact[ci];w=np.zeros(6);mj.mj_contactForce(f.model,f.data,ci,w)
        rows.append([ci,int(c.geom1),int(c.geom2),int(c.exclude),int(c.efc_address),float(c.dist),*w,*c.frame])
    return np.asarray(rows,dtype=np.float64).reshape(-1,21)

def run(f,b,rest,groups,selected,reg,c):
    folder=OUT/'trials'/c['id'];folder.mkdir(parents=True,exist_ok=False)
    write_new(folder/'condition.json',c)
    f.restore(f.initial);b.restore(rest)
    i=LEGS.index(c['leg']);f.data.qpos[f.qadr[i]]+=.005 if c['state']==42 else -.005
    geo=reg['probe_geometry'][c['leg']];center=np.array(geo['center_mm']);normal=np.array(geo['normal'])
    sham=c['control']=='noprobe'
    f.data.mocap_pos[f.probe_id]=[0,0,10] if sham else center
    mj.mj_forward(f.model,f.data)
    record={k:[] for k in ['ticks','knees','qpos','velocity','force','work_native','probe_mm','rates_hz','spike_counts','current_mv','external_mv','pools_hz','next_command_rad','applied_command_rad','all_spikes','max_rate_hz','afferent_spikes','motor_spikes']}
    inputs={k:[] for k in ['input_start_tick','output_end_tick','force_evaluation_tick','force_read_tick','contact_ratios','segment_forces','loaded_legs','tactile_mv','odor_mv']}
    pairs=[];offsets=[0];counts=np.zeros(b.backend.brain.graph.n,dtype=np.int32);pools=np.zeros((6,2));work=np.zeros(6)
    def append_pairs():
        rows=contact_rows(f);pairs.append(rows);offsets.append(offsets[-1]+len(rows))
        if sham:
            # Check every physics step, including between neural input reads.
            if any(int(r[3])==0 and int(r[4])>=0 and r[6]>0 and f.probe_geom in r[1:3] for r in rows):raise ValueError('loaded sham at physics tick '+str(f.tick))
    def frame():
        brain=b.backend.brain
        values={'ticks':f.tick,'knees':f.data.qpos[f.qadr].copy(),'qpos':f.data.qpos.copy(),'velocity':f.data.qvel[f.vadr].copy(),
            'force':f.data.actuator_force[f.aids].copy(),'work_native':work.copy(),'probe_mm':f.data.mocap_pos[f.probe_id].copy(),
            'rates_hz':brain.rates[selected].copy(),'spike_counts':counts[selected].copy(),'current_mv':brain.current[selected].copy(),
            'external_mv':brain.external[selected].copy(),'pools_hz':pools.copy(),'next_command_rad':b.held_command.copy(),'applied_command_rad':f.command.copy(),
            'all_spikes':int(counts.sum()),'max_rate_hz':float(brain.rates.max()),
            'afferent_spikes':np.array([counts[groups['afferent_'+l]].sum() for l in LEGS]),
            'motor_spikes':np.array([counts[np.r_[groups['flexor_'+l],groups['extensor_'+l]]].sum() for l in LEGS])}
        for k,v in values.items():record[k].append(v)
    def checkpoints():
        np.savez_compressed(folder/f'body-{f.tick:05}.npz',**f.checkpoint())
        np.savez_compressed(folder/f'brain-{f.tick:05}.npz',**b.checkpoint())
    complete=False
    try:
        append_pairs();frame();checkpoints()
        for sample in range(100):
            ratios,forces,loaded,_=f.observe(sham)
            encoded=b.stimulate(ratios,(0,0) if c['context']=='off' else (.55,.55),c['control']=='tactilezero')
            values={'input_start_tick':f.tick,'output_end_tick':f.tick+100,'force_evaluation_tick':max(0,f.tick-1),
                'force_read_tick':f.tick,'contact_ratios':ratios,'segment_forces':forces,'loaded_legs':loaded,
                'tactile_mv':np.where((ratios>0)&(c['control']!='tactilezero'),48.,0.),'odor_mv':48*encoded}
            for k,v in values.items():inputs[k].append(v)
            f.command_knees(b.held_command)
            counts=b.backend.advance(100)
            for _ in range(100):
                f.data.mocap_pos[f.probe_id]=[0,0,10] if sham else center-penetration(f.tick)*normal
                f.step();work+=f.data.actuator_force[f.aids]*f.data.qvel[f.vadr]*.0001;append_pairs()
            pools,_=b.readout(c['control']=='motorzero')
            if b.backend.brain.tick!=f.tick:raise ValueError('neural/physical clock mismatch')
            frame()
            if f.tick in (2000,5000,10000):checkpoints()
        # Last sample verifies any endpoint contacts without another input/neural trial.
        f.observe(sham)
        complete=True
    finally:
        np.savez_compressed(folder/'samples.npz',**{k:np.asarray(v) for k,v in record.items()})
        np.savez_compressed(folder/'inputs.npz',**{k:np.asarray(v) for k,v in inputs.items()})
        np.savez_compressed(folder/'contacts.npz',offsets=np.array(offsets,dtype=np.int64),pairs=np.concatenate(pairs) if pairs else np.empty((0,21)))
        write_new(folder/'status.json',{'complete':complete,'body_tick':f.tick,'neural_tick':b.backend.brain.tick,'registered_condition':c['id']})
    return {'id':c['id'],'seconds':1.,'spikes':b.backend.brain.total_spikes,'files_bytes':sum(p.stat().st_size for p in folder.iterdir())}

def main():
    reg=freeze();print('REGISTRATION '+file_sha(OUT/'registration.json'),flush=True)
    graph=Connectome(ORIGINAL/'data',verify=True);compiler=Compiler(graph);g=dict(np.load(INPUTS/'groups.npz'));selected=g.pop('selected')
    f=BinaryFixture(INPUTS);completed=[];current_subject=None
    try:
        for c in reg['conditions']:
            # Conservative reserve fits next trial plus derived artifacts; never start beyond cap.
            if evidence_size()+20000000>CAP:raise ValueError('evidence cap reserve reached')
            for p,h in reg['source_hashes'].items():
                if file_sha(Path(p))!=h:raise ValueError('source changed before trial '+p)
            if c['subject']!=current_subject:
                subject=next(s for s in reg['subjects'] if s['role']==c['subject'])
                weights,_=compiler.load_weights(subject['artifact_id'],ORIGINAL/'var')
                b=ContactPresenceBridge(CPUBrainBackend(Brain(graph,weights)),g)
                rest=dict(np.load(INPUTS/('rest-'+c['subject']+'.npz')));current_subject=c['subject']
            start=time.monotonic();result=run(f,b,rest,g,selected,reg,c);completed.append(result)
            print(json.dumps(result|{'wall_s':round(time.monotonic()-start,2),'completed':len(completed),'evidence_bytes':evidence_size()}),flush=True)
        check_hashes(reg)
        write_new(OUT/'execution.json',{'complete':True,'count':len(completed),'scientific':96,'repeats':3,'records':completed,'post_hashes_match':True,'evidence_bytes':evidence_size()})
    except Exception as exc:
        write_new(OUT/'integrity-stop.json',{'type':type(exc).__name__,'reason':str(exc),'completed':completed,'active_condition':c if 'c' in locals() else None,'traceback':traceback.format_exc(),'registration_sha256':file_sha(OUT/'registration.json')})
        raise

if __name__=='__main__':main()
