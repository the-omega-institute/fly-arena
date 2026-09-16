"""The fixed all-case distal-foot audit. No physical/neural trial entrypoint."""
from __future__ import annotations
import json,sys,time
from pathlib import Path
import numpy as np
from .realization_io_v11 import ROOT,RAW,OUT,SCRATCH,Budget,NumericChunks,sha,exclusive_json,failure,read_raw,slices
from .realization_native_v11 import Native,LEGS,RECORDS,SCHEMA,SHAPES,WIDTH
from .realization_parser_v11 import parse_ap,contact_runs,max_displacement,support_envelope

LO,HI,DT=6000,25000,.0001

def view_fields(values):
    s=slices(SCHEMA)
    return {k:values[:,s[k]].reshape(len(values),*SHAPES[k]) for k in s}

def corr(a,b):
    a=np.asarray(a,dtype=float);b=np.asarray(b,dtype=float)
    if np.std(a)==0 or np.std(b)==0:return None
    return float(np.corrcoef(a,b)[0,1])

def interval_metrics(d,lo,hi,record,leg,contact,adhesion):
    sl=slice(lo,hi+1);link=d['link_clearance'][sl,record,leg];low=link.min(axis=1)
    w=d['centroid_world'][sl,record,leg];body=d['centroid_thorax'][sl,record,leg]
    limiting=np.argmin(link,axis=1);ties=np.sum(link==low[:,None],axis=1)>1
    return {'samples':len(low),'wholefoot_peak_mm':float(low.max()),'wholefoot_min_mm':float(low.min()),
            'fraction_above_002':float(np.mean(low>.02)),'fraction_floor_intersection':float(np.mean(low<0)),
            'per_link_min_mm':link.min(axis=0).tolist(),'per_link_peak_mm':link.max(axis=0).tolist(),
            'limiting_link_counts':np.bincount(limiting,minlength=5).tolist(),'limiting_link_tie_samples':int(ties.sum()),
            'ap_range_mm':float(np.ptp(body[:,0])),'world_excursion_mm':max_displacement(w),'body_excursion_mm':max_displacement(body),
            'contact_duty_actual':float(contact[sl,leg].mean()),'adhesion_duty_actual':float(adhesion[sl,leg].mean()),
            'positive_normal_support_duty_actual':float(np.mean(d['normal_per_link'][sl,leg].sum(axis=1)>0))}

def parsed_metrics(d,phase,contact,adhesion):
    results={};paired=[]
    for r,record in enumerate(RECORDS):
        results[record]={}
        for leg,name in enumerate(LEGS):
            parsed=parse_ap(phase[:,leg],d['centroid_thorax'][:,r,leg,0],LO)
            for interval in parsed['intervals']:
                a=interval['start_tick']-LO;b=interval['end_tick_inclusive']-LO
                interval['metrics']=interval_metrics(d,a,b,r,leg,contact,adhesion)
                if interval['kind']=='stride':
                    mid=interval['aep_tick']-LO
                    interval['protraction']=interval_metrics(d,a,mid,r,leg,contact,adhesion)
                    interval['retraction']=interval_metrics(d,mid,b,r,leg,contact,adhesion)
                    if r==0:
                        interval['support_envelope']=support_envelope(d['centroid_world'][mid:b+1,0,leg],d['normal_per_link'][mid:b+1,leg].sum(axis=1),contact[mid:b+1,leg])
                        paired.append({'leg':name,'start_tick':a+LO,'aep_tick':mid+LO,'end_tick_inclusive':b+LO,'complete':interval['complete'],
                                       'ambiguities':interval['ambiguities'],'records':{
                                           key:{'whole_stride':interval_metrics(d,a,b,j,leg,contact,adhesion),
                                                'protraction':interval_metrics(d,a,mid,j,leg,contact,adhesion),
                                                'retraction':interval_metrics(d,mid,b,j,leg,contact,adhesion)} for j,key in enumerate(RECORDS)}})
            results[record][name]=parsed
    return results,paired

