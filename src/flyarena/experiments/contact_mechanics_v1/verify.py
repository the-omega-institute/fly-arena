"""Single native reconstruction traversal, independent actions and physical metrics."""
from pathlib import Path
from types import SimpleNamespace
import time
import numpy as np
from .schema import *
from .io import read,write,sha,stream_rows,digest,account_existing,RetentionError
from .oracle import agree,verify_candidate
from .metrics import realized_partition,physical_runs,independent_realized_gate,pose_gates
from .geometry import Geometry,prepare
from .proof import (metadata,registration_context,check_terminal,check_core,validate_reset_row,write_seal,validate_seal,active_actions)
REALIZED_FIELDS=('phi','modes','cycle','resume_modes','wait_count','lag','admitted','distal_count','load_count')

DERIVED=(('height',6),('distal',18),('ap',6),('position',3),('rotation',9),('normal',6),('weighted',6),('peak',6))
class Reference:
    def __init__(self,geometry,steps):self.geometry=geometry;self.steps=steps
    def angles(self,phi,magnitude):return np.asarray([self.steps.get_joint_angles(leg,phi[i],magnitude[i]) for i,leg in enumerate(self.steps.legs)])
    def excursion(self,i,obs,magnitude):return self.geometry.excursion(self.steps,i,obs,magnitude)

def paired_rows(trial,profile):
    a=iter(stream_rows(trial/'core',CORE,allow_partial=True));b=iter(stream_rows(trial/'state',CANDIDATE if profile==PROFILE else LEGACY,allow_partial=True))
    count=0
    while True:
        ar=next(a,None);br=next(b,None)
        if ar is None or br is None:
            if ar is not None or br is not None:raise ValueError('core/state incomplete pairing')
            return
        if ar[0]!=count or br[0]!=count:raise ValueError('dense endpoint exact grid')
        yield count,ar[1],br[1];count+=1

def contacts_by_tick(trial):
    iterator=iter(stream_rows(trial/'contacts',CONTACT,allow_partial=True));pending=next(iterator,None)
    def get(tick):
        nonlocal pending
        rows=[]
        while pending is not None and pending[0]==tick:
            rows.append(pending[1]);pending=next(iterator,None)
        if pending is not None and pending[0]<tick:raise ValueError('unconsumed contact row')
        if len(rows)>512:raise ValueError('contact capacity')
        ids=[]
        for row in rows:
            r=unpack(CONTACT,row)
            for name in ('index','geom','ground','leg','geom_order','interval_start','interval_end'):
                if r[name][0]!=int(r[name][0]):raise ValueError('fractional contact identity')
            if r['interval_end'][0]!=tick or r['interval_start'][0]!=tick-1:raise ValueError('contact interval clock')
            if r['index'][0]<0 or r['geom'][0]<0 or r['ground'][0]<0 or not -1<=r['leg'][0]<=5 or r['geom_order'][0] not in (0,1):raise ValueError('contact native identity domain')
            ids.append(int(r['index'][0]))
        if ids!=sorted(set(ids)):raise ValueError('native contact order/identity')
        return rows
    return get,lambda:pending is None

def legacy_projection(core,legacy,oldschema):
    c=unpack(CORE,core);old=unpack(LEGACY,legacy)
    old.update(qpos=c['qpos'],qvel=c['qvel'],input=c['input'],ctrl=c['ctrl'],actuator_force=c['force'],phases=c['theta'],magnitudes=c['magnitude'])
    return pack(oldschema,old)

def candidate_state(core,row,indices):
    s=state_from_rows(core,row);c=unpack(CORE,core);s['angles']=c['ctrl'][indices];s['adhesion']=c['ctrl'][42:].astype(bool)
    if np.any((c['ctrl'][42:]!=0)&(c['ctrl'][42:]!=1)):raise ValueError('adhesion encoding')
    return s

