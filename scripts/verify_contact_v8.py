"""Raw-array independent verifier; no candidate encoder, loader, runner or gate imports.

Physical and neural interval replays check deterministic integrity. Neural replay
uses the unchanged integrator and does NOT independently validate LIF physics.
"""
from pathlib import Path
import hashlib,json,sys
import numpy as np
import mujoco as mj
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'var/contact-v8';LEGS=('LF','LM','LH','RF','RM','RH')
R=444.41470981063657

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8388608),b''):h.update(b)
    return h.hexdigest()

def longest_intervals(a,b=None,threshold=.01):
    mask=np.abs(a)>threshold
    if b is not None:mask &= (np.abs(b)>threshold)&(a*b>0)
    mask=mask[:-1]&mask[1:]&(a[:-1]*a[1:]>0)
    if b is not None:mask &= b[:-1]*b[1:]>0
    best=run=0
    for x in mask:run=run+1 if x else 0;best=max(best,run)
    return best*.01

def first(mask):
    a=np.flatnonzero(mask);return int(a[0]) if len(a) else None

def compare(a,b,i):
    d=a['knees'][:,i]-b['knees'][:,i]
    n=(a['pools_hz'][:,i,0]-a['pools_hz'][:,i,1])-(b['pools_hz'][:,i,0]-b['pools_hz'][:,i,1])
    return d,n,{'Y_rad':float(np.trapezoid(d,dx=.01)),'N_hz':float(np.trapezoid(n,dx=.01)),
        'peak_rad':float(np.max(np.abs(d))),'rms_rad':float(np.sqrt(np.mean(d*d))),'duration_above_01_s':longest_intervals(d)}