def original_bouts(d,phase,contact,old):
    out={};verified=0
    for leg,name in enumerate(LEGS):
        runs=contact_runs(contact[:,leg],phase[:,leg],LO)
        frozen={}
        for kind,key in [(False,'swing_cycles'),(True,'stance_cycles')]:
            for item in old[key][leg]:frozen[(kind,item['start_tick'],item['end_tick_exclusive'])]=item
        seen=set()
        for run in runs:
            a=run['start_tick']-LO;b=run['end_tick_exclusive']-LO
            original_indices=np.arange(a,b)[(np.arange(a,b)+LO)%10==0]
            n=len(original_indices);run['original_geometry_samples']=n;run['original_sample_category']='missing' if n==0 else 'single' if n==1 else 'multiple'
            w=d['centroid_world'][a:b,0,leg];clear=d['link_clearance'][a:b,0,leg].min(axis=1)
            run['dense_peak_wholefoot_mm']=float(clear.max());run['dense_displacement_mm']=max_displacement(w)
            run['dense_material_path_mm']=float(np.linalg.norm(np.diff(w,axis=0),axis=1).sum())
            run['original_peak_wholefoot_mm']=float(d['link_clearance'][original_indices,0,leg].min(axis=1).max()) if n else None
            run['original_displacement_mm']=max_displacement(d['centroid_world'][original_indices,0,leg])
            run['single_sample_zero_is_unresolved']=bool(n==1 and run['contact'])
            run['normal_support_duty']=float(np.mean(d['normal_per_link'][a:b,leg].sum(axis=1)>0))
            if run['original_qualifying']:
                key=(run['contact'],run['start_tick'],run['end_tick_exclusive'])
                if key not in frozen:raise ValueError('original bout boundary changed')
                seen.add(key);expected=frozen[key]
                actual=run['original_displacement_mm'] if run['contact'] else run['original_peak_wholefoot_mm']
                value=expected['max_foot_displacement_mm'] if run['contact'] else expected['peak_lowest_clearance_mm']
                if (actual is None)!=(value is None) or (actual is not None and abs(actual-value)>1e-12):raise ValueError('original bout metric changed')
                verified+=1
        if set(frozen)!=seen:raise ValueError('missing original bouts')
        out[name]=runs
    return out,verified

def realization_metrics(native,core,s,d):
    q=core[:,s['qpos']];v=core[:,s['qvel']];ctrl=core[:,s['ctrl']]
    target=native.targets_to_qpos(ctrl[:,native.active]);error=target-q[:,native.qadr]
    world=d['centroid_world'][:,0];components=d['velocity_components'];pred=components.sum(axis=2)
    finite=np.gradient(world,DT,axis=0,edge_order=1);residual=finite-pred
    integral=np.trapezoid(pred,dx=DT,axis=0);actual=world[-1]-world[0]
    rows=[]
    for leg,name in enumerate(LEGS):
        e=error[:,leg*7:(leg+1)*7];low=d['link_clearance'][:,0,leg].min(axis=1)
        comp=components[:,leg];normal=d['normal_per_link'][:,leg].sum(axis=1)
        rows.append({'leg':name,'tracking_rms_rad':np.sqrt(np.mean(e*e,axis=0)).tolist(),'tracking_max_abs_rad':np.abs(e).max(axis=0).tolist(),
                     'active_qpos_range_rad':np.ptp(q[:,native.qadr[leg*7:(leg+1)*7]],axis=0).tolist(),
                     'command_range_rad':np.ptp(target[:,leg*7:(leg+1)*7],axis=0).tolist(),
                     'passive_qpos_range_rad':np.ptp(q[:,native.passive_q[leg*4:(leg+1)*4]],axis=0).tolist(),
                     'passive_qvel_rms_rad_s':np.sqrt(np.mean(v[:,native.passive[leg*4:(leg+1)*4]]**2,axis=0)).tolist(),
                     'velocity_component_rms_xyz_mm_s':np.sqrt(np.mean(comp**2,axis=0)).tolist(),
                     'velocity_residual_rms_xyz_mm_s':np.sqrt(np.mean(residual[:,leg]**2,axis=0)).tolist(),
                     'velocity_residual_max_abs_xyz_mm_s':np.abs(residual[:,leg]).max(axis=0).tolist(),
                     'integrated_component_displacement_xyz_mm':np.trapezoid(comp,dx=DT,axis=0).tolist(),
                     'integrated_displacement_residual_xyz_mm':(actual-integral)[leg].tolist(),
                     'normal_support_duty':float(np.mean(normal>0)),'normal_force_peak_native':float(normal.max()),
                     'positive_distance_normal_fraction':float((normal-d['normal_nonpositive_distance'][:,leg]).sum()/normal.sum()) if normal.sum()>0 else None,
                     'correlations':{
                         'clearance_vs_tracking_error_norm':corr(low,np.linalg.norm(e,axis=1)),
                         'clearance_vs_net_correction':corr(low,core[:,s['net_correction']][:,leg]),
                         'clearance_vs_adhesion':corr(low,ctrl[:,native.adhesion[leg]]),
                         **{f'vertical_velocity_vs_{key}':corr(finite[:,leg,2],comp[:,j,2]) for j,key in enumerate(['root','active','passive'])}}})
    return {'legs':rows,'root_translation_range_mm':np.ptp(q[:,:3],axis=0).tolist(),
            'root_qvel_rms':np.sqrt(np.mean(v[:,:6]**2,axis=0)).tolist(),'root_quaternion_start':q[0,3:7].tolist(),'root_quaternion_end':q[-1,3:7].tolist(),
            'recorded_actuator_force_max_abs_native':float(np.abs(core[:,s['actuator_force']][:,native.active]).max()),
            'magnitudes_min':core[:,s['magnitudes']].min(axis=0).tolist(),'magnitudes_max':core[:,s['magnitudes']].max(axis=0).tolist(),
            'net_correction_max_abs':np.abs(core[:,s['net_correction']]).max(axis=0).tolist(),
            'trace_reference':'Raw hash-bound core qpos/qvel/ctrl/actuator_force/phases/magnitudes/retraction/stumbling/persistence/net_correction at ticks6000..25000; unit target recomputed from sealed native formula.'}