def verify_trial(root,trial,reg,budget,model,steps):
    """Reconstruct every retained row once; no physics/controller calls."""
    import mujoco as mj
    from ..contact_v1.contracts import Binding,decode,encode
    from .original_metrics import helpers
    _cycle_metrics,_cycle_gate,_=helpers()
    root=Path(root);dest=root/trial.stage/trial.name;terminal=read(dest/'trial-terminal.json');expected=metadata(root,trial,reg)
    for stream in ('core','contacts','state'):
        if read(dest/stream/'start.json')!=expected:raise ValueError('trial/stream identity')
    n=check_terminal(terminal,trial)
    if n<1 or n>40001 or terminal['scheduled_ticks']!=40000 or terminal['missing_remainder']!=40001-n:raise ValueError('trial denominator')
    if len(reg['bodies'])!=reg['fly_body_count'] or not 0<len(reg['bodies'])<=68:raise ValueError('frozen fly body count')
    binding=Binding(**decode(reg['binding']));indices=np.asarray(reg['indices'],dtype=int);geometry=Geometry(model,binding,reg['thorax'],reg['bodies']);reference=Reference(geometry,steps)
    budget.check(pending=n*(6*8*12+120*8)+2*1024**2)
    theta=np.empty((n,6));ap=np.empty((n,6));height=np.empty((n,6));normal=np.zeros((n,6));weighted=np.zeros((n,6));peak=np.zeros((n,6));position=np.empty((n,3));rotation=np.empty((n,3,3))
    realized={k:np.empty((n,6)) for k in REALIZED_FIELDS} if trial.profile==PROFILE else None
    oldcore=None
    if trial.profile==CONTROL:
        from ..mechanical_v16 import CORE as OLDCORE,PROFILE as V16
        from ..verify_v16 import verify_allocation_row,verify_phase_law,verify_retraction_and_commands
        budget.check(pending=n*width(OLDCORE)*8);oldcore=np.empty((n,width(OLDCORE)))
    current=mj.MjData(model);prior=mj.MjData(model);rows=iter(paired_rows(dest,trial.profile));item=next(rows,None);get_contacts,contacts_done=contacts_by_tick(dest)
    derived=[];offset=0;count=0;max_geometry=max_velocity=0.;active_checked=0;lastcount=0;blockstart=time.monotonic()
    # Only low-dimensional physical derived arrays are retained. Source q/v remain in primary stream.
    from .io import BudgetEvidence
    writer=BudgetEvidence(dest/'derived',width(DERIVED),metadata=expected,budget=budget)
    failure=None
    try:
        while item is not None:
            tick,core,state=item;nextitem=next(rows,None);c=unpack(CORE,core);contacts=get_contacts(tick)
            if tick>=n:raise ValueError('extra retained endpoint')
            for field in ('action_tick','observation_tick','interval_present','contact_offset','contact_count'):
                if c[field][0]!=int(c[field][0]):raise ValueError('fractional physical clock')
            if abs(c['time'][0]-tick*DT)>1e-9 or c['action_tick'][0]!=tick-1 or c['interval_present'][0]!=int(tick>0) or c['contact_offset'][0]!=offset or c['contact_count'][0]!=len(contacts):raise ValueError('physical/interval clock mapping')
            want_u=waveform(trial.case,tick-1) if tick else np.zeros(2);agree(c['input'],want_u,'registered waveform',exact=True)
            check_core(trial,tick,core,state,offset,len(contacts))
            if tick==0:validate_reset_row(root,trial,core,state,reg)
            offset+=len(contacts);u_next=waveform(trial.case,tick);active=nextitem is not None and np.mean(u_next)>1e-4
            prepare(model,current,c['qpos'],c['qvel']);endpoint=geometry.endpoint(current,jacobians=active and trial.profile==PROFILE)
            max_geometry=max(max_geometry,endpoint.geometry_error);height[tick]=endpoint.height;ap[tick]=endpoint.ap;position[tick]=endpoint.thorax_pos;rotation[tick]=endpoint.thorax_rotation;theta[tick]=c['theta']
            if tick:
                normal[tick],weighted[tick],peak[tick],err=geometry.interval_metrics(prior,contacts,prior.qvel);max_velocity=max(max_velocity,err)
            elif contacts:raise ValueError('row0 has no completed interval')
            writer.append(tick,pack(DERIVED,{'height':height[tick],'distal':endpoint.distal,'ap':ap[tick],'position':position[tick],'rotation':rotation[tick],'normal':normal[tick],'weighted':weighted[tick],'peak':peak[tick]}))
            if realized is not None:
                numeric=unpack(CANDIDATE,state)
                for key in realized:realized[key][tick]=numeric[key]
                pre=candidate_state(core,state,indices)
                if c['observation_tick'][0]!=pre['last_tick']:raise ValueError('candidate action observation clock')
                if nextitem is not None:
                    post=candidate_state(nextitem[1],nextitem[2],indices)
                    if active:
                        obs=geometry.observation(current,prior,endpoint,contacts,tick,c['force']);budget.charge('independent_candidate')
                        verify_candidate(pre,post,obs,u_next,binding,reference);budget.complete('independent_candidate');active_checked+=1
                    else:
                        agree(nextitem[2],state,'silent complete compact candidate state',exact=True)
                        nxt=unpack(CORE,nextitem[1])
                        for key in ('theta','magnitude','ctrl'):agree(nxt[key],c[key],'silent '+key,exact=True)
            else:
                oldcore[tick]=legacy_projection(core,state,OLDCORE)
                if active:
                    minima=[]
                    for leg in range(6):
                        selected=min(range(5),key=lambda j:(endpoint.minima[leg,j,2],int(binding.foot_geoms[leg,j]),int(endpoint.minimum_vertices[leg,j])))
                        minima.append((float(endpoint.minima[leg,selected,2]),int(binding.foot_geoms[leg,selected]),int(endpoint.minimum_vertices[leg,selected])))
                    nextold=legacy_projection(nextitem[1],nextitem[2],OLDCORE)
                    verify_allocation_row(model,current,oldcore[tick],nextold,minima,{'controller':reg['legacy_controller']},profile=V16);active_checked+=1
            count+=1
            if tick%100==0:budget.check()
            if tick and tick%1000==0:
                budget.forecast('reconstruction',time.monotonic()-blockstart,count-lastcount,n-count+budget.future_reconstruction);budget.forecast_bytes(count-lastcount,n-count+budget.future_reconstruction);lastcount=count;blockstart=time.monotonic()
            prior,current=current,prior;item=nextitem
        if count!=n or not contacts_done():raise ValueError('missing/extra endpoint/contact rows')
        if count>lastcount:budget.forecast('reconstruction',time.monotonic()-blockstart,count-lastcount,budget.future_reconstruction)
        else:budget.remaining['reconstruction']=budget.future_reconstruction
        analysis_started=time.monotonic()
        if oldcore is not None:
            verify_phase_law(oldcore,V16,{'controller':reg['legacy_controller']});verify_retraction_and_commands(oldcore,V16,{'controller':reg['legacy_controller']})
        result=analyze_arrays(trial,{**reg,'beta':binding.beta.tolist()},terminal,theta,ap,height,normal,weighted,peak,position,rotation,realized)
        result.update(independent_numeric_pass=True,integration_passed=True,retention_passed=terminal['retention_passed'],active_actions_checked=active_checked,endpoint_rows_checked=count,contacts_checked=offset,max_geometry_error=max_geometry,max_velocity_error=max_velocity)
    except BaseException as exc:
        failure=exc;budget.finalizing=True
        from ..contact_v1.contracts import encode
        try:
            def portable(value):
                if isinstance(value,SimpleNamespace):return {k:portable(v) for k,v in vars(value).items()}
                if isinstance(value,(list,tuple)):return [portable(v) for v in value]
                return value
            from .runtime import cache_export
            with (dest/'first-mismatch-native-cache.npz').open('xb') as handle:np.savez_compressed(handle,**cache_export(current))
            account_existing(dest/'first-mismatch-native-cache.npz')
            write(dest/'first-verification-mismatch.json',{'tick':count,'type':type(exc).__name__,'message':str(exc),'core':encode(core),'state':encode(state),'contacts':encode(np.asarray(contacts).reshape(-1,width(CONTACT))),'current_qpos':encode(current.qpos.copy()),'current_qvel':encode(current.qvel.copy()),'independent_prediction':encode(getattr(exc,'independent_prediction',None)),'independent_observation':encode(portable(getattr(exc,'independent_observation',None)))})
        finally:raise
    finally:
        budget.finalizing=True
        try:
            child=writer.finish(failure)
            if not child['complete'] or child['retention_failures']:
                if failure is None:raise RetentionError('derived verification retention failed')
        finally:writer.release();budget.finalizing=False
    write(dest/'analysis-verification.json',result)
    write_seal(root,trial,reg,result)
    validate_seal(root,trial,reg,terminal,count,offset)
    budget.note_finalization(time.monotonic()-analysis_started)
    budget.forecast('analysis_finalization',time.monotonic()-analysis_started,1,budget.future_trials)
    result['verification_closure_validated']=True
    return result

