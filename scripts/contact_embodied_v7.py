"""Frozen local physical contact WT panel, conditional exact subject comparison."""
from pathlib import Path
import json, time
import numpy as np
import mujoco as mj
from flyarena.common import write_json, file_sha
from flyarena.connectome import Connectome
from flyarena.compiler import Compiler
from flyarena.neural import Brain
from flyarena.backend import CPUBrainBackend
from flyarena.experiments.embodied_v7 import EmbodiedBridge, RMAX
from flyarena.experiments.contact_v6 import LEGS, bind_annotations, observe_flygym_contact
from flyarena.experiments.fixture_v7 import Fixture
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'var/embodied-v7/contact'
ORIGINAL=Path('/Users/lexa/Desktop/lexa/omega/fly-arena')

def probe_geometry(f):
    result={}; f.restore(f.initial)
    pg=mj.mj_name2id(f.model,mj.mjtObj.mjOBJ_GEOM,'probe_sphere')
    for l in LEGS:
        _,k,d=f.points(l); axis=d-k; axis/=np.linalg.norm(axis)
        outward=np.array([0,1 if l[0]=='L' else -1,0.]); outward-=axis*(outward@axis); outward/=np.linalg.norm(outward)
        origin=k+.8*(d-k)+outward
        gid=mj.mj_name2id(f.model,mj.mjtObj.mjOBJ_GEOM,'fixture/'+l.lower()+'_tibia')
        normal=np.zeros(3); distance=mj.mj_rayMesh(f.model,f.data,gid,origin,-outward,normal)
        if distance<0: raise ValueError('ray missed distal tibia '+l)
        if normal@outward<0: normal=-normal
        normal/=np.linalg.norm(normal); surface=origin-distance*outward
        # The collision surface is the compiled convex hull. Register its tangent
        # along this fixed mesh surface normal, by static signed-distance root only.
        lo,hi=0.,.3
        def dist(offset):
            f.data.mocap_pos[f.probe_id]=surface+offset*normal; mj.mj_forward(f.model,f.data)
            return float(mj.mj_geomDistance(f.model,f.data,gid,pg,1.,None))
        if not dist(lo)<=0<=dist(hi): raise ValueError('tangent bracket')
        for _ in range(48):
            mid=(lo+hi)/2
            if dist(mid)>0: hi=mid
            else: lo=mid
        offset=(lo+hi)/2; center=surface+offset*normal
        tangent_distance=dist(offset)
        if abs(tangent_distance)>1e-8: raise ValueError('tangent registration')
        result[l]={'center_mm':center.tolist(),'normal':normal.tolist(),'mesh_intersection_mm':surface.tolist(),
                   'radius_mm':.1,'convex_surface_offset_mm':offset,'tangent_distance_mm':tangent_distance,'geom_id':gid}
    f.restore(f.initial); return result

def penetration(tick):
    t=tick*.0001
    return 0. if t<.2 or t>=.5 else .05*(t-.2)/.1 if t<.3 else .05 if t<.4 else .05*(.5-t)/.1

def run(f,b,rest,selected,groups,geometry,folder,leg,seed,context,control):
    folder.mkdir(); f.restore(f.initial); b.restore(rest)
    i=LEGS.index(leg); f.data.qpos[f.qadr[i]] += .005 if seed==42 else -.005
    f.data.mocap_pos[f.probe_id]=geometry[leg]['center_mm']; mj.mj_forward(f.model,f.data)
    np.savez_compressed(folder/'body-0000.npz',**f.checkpoint())
    record={k:[] for k in ('ticks','knees','qpos','velocity','force','work_native','probe_mm','contact_ratios','rates_hz','spike_counts','current_mv','external_mv','pools_hz','command_rad','all_spikes','max_rate_hz','afferent_spikes','motor_spikes')}
    cumulative=np.zeros(6); contact_impulse=np.zeros(6); record['contact_impulse_native']=[]
    counts=np.zeros(b.backend.brain.graph.n,dtype=np.int32); pools=np.zeros((6,2)); ratios=np.zeros(6)
    def frame():
        brain=b.backend.brain
        values={'ticks':f.tick,'knees':f.data.qpos[f.qadr].copy(),'qpos':f.data.qpos.copy(),'velocity':f.data.qvel[f.vadr].copy(),
            'force':f.data.actuator_force[f.aids].copy(),'work_native':cumulative.copy(),'probe_mm':f.data.mocap_pos[f.probe_id].copy(),
            'contact_ratios':ratios.copy(),'rates_hz':brain.rates[selected].copy(),'spike_counts':counts[selected].copy(),
            'current_mv':brain.current[selected].copy(),'external_mv':brain.external[selected].copy(),'pools_hz':pools.copy(),
            'command_rad':b.held_command.copy(),'all_spikes':int(counts.sum()),'max_rate_hz':float(brain.rates.max()),
            'afferent_spikes':np.array([counts[groups['afferent_'+l]].sum() for l in LEGS]),
            'motor_spikes':np.array([counts[np.r_[groups['flexor_'+l],groups['extensor_'+l]]].sum() for l in LEGS]),
            'contact_impulse_native':contact_impulse.copy()}
        for k,v in values.items(): record[k].append(v)
    frame()
    for sample in range(100):
        # Causal zero-order hold: local body sample -> neural interval -> next motor
        # command; physics in this interval uses the PREVIOUS held neural command.
        ratios=observe_flygym_contact(f.sim,'fixture')
        b.stimulate(ratios,(0,0) if context=='off' else (.55,.55),control=='tactilezero')
        f.command_knees(b.held_command)
        counts=b.backend.advance(100)
        for _ in range(100):
            f.data.mocap_pos[f.probe_id]=np.array(geometry[leg]['center_mm'])-penetration(f.tick)*np.array(geometry[leg]['normal'])
            f.step(); cumulative+=f.data.actuator_force[f.aids]*f.data.qvel[f.vadr]*.0001
        contact_impulse+=ratios*.01 # F/W seconds; multiplied by registered weight in reports
        pools,_=b.readout(control=='motorzero')
        assert b.backend.brain.tick==f.tick
        frame()
        if f.tick in (2000,5000,10000):
            np.savez_compressed(folder/f'body-{f.tick:04}.npz',**f.checkpoint())
            np.savez_compressed(folder/f'brain-{f.tick:04}.npz',**b.checkpoint())
    np.savez_compressed(folder/'samples.npz',**{k:np.asarray(v) for k,v in record.items()})
    write_json(folder/'condition.json',{'leg':leg,'seed':seed,'context':context,'control':control,'tethered':True,'duration_s':1.,'contact_impulse_units':'weight seconds; 10ms sampled quadrature','work_units':'native torque*radians; actuator work proxy'})