def verify_inputs(inputs,budget):
    for i,(name,item) in enumerate(inputs.items()):
        if sha(name)!=item['sha256']:raise ValueError('registered input hash mismatch: '+name)
        if i%200==0:budget.check()

def run_trial(item,reg,inputs,old,budget):
    casepath=OUT/'cases'/item['id'];writer=NumericChunks(casepath/'dense',WIDTH,{'schema':SCHEMA,'shapes':SHAPES,'records':RECORDS,'case':item,'registration_sha256':sha(OUT/'registration.json')})
    primary=None;summary=None;validation={'geometry_overlap_rows':0,'thorax_rows':0,'contact_rows':0,'max_force_balance_residual_native':0.,'source_command_max_error_rad':None}
    try:
        budget.check();raw=Path(item['raw']);s=slices(reg['core_schema'])
        _,x=read_raw(raw/'core',40001,sum(n for _,n in reg['core_schema']),1,inputs)
        gt,g=read_raw(raw/'geometry',4001,360,10,inputs)
        a=json.loads((raw/'core/start.json').read_text());b=json.loads((raw/'geometry/start.json').read_text())
        if a!=b or a['registration_sha256']!=sha(RAW/'registration.json') or a['sources_sha256']!=reg['sources_sha256']:raise ValueError('condition/identity mismatch')
        if (a['profile'],a['seed'],a['case'])!=(item['profile'],item['seed'],item['case']):raise ValueError('inventory condition mismatch')
        _,common,asym=item['case'];expected=np.zeros((40001,2));expected[3001:25001]=[common*(1-asym),common*(1+asym)]
        if not np.array_equal(x[:,s['input']],expected):raise ValueError('waveform mismatch')
        if not np.isin(x[:,s['foot_contact']],[0.,1.]).all():raise ValueError('invalid native contacts')
        native=Native();m=native.model
        for key in reg['compiled_arrays']:
            if not np.array_equal(getattr(m,key),np.load(RAW/f'model-{key}.npy',allow_pickle=False)):raise ValueError('model arrays changed')
        steady=x[LO:HI+1];phases=steady[:,s['phases']]
        if not (np.diff(phases,axis=0)>0).all():raise ValueError('phase/frame mismatch')
        unit=native.unit_targets(phases)
        source=native.source_targets(phases,steady[:,s['magnitudes']],steady[:,s['net_correction']])
        command=steady[:,s['ctrl']][:,native.active]
        err=float(np.abs(source-command).max());validation['source_command_max_error_rad']=err
        if err>1e-12:raise ValueError('source equation / recorded command mismatch')
        # Fresh diagnostic data, replaying only recorded observations. No resets,
        # state integration, CPG steps, or controller construction.
        for tick in range(LO):
            flags,_,_,_=native.observe(x[tick,s['qpos']],x[tick,s['qvel']],x[tick,s['ctrl']],tick)
            if not np.array_equal(flags,x[tick,s['foot_contact']]):raise ValueError(f'prefix contact mismatch {tick}')
            if tick%1000==0:budget.check()
        arrays=[]
        for begin in range(LO,HI+1,1000):
            end=min(begin+1000,HI+1);n=end-begin;budget.check()
            positions=np.empty((n,3,30,3));rotations=np.empty((n,3,30,3,3));vel=np.empty((n,6,3,3));normals=np.empty((n,30));penetrating=np.empty((n,6))
            tp=x[begin:end,s['thorax_position']];tr=x[begin:end,s['thorax_rotation']].reshape(n,3,3)
            for i,tick in enumerate(range(begin,end)):
                flags,normals[i],penetrating[i],balance=native.observe(x[tick,s['qpos']],x[tick,s['qvel']],x[tick,s['ctrl']],tick,tick%10==0)
                validation['max_force_balance_residual_native']=max(validation['max_force_balance_residual_native'],balance)
                if not np.array_equal(flags,x[tick,s['foot_contact']]):raise ValueError(f'contact mismatch at {tick}')
                validation['contact_rows']+=1;dd=native.actual
                if not np.array_equal(dd.xpos[native.thorax],tp[i]) or not np.array_equal(dd.xmat[native.thorax].reshape(3,3),tr[i]):raise ValueError(f'thorax frame mismatch {tick}')
                validation['thorax_rows']+=1
                positions[i],rotations[i]=native.transforms(x[tick,s['qpos']],command[tick-LO],unit[tick-LO])
                if tick%10==0:
                    recorded=g[tick//10]
                    if not np.array_equal(positions[i,0],recorded[:90].reshape(30,3)) or not np.array_equal(rotations[i,0],recorded[90:].reshape(30,3,3)):raise ValueError(f'geometry overlap mismatch {tick}')
                    validation['geometry_overlap_rows']+=1
                point=np.einsum('lij,lj->li',rotations[i,0,4::5],native.centroids)+positions[i,0,4::5]
                vel[i]=native.velocities(point)
            low,world,body=native.geometry(positions,rotations,tp,tr)
            values=np.concatenate([low.reshape(n,-1),world.reshape(n,-1),body.reshape(n,-1),vel.reshape(n,-1),normals,penetrating],axis=1)
            if not np.isfinite(values).all():raise FloatingPointError('nonfinite dense geometry')
            for i,row in enumerate(values):writer.append(begin+i,row)
            writer.flush();arrays.append(values)
            print(json.dumps({'case':item['id'],'last_committed_tick':end-1,'rows':writer.committed}),flush=True)
        values=np.concatenate(arrays);d=view_fields(values);contacts=steady[:,s['foot_contact']].astype(bool);adhesion=steady[:,s['ctrl']][:,native.adhesion]
        if not np.isin(adhesion,[0.,1.]).all():raise ValueError('invalid adhesion')
        parsed,paired=parsed_metrics(d,phases,contacts,adhesion)
        bouts,verified=original_bouts(d,phases,contacts,old)
        validation['original_qualifying_bouts_verified']=verified
        realization=realization_metrics(native,steady,s,d)
        summaries=[]
        for r,key in enumerate(RECORDS):
            for leg,name in enumerate(LEGS):
                intervals=[i for i in parsed[key][name]['intervals'] if i['kind']=='stride']
                complete=[i for i in intervals if i['complete']]
                summaries.append({'record':key,'leg':name,'window':interval_metrics(d,0,len(values)-1,r,leg,contacts,adhesion),
                                  'complete_strides':len(complete),'partial_strides':len(intervals)-len(complete),
                                  'ambiguous_complete_strides':sum(bool(i['ambiguities']) for i in complete),
                                  'complete_stride_peak_above_002':sum(i['metrics']['wholefoot_peak_mm']>.02 for i in complete),
                                  'complete_protraction_peak_above_002':sum(i['protraction']['wholefoot_peak_mm']>.02 for i in complete),
                                  'minimum_complete_stride_peak_mm':min([i['metrics']['wholefoot_peak_mm'] for i in complete],default=None),
                                  'maximum_complete_stride_peak_mm':max([i['metrics']['wholefoot_peak_mm'] for i in complete],default=None)})
        exclusive_json(casepath/'parsed.json',parsed);exclusive_json(casepath/'paired.json',paired);exclusive_json(casepath/'original-bouts.json',bouts)
        summary={'schema':'distal-case/v11','case':item,'validation':validation,'records':summaries,'realization':realization,
                 'raw_identity':a,'old_gates_verbatim':old['gates'],'new_admission':False}
        exclusive_json(casepath/'summary.json',summary);budget.check()
    except BaseException as exc:
        primary=failure(exc,'audit-trial')
    finally:
        terminal=writer.finish(primary,{'validation':validation,'summary_written':summary is not None})
        if not terminal['complete'] and primary is None:primary={'type':'RetentionFailure','message':'dense finalization failed','stage':'audit-trial'}
    if primary:raise RuntimeError(json.dumps(primary))
    return summary

def seal():
    sources={}
    for base in ['src','scripts','tests']:
        for p in sorted((ROOT/base).rglob('*v11*')):
            if p.is_file() and p.suffix in ['.py','.sh']:sources[str(p)]={'sha256':sha(p),'bytes':p.stat().st_size}
    for p in [OUT/'registration.json',OUT/'registration-addendum.json',OUT/'inputs.json',OUT/'native.json',OUT/'tests.xml',OUT/'tests-final.xml']:
        sources[str(p)]={'sha256':sha(p),'bytes':p.stat().st_size}
    exclusive_json(OUT/'implementation-seal.json',{'schema':'pre-outcome-implementation-seal/v11','files':sources,'utc':time.time()})

def run():
    budget=Budget();primary=None;errors=[];complete=[];summaries=[];items=[]
    exclusive_json(OUT/'execution-start.json',{'schema':'distal-start/v11','utc':time.time(),'physical_seconds':0,'neural_seconds':0})
    try:
        registration=json.loads((OUT/'registration.json').read_text());items=registration['inventory']
        if len(items)!=28:raise ValueError('required all28 inventory')
        inputs=json.loads((OUT/'inputs.json').read_text());sealdata=json.loads((OUT/'implementation-seal.json').read_text())
        verify_inputs(sealdata['files'],budget);verify_inputs(inputs,budget)
        (OUT/'cases').mkdir(exist_ok=False)
        for item in items:
            p=OUT/'cases'/item['id'];p.mkdir(exist_ok=False);exclusive_json(p/'initialized.json',{'case':item,'rows':0})
        reg=json.loads((RAW/'registration.json').read_text());old=json.loads((RAW/'development-decision.json').read_text())['trials']
        for item in items:
            summary=run_trial(item,reg,inputs,old[item['id']],budget);summaries.append(summary);complete.append(item['id'])
            exclusive_json(OUT/f'progress-{len(complete):02d}.json',{'complete':complete.copy(),'resources':budget.report()})
        verify_inputs(sealdata['files'],budget);verify_inputs(inputs,budget)
        exclusive_json(OUT/'all-conditions.json',{'schema':'distal-all-conditions/v11','cases':summaries,'complete':complete,
                       'old_failure_verbatim':registration['old_failure_verbatim'],'downstream':registration['downstream'],
                       'scientific_admission':False,'interpretation':'Kinematic references at fixed actual root/passive state; support forces are instantaneous native forward reconstructions. No dynamic counterfactual or causality established.'})
        budget.check()
    except BaseException as exc:
        primary=failure(exc,'execution')
    finally:
        skipped=[i['id'] for i in items if i['id'] not in complete]
        for name in skipped:
            try:
                p=OUT/'cases'/name
                if p.exists():exclusive_json(p/'incomplete.json',{'case':name,'reason':primary,'retained_partial':(p/'dense').exists()})
            except BaseException as exc:errors.append(failure(exc,'incomplete-case-receipt'))
        try:resources=budget.report()
        except BaseException as exc:resources=None;errors.append(failure(exc,'resource-report'))
        receipt={'schema':'distal-execution-terminal/v11','complete':primary is None and not errors and len(complete)==28,
                 'primary_failure':primary,'retention_failures':errors,'complete_cases':complete,'skipped_or_incomplete_cases':skipped,'resources':resources}
        try:exclusive_json(OUT/'execution-terminal.json',receipt)
        except BaseException as exc:
            errors.append(failure(exc,'execution-terminal'));receipt['complete']=False
            try:exclusive_json(SCRATCH/'execution-failure.json',receipt)
            except BaseException as fallback:
                errors.append(failure(fallback,'fallback-terminal'));print('TOTAL FILESYSTEM FAILURE: cannot guarantee durable receipt '+json.dumps(receipt),file=sys.stderr)
    print(json.dumps(receipt),flush=True)
    if not receipt['complete']:raise SystemExit(1)

if __name__=='__main__':
    if sys.argv[1:] == ['seal']:seal()
    elif sys.argv[1:] == ['run']:run()
    else:raise SystemExit('usage: realization_v11 seal|run')