def analyze_arrays(trial,reg,terminal,theta,ap,height,normal,weighted,peak,position,rotation,realized):
    from .original_metrics import helpers
    n=len(theta);complete=terminal['complete'];active_case=trial.case[1]>0;lo=6000;hi=min(25000,n-1)
    if complete and n!=40001:raise ValueError('complete trial has missing rows')
    primary=realized_result=None;physical_primary=False;physical_realized=False
    if hi>lo:
        _cycle_metrics,_cycle_gate,_=helpers(lo,hi);swing=reg['legacy_controller']['swing_periods_strict_modulo']
        primary=_cycle_metrics(theta,ap,height,normal,weighted,peak,swing,strict_active_window=active_case)
        iv=_cycle_gate(theta,ap,height,normal,weighted,swing)
        if active_case and tuple(iv[:3])!=(primary['recovery_passed'],primary['support_slip_passed'],primary['invalid_interior_phase_episodes']):raise ValueError('independent primary cycle disagreement')
        primary['retained_window_inclusive']=[lo,hi]
        physical_primary=not active_case or (primary['recovery_passed'] and primary['support_slip_passed'] and not primary['invalid_interior_phase_episodes'])
        if realized is not None:
            partitions=realized_partition(realized['phi'],realized['modes'],realized['cycle'],realized['resume_modes'],np.asarray(reg['beta']),realized['wait_count'],realized['lag'],lo=lo,hi=hi,active=active_case,
              admitted=realized.get('admitted'),distal_count=realized.get('distal_count'),load_count=realized.get('load_count'))
            realized_result=physical_runs(partitions,ap,height,normal,weighted,peak)
            independent=independent_realized_gate(realized['phi'],realized['modes'],realized['cycle'],ap,height,normal,weighted,lo=lo,hi=hi)
            # Phase conformance never contaminates the separate physical arithmetic comparison.
            if active_case and tuple(independent[:2])!=(realized_result['recovery_passed'],realized_result['support_slip_passed']):raise ValueError('independent realized physical gate disagreement')
            realized_result['retained_window_inclusive']=[lo,hi]
            physical_realized=not active_case or (realized_result['recovery_passed'] and realized_result['support_slip_passed'] and realized_result['phase_valid'])
        else:physical_realized=True
    if not complete:
        return {'report_schema':'contact-mechanics-analysis/v2','trial_id':trial.identity,'complete':False,'all_original_gates_pass':False,
          'inconclusive':True,'controller_failure':terminal.get('failure_kind')=='controller_infeasible','missing_remainder':True,
          'scheduled_ticks':40000,'retained_completed_ticks':max(0,n-1),'missing_ticks':40001-n,'partials_retained':True,
          'prefix_rows_checked':n,'failure_kind':terminal.get('failure_kind'),'primary':primary,'realized':realized_result,
          'retained_active_window':None if hi<lo else [lo,hi],'retained_original_physical_pass':bool(physical_primary),
          'retained_realized_physical_pass':bool(physical_realized),'realized_passed':False,'candidate_passed':False}
    gates,summary=pose_gates(position,rotation,trial.case)
    if active_case:gates.update(recovery=primary['recovery_passed'],support_slip=primary['support_slip_passed'])
    return {'report_schema':'contact-mechanics-analysis/v2','trial_id':trial.identity,'complete':True,'all_original_gates_pass':bool(all(gates.values())),
      'inconclusive':False,'controller_failure':False,'missing_remainder':False,'scheduled_ticks':40000,'retained_completed_ticks':40000,'missing_ticks':0,
      'partials_retained':True,'gates':gates,'summary':summary,'primary':primary,'realized':realized_result,'realized_passed':bool(physical_realized),
      'candidate_passed':bool(all(gates.values()) and physical_realized)}