def longest(mask): return max((len(x) for x in ''.join('1' if x else '0' for x in mask).split('0')),default=0)

def evaluate():
    metrics={}
    for l in LEGS:
        i=LEGS.index(l)
        for context in ('off','neutral'):
            stem=f'WT-{l}-42-{context}-'
            a=np.load(OUT/(stem+'intact')/'samples.npz'); p=np.load(OUT/(stem+'motorzero')/'samples.npz'); c=np.load(OUT/(stem+'tactilezero')/'samples.npz')
            effect=a['knees'][:,i]-p['knees'][:,i]; residual=c['knees'][:,i]-p['knees'][:,i]
            window=np.arange(101)>=20
            peak=float(np.max(np.abs(effect[window]))); rem=float(np.max(np.abs(residual[window])))
            duration=longest((np.abs(effect)>.01)&window)*.01
            # Seed43 has no extra passive control in approved panel; sign consistency
            # is defined on own excursion from pre-contact frame t=.2, same for seed42.
            a43=np.load(OUT/f'WT-{l}-43-{context}-intact/samples.npz')
            ex42=a['knees'][20:,i]-a['knees'][20,i]; ex43=a43['knees'][20:,i]-a43['knees'][20,i]
            signed42=float(ex42[np.argmax(np.abs(ex42))]); signed43=float(ex43[np.argmax(np.abs(ex43))])
            aff=np.flatnonzero(a['afferent_spikes'][:,i]>0); mn=np.flatnonzero(a['motor_spikes'][:,i]>0); response=np.flatnonzero((np.abs(effect)>.01)&window)
            ordered=bool(len(aff) and len(mn) and len(response) and aff[0]<=mn[0]<response[0])
            metrics[l+'-'+context]={'peak_active_minus_passive_rad':peak,'duration_above_001_s':duration,
                'tactile_clamp_remaining_fraction':rem/peak if peak else None,'onset_afferent_s':float(aff[0]*.01) if len(aff) else None,
                'onset_motor_s':float(mn[0]*.01) if len(mn) else None,'response_onset_s':float(response[0]*.01) if len(response) else None,
                'onset_ordered_at_10ms_resolution':ordered,'seed42_excursion_rad':signed42,'seed43_excursion_rad':signed43,
                'seed_sign_consistent':bool(signed42*signed43>0),'peak_own_contact_over_weight':float(a['contact_ratios'][:,i].max()),
                'pass':bool(duration>=.05 and peak>0 and rem<=.2*peak and ordered and signed42*signed43>0)}
    repeat=np.load(OUT/'WT-LF-42-off-repeat/samples.npz'); original=np.load(OUT/'WT-LF-42-off-intact/samples.npz')
    exact=all(np.array_equal(repeat[k],original[k]) for k in original.files)
    # A coherent one-context chain must contain LF and at least one RM/RH.
    passed=any(metrics['LF-'+c]['pass'] and (metrics['RM-'+c]['pass'] or metrics['RH-'+c]['pass']) for c in ('off','neutral')) and exact
    return {'physical_causal_pass':passed,'metrics':metrics,'LF_repeat_all_arrays_exact':exact,'repeat_max_knee_rad':float(np.max(np.abs(repeat['knees']-original['knees']))),'scientific_trials':48,'deterministic_integrity_replays':1,'next_stage':'ABC and free-body' if passed else 'STOP dependent ABC and free-body'}