def verify():
    reg=json.loads((BASE/'registration.json').read_text());expected=json.loads((BASE/'registration.sha256.json').read_text())['sha256']
    assert sha(BASE/'registration.json')==expected
    hashcount=0
    for section in ['source_hashes','source_archive_hashes','input_hashes','dependency_hashes','external_hashes']:
        for p,h in reg[section].items():assert sha(p)==h,(section,p);hashcount+=1
    pre=json.loads((BASE/'preflight.json').read_text());assert sha(BASE/'preflight.json')==reg['preflight_sha256']
    g=dict(np.load(BASE/'inputs/groups.npz'));selected=g.pop('selected');lookup={int(v):i for i,v in enumerate(selected)}
    idx={k:np.array([lookup[int(v)] for v in group]) for k,group in g.items()}
    geo=json.loads((BASE/'inputs/geometry.json').read_text());m=mj.MjModel.from_binary_path(str(BASE/'inputs/compiled.mjb'));d=mj.MjData(m)
    jids=np.array([mj.mj_name2id(m,mj.mjtObj.mjOBJ_JOINT,n) for n in geo['joint_names']]);qa=m.jnt_qposadr[jids]
    aids=np.array([mj.mj_name2id(m,mj.mjtObj.mjOBJ_ACTUATOR,n) for n in geo['actuator_names']]);neutral=np.array(geo['neutral_rad']);signs=np.array(geo['flexion_signs'])
    probe=mj.mj_name2id(m,mj.mjtObj.mjOBJ_GEOM,'probe_sphere');pid=m.body_mocapid[mj.mj_name2id(m,mj.mjtObj.mjOBJ_BODY,'probe')]
    geomids=[mj.mj_name2id(m,mj.mjtObj.mjOBJ_GEOM,'fixture/'+l.lower()+'_'+s) for l in LEGS for s in ['tibia','tarsus1','tarsus2']];segment={v:i for i,v in enumerate(geomids)}
    flyids=[i for i in range(m.nbody) if (mj.mj_id2name(m,mj.mjtObj.mjOBJ_BODY,i) or '').startswith('fixture/')]
    weight=float(m.body_mass[flyids].sum()*np.linalg.norm(m.opt.gravity));assert weight==geo['body_weight_native']
    assert (m.nq,m.nv,m.nu,m.neq)==(66,66,42,60) and m.opt.timestep==.0001
    assert np.all(m.actuator_gainprm[aids,0]==45) and np.all(m.actuator_forcerange[aids]==[-65,65])
    rawgroups=dict(np.load('/Users/lexa/Desktop/lexa/omega/fly-arena/data/connectome/groups.npz'))
    records={};physical=[];checkpoint_count=0;paircount=0
    for c in reg['conditions']:
        folder=BASE/'trials'/c['id']
        assert json.loads((folder/'condition.json').read_text())==c
        assert json.loads((folder/'status.json').read_text())['complete']
        a=dict(np.load(folder/'samples.npz'));u=dict(np.load(folder/'inputs.npz'));contact=np.load(folder/'contacts.npz');rows=contact['pairs'];offsets=contact['offsets']
        for arrays in [a,u,dict(contact)]:assert all(np.isfinite(v).all() for v in arrays.values())
        assert np.array_equal(a['ticks'],np.arange(0,10001,100))
        assert np.array_equal(u['input_start_tick'],np.arange(0,10000,100))
        assert np.array_equal(u['output_end_tick'],u['input_start_tick']+100)
        assert np.array_equal(u['force_read_tick'],u['input_start_tick'])
        assert np.array_equal(u['force_evaluation_tick'],np.maximum(0,u['input_start_tick']-1))
        assert len(offsets)==10002 and offsets[0]==0 and offsets[-1]==len(rows) and np.all(np.diff(offsets)>=0)
        assert np.array_equal(a['knees'],a['qpos'][:,qa]) and np.max(np.abs(a['force']))<=65+1e-9
        assert a['rates_hz'].min()>=0 and a['rates_hz'].max()<=R+1e-9 and a['max_rate_hz'].max()<=R+1e-9
        assert np.all(a['spike_counts']>=0) and np.issubdtype(a['spike_counts'].dtype,np.integer)
        pools=np.array([[a['rates_hz'][:,idx[ant+'_'+l]].mean(axis=1) for ant in ['flexor','extensor']] for l in LEGS]).transpose(2,0,1)
        assert np.array_equal(pools,a['pools_hz'])
        cmd=.1*(pools[:,:,0]-pools[:,:,1])/R
        if c['control']=='motorzero':cmd[:]=0
        assert np.array_equal(cmd,a['next_command_rad'])
        assert np.array_equal(a['applied_command_rad'][1:],cmd[:-1]) and np.all(a['applied_command_rad'][0]==0)
        for i,l in enumerate(LEGS):
            assert np.array_equal(a['afferent_spikes'][:,i],a['spike_counts'][:,idx['afferent_'+l]].sum(axis=1))
            assert np.array_equal(a['motor_spikes'][:,i],a['spike_counts'][:,np.r_[idx['flexor_'+l],idx['extensor_'+l]]].sum(axis=1))
        for j,tick in enumerate(u['input_start_tick']):
            net=np.zeros((18,3));loaded=np.zeros(6,dtype=bool)
            for row in rows[offsets[tick]:offsets[tick+1]]:
                ci,g1,g2,exclude,efc=map(int,row[:5]);w=row[6:12];frame=row[12:].reshape(3,3)
                if exclude:continue
                force=frame.T@w[:3]
                if g1 in segment:net[segment[g1]]-=force
                if g2 in segment:net[segment[g2]]+=force
                other=g2 if g1==probe else g1 if g2==probe else -1
                if other in segment and efc>=0 and w[0]>0:loaded[segment[other]//3]=True
            ratios=np.linalg.norm(net.reshape(6,3,3),axis=2).sum(axis=1)/weight
            assert np.array_equal(net.reshape(6,3,3),u['segment_forces'][j])
            assert np.array_equal(ratios,u['contact_ratios'][j]) and np.array_equal(loaded,u['loaded_legs'][j])
            assert not np.any((ratios>0)&~loaded)
            current=np.where((ratios>0)&(c['control']!='tactilezero'),48.,0.)
            assert np.array_equal(current,u['tactile_mv'][j])
            for i,l in enumerate(LEGS):assert np.all(a['external_mv'][j+1,idx['afferent_'+l]]==current[i])
        odor=0. if c['context']=='off' else 48*(.55/(.55+.3))
        assert np.all(u['odor_mv']==odor)
        if c['control']=='noprobe':
            assert np.all(u['contact_ratios']==0) and np.all(u['tactile_mv']==0)
            assert np.array_equal(a['probe_mm'],np.tile([0,0,10],(101,1)))
            active=(rows[:,3]==0)&(rows[:,4]>=0)&(rows[:,6]>0)
            assert not np.any(active & ((rows[:,1]==probe)|(rows[:,2]==probe)))
        # Fixed input and numerical initial conditions match every subject/control.
        initial=np.load(folder/'body-00000.npz');rest=np.load(BASE/'inputs/body-rest.npz')
        mj.mj_setState(m,d,rest['integration'],mj.mjtState.mjSTATE_INTEGRATION);mj.mj_forward(m,d)
        d.qpos[qa[LEGS.index(c['leg'])]]+=.005 if c['state']==42 else -.005
        d.mocap_pos[pid]=[0,0,10] if c['control']=='noprobe' else reg['probe_geometry'][c['leg']]['center_mm'];mj.mj_forward(m,d)
        initial_state=np.empty_like(initial['integration']);mj.mj_getState(m,d,initial_state,mj.mjtState.mjSTATE_INTEGRATION)
        assert np.array_equal(initial_state,initial['integration'])
        for tick in (0,2000,5000,10000):
            j=tick//100;cp=dict(np.load(folder/f'brain-{tick:05}.npz'));bp=np.load(folder/f'body-{tick:05}.npz')
            assert all(np.isfinite(v).all() for v in cp.values())
            assert int(cp['tick'])==int(bp['tick'])==tick
            assert np.array_equal(cp['rates'][selected],a['rates_hz'][j]) and np.array_equal(cp['current'][selected],a['current_mv'][j])
            assert np.array_equal(cp['external'][selected],a['external_mv'][j]) and np.array_equal(cp['held_command'],cmd[j])
            assert int(cp['total_spikes'])==int(a['all_spikes'][:j+1].sum())
            assert cp['delay'].shape==(19,len(cp['v'])) and cp['refractory'].dtype==np.int32 and cp['refractory'].min()>=0 and cp['refractory'].max()<=22
            assert cp['rates'].min()>=0 and cp['rates'].max()<=R+1e-9
            external=np.zeros_like(cp['external'])
            if tick:
                for i,l in enumerate(LEGS):external[g['afferent_'+l]]=u['tactile_mv'][j-1,i]
                for side in ['left','right']:external[rawgroups['olfactory_'+side]]=odor
            assert np.array_equal(cp['external'],external)
            mj.mj_setState(m,d,bp['integration'],mj.mjtState.mjSTATE_INTEGRATION);mj.mj_forward(m,d)
            assert abs(d.time-tick*.0001)<1e-8 and np.array_equal(d.qpos,a['qpos'][j])
            assert np.array_equal(bp['command'],a['applied_command_rad'][j])
            checkpoint_count+=1
        # Every record's exact physical .20-.21 interval, with the recorded delayed command.
        bp=np.load(folder/'body-02000.npz');mj.mj_setState(m,d,bp['integration'],mj.mjtState.mjSTATE_INTEGRATION);mj.mj_forward(m,d)
        d.ctrl[aids]=neutral+signs*cmd[20];pg=reg['probe_geometry'][c['leg']]
        for tick in range(2000,2100):
            inward=.05*(tick*.0001-.2)/.1
            d.mocap_pos[pid]=[0,0,10] if c['control']=='noprobe' else np.array(pg['center_mm'])-inward*np.array(pg['normal'])
            mj.mj_step(m,d)
        error=float(np.max(np.abs(d.qpos-a['qpos'][21])));assert error<1e-12
        physical.append({'id':c['id'],'qpos_max_error':error,'ticks':[2000,2100]})
        paircount+=len(rows);records[c['id']]=(a,u)
    assert len(records)==99
    repeats={}
    for subject in reg['subjects']:
        role=subject['role'];name=f'{role}-LF-42-neutral-intact';a,u=records[name];b,v=records[name+'-repeat']
        assert all(np.array_equal(a[k],b[k]) for k in a) and all(np.array_equal(u[k],v[k]) for k in u)
        for file in ['contacts.npz']+[f'{kind}-{tick:05}.npz' for kind in ['brain','body'] for tick in [0,2000,5000,10000]]:
            x=np.load(BASE/'trials'/name/file);y=np.load(BASE/'trials'/(name+'-repeat')/file)
            assert x.files==y.files and all(np.array_equal(x[k],y[k]) for k in x.files),(name,file)
        _,_,errors=compare(b,a,0)
        repeats[role]={'all_arrays_and_full_checkpoints_exact':True,'knee_max_error_rad':float(np.max(np.abs(a['knees']-b['knees']))),'Y_error_rad':abs(errors['Y_rad']),'N_error_hz':abs(errors['N_hz'])}
    local={}
    for subject in reg['subjects']:
        role=subject['role']
        for context in ['neutral','off'] if role=='wildtype' else ['neutral']:
            for leg in ['LF','RM','RF']:
                i=LEGS.index(leg);states={}
                for state in [42,43]:
                    prefix=f'{role}-{leg}-{state}-{context}-';a,u=records[prefix+'intact'];t,_=records[prefix+'tactilezero'];z,_=records[prefix+'motorzero'];s,_=records[prefix+'noprobe']
                    delta,n,metrics=compare(a,t,i);mech,_,mechanical=compare(a,z,i)
                    _,_,residual=compare(t,z,i);_,_,sham=compare(a,s,i)
                    sensor=first(u['contact_ratios'][:,i]>0)
                    aff=first(a['afferent_spikes'][:,i]!=t['afferent_spikes'][:,i])
                    mn=first(np.any(a['pools_hz'][:,i]!=t['pools_hz'][:,i],axis=1))
                    command=first(a['next_command_rad'][:,i]!=t['next_command_rad'][:,i])
                    application=first(a['applied_command_rad'][:,i]!=t['applied_command_rad'][:,i])
                    body=first(delta!=0)
                    precontact=bool(sensor is not None and all(np.array_equal(a[k][:sensor+1],t[k][:sensor+1]) for k in ['rates_hz','spike_counts','next_command_rad','knees']))
                    aff_increment=int(a['afferent_spikes'][:,i].sum()-t['afferent_spikes'][:,i].sum())
                    ordered=bool(sensor is not None and aff is not None and mn is not None and command is not None and application is not None and body is not None and aff>=sensor+1 and mn>=aff and command>=mn and application==command+1 and body>=application)
                    causal=bool(precontact and ordered and aff_increment>0)
                    overlap=longest_intervals(delta,mech)
                    metrics.update({'mechanical':mechanical,'tactilezero_minus_motorzero':residual,'intact_minus_noprobe':sham,
                        'overlapping_same_direction_s':overlap,'causal_pass':causal,'afferent_spike_increment':aff_increment,
                        'first_sensor_read_s':None if sensor is None else sensor*.01,'first_force_evaluation_s':None if sensor is None else int(u['force_evaluation_tick'][sensor])*.0001,
                        'afferent_difference_endpoint_s':None if aff is None else aff*.01,'MN_difference_endpoint_s':None if mn is None else mn*.01,
                        'next_command_difference_s':None if command is None else command*.01,'command_application_start_s':None if application is None else (application-1)*.01,
                        'body_difference_endpoint_s':None if body is None else body*.01,'precontact_paired_equal':precontact,'ordered_at_10ms':ordered,
                        'local_state_pass':bool(causal and overlap>=.05)})
                    states[str(state)]=metrics
                passed=bool(all(s['local_state_pass'] for s in states.values()) and states['42']['Y_rad']*states['43']['Y_rad']>0)
                local[f'{role}-{leg}-{context}']={'states':states,'local_admission':passed}
    phenotypes={}
    roles=[s['role'] for s in reg['subjects']]
    for ai,ar in enumerate(roles):
        for br in roles[ai+1:]:
            for leg in ['LF','RM','RF']:
                aa=local[f'{ar}-{leg}-neutral'];bb=local[f'{br}-{leg}-neutral']
                dy=[aa['states'][str(s)]['Y_rad']-bb['states'][str(s)]['Y_rad'] for s in [42,43]]
                dn=[aa['states'][str(s)]['N_hz']-bb['states'][str(s)]['N_hz'] for s in [42,43]]
                ye=max(repeats[ar]['Y_error_rad'],repeats[br]['Y_error_rad']);ne=max(repeats[ar]['N_error_hz'],repeats[br]['N_error_hz'])
                body=bool(dy[0]*dy[1]>0 and all(abs(v)>.001 and abs(v)>10*ye for v in dy))
                neural=bool(dn[0]*dn[1]>0 and all(abs(v)>1 and abs(v)>10*ne for v in dn))
                category='joint' if body and neural else 'body-only' if body else 'neural-only' if neural else 'exact-zero' if all(v==0 for v in dy+dn) else 'state-dependent' if dy[0]*dy[1]<0 or dn[0]*dn[1]<0 else 'below-threshold'
                phenotypes[f'{ar}-minus-{br}-{leg}']={'deltaY_rad_states42_43':dy,'deltaN_hz_states42_43':dn,'body_resolved':body,'neural_resolved':neural,'joint_tactile_phenotype':bool(body and neural and (aa['local_admission'] or bb['local_admission'])),'category':category}
    # Raw-source ID binding and reconstructed actual subject weights, then three
    # fixed recorded neural interval replays. No new scientific conditions.
    from flyarena.connectome import Connectome
    from flyarena.compiler import Compiler
    from flyarena.neural import Brain
    import pyarrow.feather as feather
    original=Path('/Users/lexa/Desktop/lexa/omega/fly-arena');graph=Connectome(original/'data',verify=True)
    annotations=feather.read_table(original/'data/raw/body-annotations.feather',columns=['bodyId','status']).to_pylist()
    ids=[int(r['bodyId']) for r in annotations if r['status']=='Traced'];assert len(ids)==graph.n and set(ids)==set(map(int,graph.ids))
    replays=[]
    for subject in reg['subjects']:
        name=subject['role']+'-LF-42-neutral-intact';folder=BASE/'trials'/name;a,u=records[name]
        weights,manifest=Compiler(graph).load_weights(subject['artifact_id'],original/'var')
        assert hashlib.sha256(weights.tobytes()).hexdigest()==subject['weights_sha256']
        brain=Brain(graph,weights);start=dict(np.load(folder/'brain-02000.npz'));finish=dict(np.load(folder/'brain-05000.npz'))
        brain.restore({k:v for k,v in start.items() if k!='held_command'})
        for j in range(20,50):
            brain.external.fill(0)
            for i,l in enumerate(LEGS):brain.external[g['afferent_'+l]]=u['tactile_mv'][j,i]
            for side in ['left','right']:brain.external[graph.groups['olfactory_'+side]]=u['odor_mv'][j,0]
            counts=brain.advance(100)
            assert np.array_equal(counts[selected],a['spike_counts'][j+1]) and np.array_equal(brain.rates[selected],a['rates_hz'][j+1])
            assert int(counts.sum())==int(a['all_spikes'][j+1])
        for k,v in brain.checkpoint().items():assert np.array_equal(v,finish[k]),(name,k)
        replays.append({'subject':subject['role'],'ticks':[2000,5000],'full_state_bitwise':True})
    size=sum(p.stat().st_size for p in BASE.rglob('*') if p.is_file());assert size<1500000000
    return {'integrity_pass':True,'registered_hashes_checked':hashcount,'registration_sha256':expected,'verified_records':99,'scientific_records':96,'exact_repeats':repeats,'full_checkpoints_verified':checkpoint_count,
        'physical_intervals':physical,'physical_interval_max_error':max(x['qpos_max_error'] for x in physical),'neural_intervals':replays,'neural_replay_limit':'same unchanged integrator, deterministic integrity only; not independent LIF validation',
        'raw_contact_pairs_verified':paircount,'all_six_outputs_verified':True,'sham_all_physics_steps_verified':True,'local':local,'phenotypes':phenotypes,'evidence_bytes_at_verification':size,
        'absent':'official/submitted odor OFF; LM/LH/RH direct probes; free-body; production/browser/device/remote qualification'}

if __name__=='__main__':
    try:
        result=verify()
        with (BASE/'verification.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
        print(json.dumps({'integrity_pass':True,'records':result['verified_records'],'physical_max_error':result['physical_interval_max_error'],'local':result['local'],'phenotypes':result['phenotypes']}),flush=True)
    except Exception as exc:
        import traceback
        with (BASE/'verification-failure.json').open('x') as f:json.dump({'type':type(exc).__name__,'reason':str(exc),'traceback':traceback.format_exc()},f,indent=2)
        raise