def checked_report(trial,value):
    required={'report_schema','trial_id','complete','all_original_gates_pass','realized_passed','inconclusive','controller_failure','missing_remainder',
      'candidate_passed','independent_numeric_pass','integration_passed','retention_passed','verification_closure_validated','scheduled_ticks','retained_completed_ticks','missing_ticks'}
    if not isinstance(value,dict) or not required<=set(value) or value['report_schema']!='contact-mechanics-analysis/v2' or value['trial_id']!=trial.identity:raise ValueError('admission report schema/identity')
    flags=required-{'report_schema','trial_id','scheduled_ticks','retained_completed_ticks','missing_ticks'}
    if any(type(value[k]) is not bool for k in flags):raise ValueError('admission Boolean domain')
    if not all(value[k] for k in ('independent_numeric_pass','integration_passed','retention_passed','verification_closure_validated')):raise ValueError('unverified integration/retention report')
    if any(type(value[k]) is not int for k in ('scheduled_ticks','retained_completed_ticks','missing_ticks')) or value['scheduled_ticks']!=40000 or not 0<=value['retained_completed_ticks']<=40000 or value['missing_ticks']!=40000-value['retained_completed_ticks']:raise ValueError('admission full denominator')
    if not value['complete']:
        if trial.profile==CONTROL:raise ValueError('incomplete comparator integration')
        if value['candidate_passed'] or value['all_original_gates_pass'] or value['realized_passed'] or not value['missing_remainder'] or not value['inconclusive']:raise ValueError('contradictory incomplete candidate')
        return False
    if value['missing_ticks'] or value['missing_remainder'] or value['inconclusive'] or value['controller_failure']:raise ValueError('contradictory complete report')
    gates=value.get('gates',{});keys={'finite','upright','stop'}
    if trial.case[1]>0:keys.update(('turn' if trial.case[2] else 'straight_yaw','recovery','support_slip'))
    if set(gates)!=keys or any(type(v) is not bool for v in gates.values()) or value['all_original_gates_pass']!=all(gates.values()):raise ValueError('stale original gate aggregate')
    if trial.case[1]>0:
        primary=value.get('primary')
        if not isinstance(primary,dict) or any(type(primary.get(k)) is not bool for k in ('recovery_passed','support_slip_passed')) or type(primary.get('invalid_interior_phase_episodes')) is not int or primary['invalid_interior_phase_episodes']<0:raise ValueError('original physical gate evidence')
        if (gates['recovery'],gates['support_slip'])!=(primary['recovery_passed'],primary['support_slip_passed']):raise ValueError('stale original physical gates')
        if primary['invalid_interior_phase_episodes']>0 and primary['recovery_passed'] and primary['support_slip_passed']:
            raise ValueError('invalid primary phase episodes contradict passing physical gates')
    realized=True
    if trial.profile==PROFILE:
        r=value.get('realized')
        if not isinstance(r,dict) or any(type(r.get(k)) is not bool for k in ('recovery_passed','support_slip_passed','phase_valid')):raise ValueError('realized gate evidence')
        realized=trial.case[1]==0 or (r['recovery_passed'] and r['support_slip_passed'] and r['phase_valid'])
    if value['realized_passed']!=realized or value['candidate_passed']!=(all(gates.values()) and realized):raise ValueError('stale candidate gate aggregate')
    speed=value.get('summary',{}).get('forward_mean_mm_s')
    if isinstance(speed,bool) or not isinstance(speed,(int,float)) or not np.isfinite(speed):raise ValueError('finite summary speed')
    return value['candidate_passed']