def main():
    assert json.loads((ROOT/'var/embodied-v7/replay/gate.json').read_text())['transduction_pass']
    OUT.mkdir(exist_ok=False); f=Fixture(); f.geometry(); geometry=probe_geometry(f)
    graph=Connectome(ORIGINAL/'data',verify=True); groups,rows=bind_annotations(graph,ORIGINAL/'data/raw/body-annotations.feather')
    compiler=Compiler(graph); subjects=json.loads((ROOT/'var/embodied-v7/subjects.json').read_text()); bindings=[]
    for subject in subjects:
        weights,manifest=compiler.load_weights(subject['artifact_id'],ORIGINAL/'var')
        assert manifest['phenotype']['neuron_parameters']==subject['spec']['neuron_parameters']
        bindings.append(subject|{'manifest_sha256':file_sha(ORIGINAL/'var/artifacts'/subject['artifact_id']/'manifest.json'),'weights_sha256':manifest['phenotype']['weights_sha256']})
    weights,manifest=compiler.load_weights(subjects[0]['artifact_id'],ORIGINAL/'var')
    b=EmbodiedBridge(CPUBrainBackend(Brain(graph,weights)),groups); rest=b.checkpoint()
    selected=np.unique(np.concatenate(list(groups.values()))); np.savez_compressed(OUT/'groups.npz',**groups,selected=selected)
    np.savez_compressed(OUT/'neural-rest.npz',**rest); write_json(OUT/'annotations.json',rows)
    sources=[ROOT/'src/flyarena'/n for n in ('neural.py','backend.py','compiler.py','connectome.py','experiments/contact_v6.py','experiments/embodied_v7.py','experiments/fixture_v7.py','experiments/sensor.py')]+[Path(__file__)]
    hashes={str(p):file_sha(p) for p in sources}
    protocol={'probe_geometry':geometry,'body_geometry_sha256':file_sha(ROOT/'var/embodied-v7/replay/geometry.json'),
        'motion':'radius .10mm tangent neutral distal tibia; .05mm inward linear .2-.3, hold .3-.4, withdraw .4-.5; end1s',
        'contexts':{'off':[0,0],'neutral':[.55,.55]},'seeds':{'42':'+.005rad own knee','43':'-.005rad own knee'},
        'scientific_panel':'six legs x two contexts x (seed42 intact,tactilezero,motorzero + seed43 intact) =48',
        'repeat':'one exact LF42 off verification continuation, not an additional scientific condition; see deviation.json',
        'source_hashes':hashes,'bindings':bindings,'graph_manifest_sha256':file_sha(graph.path/'manifest.json'),'raw_annotations_sha256':file_sha(ORIGINAL/'data/raw/body-annotations.feather'),
        'gate':'LF and one RM/RH in same context, own active-minus-motorzero>.01rad for>=.05s at10ms; tactilezero residual<=20%; response after own afferent and own MN onset; seed43 excursion sign agrees; exact LF repeat',
        'sample_timing':'body contact at t -> neural[t,t+.01]; body[t,t+.01] uses prior held command; record new command at endpoint; no instantaneous future motor access',
        'seed_sign_limit':'seed43 sign compares excursion from .2s, no seed43 passive controls authorized',
        'record_bound_bytes':700000000,'rmax':RMAX}
    write_json(OUT/'registration.json',protocol)
    for l in LEGS:
        for context in ('off','neutral'):
            for seed,control in ((42,'intact'),(43,'intact'),(42,'tactilezero'),(42,'motorzero')):
                run(f,b,rest,selected,groups,geometry,OUT/f'WT-{l}-{seed}-{context}-{control}',l,seed,context,control)
                print(json.dumps({'completed':f'WT-{l}-{seed}-{context}-{control}','spikes':b.backend.brain.total_spikes}),flush=True)
    run(f,b,rest,selected,groups,geometry,OUT/'WT-LF-42-off-repeat','LF',42,'off','intact')
    result=evaluate(); write_json(OUT/'gate.json',result); print(json.dumps(result),flush=True)
    assert all(file_sha(Path(p))==h for p,h in hashes.items())
    assert sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file())<700000000
    if result['physical_causal_pass']:
        for subject in subjects[1:]:
            weights,manifest=compiler.load_weights(subject['artifact_id'],ORIGINAL/'var')
            b=EmbodiedBridge(CPUBrainBackend(Brain(graph,weights)),groups); rest=b.checkpoint()
            for l in LEGS:
                for context in ('off','neutral'):
                    for seed in (42,43):
                        run(f,b,rest,selected,groups,geometry,OUT/f'{subject["role"]}-{l}-{seed}-{context}-intact',l,seed,context,'intact')
        write_json(OUT/'ABC-complete.json',{'trials':48,'subjects':bindings})

if __name__=='__main__': main()
