"""Read-only recomputation from arrays; does not import candidate/readout/gate code."""
from pathlib import Path
import hashlib,json
import numpy as np
import mujoco as mj
ROOT=Path(__file__).resolve().parents[1]; BASE=ROOT/'var/embodied-v7'
LEGS=('LF','LM','LH','RF','RM','RH')
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def longest(mask):
    n=best=0
    for value in mask:
        n=n+1 if value else 0; best=max(best,n)
    return best

def verify():
    checks={}; rep=BASE/'replay'; con=BASE/'contact'
    registration=json.loads((rep/'registration.json').read_text()); geo=json.loads((rep/'geometry.json').read_text())
    for p,h in registration['source_hashes'].items(): assert sha(p)==h
    for p,h in registration['archive_hashes'].items(): assert sha(p)==h
    for p,h in registration['compiled_hashes'].items(): assert sha(rep/p)==h
    m=mj.MjModel.from_binary_path(str(rep/'compiled.mjb')); d=mj.MjData(m)
    ids=np.array([mj.mj_name2id(m,mj.mjtObj.mjOBJ_JOINT,n) for n in geo['joint_names']]); qa=m.jnt_qposadr[ids]
    aids=np.array([mj.mj_name2id(m,mj.mjtObj.mjOBJ_ACTUATOR,n) for n in geo['actuator_names']]); neutral=np.array(geo['neutral_rad']); signs=np.array(geo['flexion_signs'])
    assert np.array_equal(qa,geo['qpos_addresses']) and np.all(m.actuator_gainprm[aids,0]==45) and np.all(m.actuator_forcerange[aids]==[-65,65])
    assert m.neq==60 and m.nq==66 and m.nv==66 and m.nu==42 and m.opt.timestep==.0001
    # Bind binary to MJCF construction by separately compiling the registered spec.
    xmlmodel=mj.MjModel.from_xml_path(str(rep/'compiled.xml'))
    for key in ('jnt_axis','jnt_pos','qpos0','actuator_gainprm','actuator_forcerange','geom_contype','geom_conaffinity'):
        assert np.array_equal(getattr(m,key),getattr(xmlmodel,key)),key
    checks['xml_roundtrip_limit']={'binary_is_authoritative':True,'thorax_mass_native_difference':float(xmlmodel.body_mass[1]-m.body_mass[1]),'equality_first5_max_difference':float(np.max(np.abs(m.eq_data[:,:5]-xmlmodel.eq_data[:,:5]))),'reason':'MjSpec XML export rounds joint constants, changes unused equality slots and omits 2.052e-6 native fused thorax mass; use frozen compiled.mjb for exact replay'}
    R=(1-np.exp(-.002))*10000/(1-np.exp(-.002)**23)
    old=Path('/tmp/fly-arena-contact-v6/var/contact-v6/assay-001')
    g=np.load(old/'groups.npz'); selected=g['selected']; index={int(v):i for i,v in enumerate(selected)}
    physics_checks=0; interval_errors=[]
    for folder in sorted(rep.iterdir()):
        if not folder.is_dir(): continue
        a=np.load(folder/'body.npz'); assert np.array_equal(a['ticks'],np.arange(6001))
        assert all(np.isfinite(a[k]).all() for k in a.files)
        assert np.array_equal(a['knees'],a['qpos'][:,qa]); assert np.max(np.abs(a['force']))<=65+1e-9
        if not folder.name.startswith('coordinate'):
            name,mode=folder.name.rsplit('-',1); original=np.load(old/name/'samples.npz')
            rates=original['rates_hz']; assert rates.min()>=0 and rates.max()<=R+1e-9
            pools=np.array([[rates[:,[index[int(i)] for i in g[ant+'_'+l]]].mean(axis=1) for ant in ('flexor','extensor')] for l in LEGS]).transpose(2,0,1)
            assert np.allclose(pools,original['motor_pools_hz'],rtol=0,atol=1e-12)
            cmd=.1*(pools[:-1,:,0]-pools[:-1,:,1])/R
            expected=np.repeat(cmd if mode=='intact' else np.zeros_like(cmd),100,axis=0)
            assert np.allclose(a['requested'][1:],expected,rtol=0,atol=1e-14)
        for tick in (0,2000,4000,6000):
            cp=np.load(folder/f'checkpoint-{tick:04}.npz'); assert int(cp['tick'])==tick
            assert cp['integration'].shape==(mj.mj_stateSize(m,mj.mjtState.mjSTATE_INTEGRATION),)
            mj.mj_setState(m,d,cp['integration'],mj.mjtState.mjSTATE_INTEGRATION); mj.mj_forward(m,d)
            assert abs(d.time-tick*.0001)<1e-8 and np.array_equal(d.qpos,a['qpos'][tick])
            if tick==2000:
                d.ctrl[aids]=neutral+signs*a['requested'][tick+1]
                for _ in range(100): mj.mj_step(m,d)
                interval_errors.append(float(np.max(np.abs(d.qpos-a['qpos'][2100]))))
        physics_checks+=1
    assert max(interval_errors)<1e-12
    peak={}; duration={}
    for i,l in enumerate(LEGS):
        diff=np.load(rep/f'{l}-intact/body.npz')['knees'][:,i]-np.load(rep/f'{l}-zero/body.npz')['knees'][:,i]
        peak[l]=float(np.max(np.abs(diff))); duration[l]=longest(np.abs(diff)>.01)*.0001
    rms=float(np.sqrt(np.mean((np.load(rep/'blank-zero/body.npz')['knees'][2000:]-neutral)**2)))
    repeat=float(np.max(np.abs(np.load(rep/'LF-intact/body.npz')['knees']-np.load(rep/'LF-repeat-intact/body.npz')['knees'])))
    gate=duration['LF']>=.05 and (duration['RM']>=.05 or duration['RH']>=.05) and rms<=.001 and repeat<=1e-9
    assert gate==json.loads((rep/'gate.json').read_text())['transduction_pass']
    checks['replay']={'pass':True,'transduction_pass':gate,'peak_rad':peak,'duration_above_001_s':duration,'zero_settled_rms_rad':rms,'repeat_error_rad':repeat,'verified_body_records':physics_checks,'checkpoint_interval_max_error':max(interval_errors)}
    if not (con/'gate.json').exists(): raise ValueError('contact panel incomplete')
    reg=json.loads((con/'registration.json').read_text())
    for p,h in reg['source_hashes'].items(): assert sha(p)==h
    groups=np.load(con/'groups.npz'); obs=groups['selected']; lookup={int(x):i for i,x in enumerate(obs)}
    original_groups=np.load(old/'groups.npz')
    for k in groups.files: assert np.array_equal(groups[k],original_groups[k])
    neural_checks=0; errors=[]; compiled_body_checks=[]
    pid=m.body_mocapid[mj.mj_name2id(m,mj.mjtObj.mjOBJ_BODY,'probe')]
    for folder in sorted(con.iterdir()):
        if not folder.is_dir():continue
        a=np.load(folder/'samples.npz'); condition=json.loads((folder/'condition.json').read_text()); assert a['ticks'].tolist()==list(range(0,10001,100))
        assert all(np.isfinite(a[k]).all() for k in a.files)
        assert a['rates_hz'].min()>=0 and a['rates_hz'].max()<=R+1e-9 and a['max_rate_hz'].max()<=R+1e-9
        pools=np.array([[a['rates_hz'][:,[lookup[int(i)] for i in groups[ant+'_'+l]]].mean(axis=1) for ant in ('flexor','extensor')] for l in LEGS]).transpose(2,0,1)
        assert np.allclose(pools,a['pools_hz'],rtol=0,atol=1e-12)
        cmd=.1*(pools[:,:,0]-pools[:,:,1])/R
        if condition['control']=='motorzero':cmd[:]=0
        assert np.allclose(cmd,a['command_rad'],rtol=0,atol=1e-14)
        for tick in (2000,5000,10000):
            j=tick//100; cp=np.load(folder/f'brain-{tick:04}.npz'); body=np.load(folder/f'body-{tick:04}.npz')
            assert int(cp['tick'])==int(body['tick'])==tick
            assert np.array_equal(cp['rates'][obs],a['rates_hz'][j]) and np.array_equal(cp['current'][obs],a['current_mv'][j])
            assert np.array_equal(cp['external'][obs],a['external_mv'][j]) and np.array_equal(cp['held_command'],a['command_rad'][j])
            assert int(cp['total_spikes'])==int(a['all_spikes'][:j+1].sum())
            assert cp['delay'].shape==(19,len(cp['v'])) and cp['refractory'].dtype==np.int32 and cp['refractory'].min()>=0 and cp['refractory'].max()<=22
            expected=np.zeros_like(cp['external'])
            for k,l in enumerate(LEGS): expected[groups['afferent_'+l]]=0 if condition['control']=='tactilezero' else 48*min(a['contact_ratios'][j,k],1)
            # Graph ORNs are absent from selected observer union: bind directly.
            rawgroups=np.load('/Users/lexa/Desktop/lexa/omega/fly-arena/data/connectome/groups.npz')
            for side in ('left','right'):expected[rawgroups['olfactory_'+side]]=0 if condition['context']=='off' else 48*.55/.85
            assert np.allclose(cp['external'],expected,rtol=0,atol=1e-12)
            mj.mj_setState(m,d,body['integration'],mj.mjtState.mjSTATE_INTEGRATION); mj.mj_forward(m,d)
            assert abs(d.time-tick*.0001)<1e-8 and np.array_equal(d.qpos,a['qpos'][j])
            assert np.array_equal(body['command'],a['command_rad'][j-1])
            if tick==2000:
                d.ctrl[aids]=neutral+signs*a['command_rad'][j]
                geometry=reg['probe_geometry'][condition['leg']]
                for t in range(2000,2100):
                    d.mocap_pos[pid]=np.array(geometry['center_mm'])-.05*((t*.0001-.2)/.1)*np.array(geometry['normal']); mj.mj_step(m,d)
                errors.append(float(np.max(np.abs(d.qpos-a['qpos'][21]))))
            neural_checks+=1
        compiled_body_checks.append(folder.name)
    assert max(errors)<1e-12
    # Independently recompute the causal gate (rather than importing its emitter).
    facts={}
    for i,l in enumerate(LEGS):
        for context in ('off','neutral'):
            stem=f'WT-{l}-42-{context}-'
            a=np.load(con/(stem+'intact')/'samples.npz'); z=np.load(con/(stem+'motorzero')/'samples.npz'); c=np.load(con/(stem+'tactilezero')/'samples.npz'); b=np.load(con/f'WT-{l}-43-{context}-intact/samples.npz')
            delta=a['knees'][:,i]-z['knees'][:,i]; residual=c['knees'][:,i]-z['knees'][:,i]
            peak=float(np.max(np.abs(delta[20:]))); rem=float(np.max(np.abs(residual[20:]))); dur=longest(np.abs(delta[20:])>.01)*.01
            aff=np.flatnonzero(a['afferent_spikes'][:,i]>0); mn=np.flatnonzero(a['motor_spikes'][:,i]>0); on=np.flatnonzero((np.abs(delta)>.01)&(np.arange(101)>=20))
            e1=a['knees'][20:,i]-a['knees'][20,i]; e2=b['knees'][20:,i]-b['knees'][20,i]; same=bool(e1[np.argmax(np.abs(e1))]*e2[np.argmax(np.abs(e2))]>0)
            passed=bool(dur>=.05 and peak>0 and rem<=.2*peak and len(aff) and len(mn) and len(on) and aff[0]<=mn[0]<on[0] and same)
            facts[l+'-'+context]={'peak_rad':peak,'duration_s':dur,'tactile_remaining_fraction':rem/peak if peak else None,'pass':passed}
    a=np.load(con/'WT-LF-42-off-intact/samples.npz'); b=np.load(con/'WT-LF-42-off-repeat/samples.npz'); exact=all(np.array_equal(a[k],b[k]) for k in a.files)
    causal=exact and any(facts['LF-'+c]['pass'] and (facts['RM-'+c]['pass'] or facts['RH-'+c]['pass']) for c in ('off','neutral'))
    assert causal==json.loads((con/'gate.json').read_text())['physical_causal_pass']
    # Deterministic replay of archived full-graph intervals; no new condition.
    from flyarena.connectome import Connectome
    from flyarena.compiler import Compiler
    from flyarena.neural import Brain
    original=Path('/Users/lexa/Desktop/lexa/omega/fly-arena')
    graph=Connectome(original/'data',verify=True)
    weights,manifest=Compiler(graph).load_weights(reg['bindings'][0]['artifact_id'],original/'var')
    neural_replay=[]
    for name in ('WT-LF-42-off-intact','WT-RM-42-neutral-intact'):
        folder=con/name; a=np.load(folder/'samples.npz'); start=dict(np.load(folder/'brain-2000.npz')); finish=dict(np.load(folder/'brain-5000.npz'))
        brain=Brain(graph,weights); brain.restore({k:v for k,v in start.items() if k!='held_command'})
        for j in range(21,51):
            brain.external.fill(0)
            for i,l in enumerate(LEGS):brain.external[groups['afferent_'+l]]=48*min(a['contact_ratios'][j,i],1)
            if 'neutral' in name:
                for side in ('left','right'):brain.external[graph.groups['olfactory_'+side]]=48*(.55/(.55+.3))
            counts=brain.advance(100)
            assert np.array_equal(counts[obs],a['spike_counts'][j])
            assert np.array_equal(brain.rates[obs],a['rates_hz'][j])
            assert int(counts.sum())==int(a['all_spikes'][j])
        for k,v in brain.checkpoint().items():assert np.array_equal(v,finish[k]),(name,k)
        neural_replay.append({'condition':name,'ticks':[2000,5000],'all_neural_state_bitwise':True})
    checks['neural_interval_replay']=neural_replay
    checks['contact']={'integrity_pass':True,'physical_causal_pass':causal,'facts':facts,'exact_repeat':exact,'full_neural_checkpoints':neural_checks,'physical_records':len(compiled_body_checks),'checkpoint_interval_max_error':max(errors)}
    return checks
if __name__=='__main__':
    checks=verify()
    (BASE/'verification.json').write_text(json.dumps(checks,indent=2)+'\n')
    print(json.dumps(checks))