def panel_admission(trials,stage):
    expected={t.identity:t for t in panel(stage)}
    if set(trials)!=set(expected):raise ValueError('panel denominator identity')
    decisions={key:checked_report(trial,trials[key]) for key,trial in expected.items()}
    selected={key:value for key,value in trials.items() if expected[key].profile==PROFILE};aggregates={}
    for seed in ((42,43) if stage=='development' else (31042,31043)):
        names=[f'{stage}/{PROFILE}--{seed}--{case}' for case in ('straight-008','straight-02','straight-04')]
        values=[selected[name].get('summary',{}).get('forward_mean_mm_s') for name in names]
        aggregates[str(seed)]=bool(all(isinstance(v,(int,float)) and not isinstance(v,bool) and np.isfinite(v) for v in values) and values[0]>.2 and all(b-a>.2 for a,b in zip(values,values[1:])))
    passed=all(decisions[key] for key in selected) and all(aggregates.values())
    return {'stage':stage,'passed':bool(passed),'aggregate_speed_dose':aggregates,'trials':trials,'ready':False}

def independent_saved_review(root):
    """Check protocol closure and recompute numeric metrics without another native pass.

    A validated producer attestation binds the one registered traversal. Hashes
    cannot establish authenticity or independently reproduce native mathematics.
    """
    from ..contact_v1.contracts import decode
    root=Path(root);reg,pre=registration_context(root);statuses=read(root/'panel-terminal.json')
    if statuses['registration_sha256']!=sha(root/'registration.json'):raise ValueError('verification registration identity')
    expected={t.identity:t for stage in ('development','heldout','repeat') for t in panel(stage)}
    if set(statuses['trials'])!=set(expected):raise ValueError('terminal denominator')
    reports={};prefixes={};reg={**reg,'beta':decode(reg['binding'])['beta']}
    for identity,trial in expected.items():
        dest=root/trial.stage/trial.name;status=statuses['trials'][identity]['status']
        if not (dest/'trial-terminal.json').exists():
            if status in ('complete','failed_incomplete'):raise ValueError('missing measured trial')
            continue
        terminal=read(dest/'trial-terminal.json');n=check_terminal(terminal,trial)
        if terminal.get('setup_failed') and not terminal.get('retained_rows',{}).get('core',0):
            if (dest/'numeric-verification-seal.json').exists() or status=='complete':raise ValueError('setup failure claimed verification')
            prefixes[identity]={'rows':0,'missing_remainder':40000,'native_numeric_verification_complete':False};continue
        # An unsealed interrupted writer can retain fewer rows than successful physics calls.
        n=terminal.get('retained_rows',{}).get('core',n)
        if type(n) is not int or not 0<n<=terminal['completed_ticks']+1:raise ValueError('retained endpoint domain')
        theta=np.empty((n,6));rstate={k:np.empty((n,6)) for k in REALIZED_FIELDS} if trial.profile==PROFILE else None
        count=0;offset=0;contact_reader,done=contacts_by_tick(dest)
        for stream in ('core','state','contacts'):
            if read(dest/stream/'start.json')!=metadata(root,trial,reg):raise ValueError('saved stream trial/reset/source metadata')
        for tick,core,state in paired_rows(dest,trial.profile):
            if tick>=n:raise ValueError('extra endpoint')
            rows=contact_reader(tick);c=check_core(trial,tick,core,state,offset,len(rows));theta[tick]=c['theta']
            if tick==0:validate_reset_row(root,trial,core,state,reg)
            if rstate is not None:
                numeric=unpack(CANDIDATE,state)
                for key in rstate:rstate[key][tick]=numeric[key]
            offset+=len(rows);count+=1
        if count!=n or not done():raise ValueError('saved endpoint/contact denominator')
        if not (dest/'numeric-verification-seal.json').exists():
            if status=='complete':raise ValueError('complete panel trial lacks verification closure')
            prefixes[identity]={'rows':n,'missing_remainder':40001-n,'native_numeric_verification_complete':False};continue
        if n!=terminal['completed_ticks']+1:raise ValueError('native seal has unretained completed endpoints')
        if status=='complete' and not terminal['complete'] or status=='failed_incomplete' and terminal['complete']:raise ValueError('panel/trial completion mismatch')
        if status not in ('complete','failed_incomplete','stopped'):raise ValueError('unstarted trial has native attestation')
        saved=validate_seal(root,trial,reg,terminal,n,offset)
        derived=np.empty((n,width(DERIVED)));count=0
        for tick,row in stream_rows(dest/'derived',DERIVED):
            if tick!=count or tick>=n:raise ValueError('derived exact grid')
            derived[tick]=row;count+=1
        if count!=n:raise ValueError('derived missing endpoint')
        d={k:derived[:,v] for k,v in slices(DERIVED).items()}
        actual=analyze_arrays(trial,reg,terminal,theta,d['ap'],d['height'],d['normal'],d['weighted'],d['peak'],d['position'],d['rotation'].reshape(n,3,3),rstate)
        if digest(actual)!=digest({k:saved[k] for k in actual}):raise ValueError('saved metric recomputation disagreement')
        actual.update(independent_numeric_pass=True,integration_passed=True,retention_passed=True,verification_closure_validated=True);reports[identity]=actual
    decisions={}
    for stage in ('development','heldout'):
        selected={k:v for k,v in reports.items() if k.startswith(stage+'/')}
        if len(selected)==len(panel(stage)):decisions[stage]=panel_admission(selected,stage)['passed']
    return {'scheduled_ids':len(expected),'numeric_metrics_recomputed':len(reports),'prefixes_without_complete_native_verification':prefixes,
      'admission':decisions,'ready':False,'native_calls':0,'action_check_scope':'validated evidence closure of the single registered native traversal; producer attestation, not hash-based authenticity'}
