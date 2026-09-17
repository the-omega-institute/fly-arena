"""Only this registered runtime may build/step native bodies; imports are lazy."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json,time,hashlib,os
import numpy as np
from .schema import *
from .io import write,read,sha,digest,Writers,account_existing,RetentionError
from .budget import Budget
from .registration import validate
from .control_evidence import control_snapshot
from .proof import metadata

def integration(body):
    import mujoco as mj
    signature=mj.mjtState.mjSTATE_INTEGRATION
    result=np.empty(mj.mj_stateSize(body.model,signature));mj.mj_getState(body.model,body.data,result,signature);return result

def science_state(port):
    from ..contact_v1.contracts import encode
    return {'controller':port.controller.checkpoint(),'sensor':encode(port.sensor_state),'recorder':encode(port.recorder_state),'tick':port.body.tick,'drives':encode(port.body.drives)}

def make_body(seed,budget):
    from .. import mechanical_v16 as old
    body=budget.call('model_build',old.new_body,seed,old.PROFILE)
    if (body.model.nq,body.model.nv,body.model.nu)!=(73,72,48):raise ValueError('accepted native dimensions changed')
    return body

def candidate(body,reg,budget):
    from ..contact_v1.native import bind_native,NativePort
    from ..contact_v1.law import Controller
    old=body.controllers[0]
    adapter=budget.call('bind_native',bind_native,body.model,old.preprogrammed_steps,
       expected_model_hash=reg['model_digest'],asset_hash=reg['asset_hash'],input_hash=reg['input_hash'])
    if not 0<len(adapter.bodies)<=68 or body.model.nbody!=69:raise ValueError('registered fly-body upper bound')
    if 'fly_body_count' in reg and len(adapter.bodies)!=reg['fly_body_count']:raise ValueError('frozen fly body count')
    c=Controller(adapter.binding,old.cpg_network.curr_phases.copy(),body.data.ctrl[adapter.indices].copy(),body.data.ctrl[42:].astype(bool),old.cpg_network.random_state.get_state())
    port=NativePort(body,adapter,c,reg['experiment_binding'])
    return port

def reset_record(body):
    from ..contact_v1.contracts import encode
    old=body.controllers[0]
    return {'qpos':encode(body.data.qpos.copy()),'qvel':encode(body.data.qvel.copy()),'ctrl':encode(body.data.ctrl.copy()),'integration':encode(integration(body)),
      'theta':encode(old.cpg_network.curr_phases.copy()),'magnitude':encode(old.cpg_network.curr_magnitudes.copy()),'rng':encode(old.cpg_network.random_state.get_state())}

def cache_export(data):
    arrays={}
    for name in dir(data):
        if name.startswith('_'):continue
        v=getattr(data,name)
        if isinstance(v,np.ndarray) and v.dtype.kind in 'fiub':arrays[name]=v.copy()
    for name in dir(data.contact):
        if name.startswith('_'):continue
        v=getattr(data.contact,name)
        if isinstance(v,np.ndarray) and v.dtype.kind in 'fiub':arrays['contact.'+name]=v.copy()
    return arrays

def export_checkpoint(dest,checkpoint):
    from ..contact_v1.contracts import encode
    dest=Path(dest);dest.mkdir(parents=True,exist_ok=False)
    with (dest/'native-numeric-cache.npz').open('xb') as f:np.savez_compressed(f,**cache_export(checkpoint['data']))
    account_existing(dest/'native-numeric-cache.npz')
    portable={k:encode(v) for k,v in checkpoint.items() if k!='data'}
    write(dest/'checkpoint.json',portable)
    write(dest/'manifest.json',{'files':{p.name:sha(p) for p in dest.iterdir() if p.is_file()},'live_MjData_required_for_native_restore':True,'crash_resumability_claimed':False})

def export_failure(dest,body,port,error,reg):
    """Full numeric checkpoint export without an extra checkpoint/restore call."""
    from ..contact_v1.contracts import encode,observation_state
    from ..contact_v1.native import native_cache_manifest
    dest=Path(dest);dest.mkdir(parents=True,exist_ok=False)
    with (dest/'native-numeric-cache.npz').open('xb') as f:np.savez_compressed(f,**cache_export(body.data))
    account_existing(dest/'native-numeric-cache.npz')
    frames=[];trace=error.__traceback__
    while trace is not None:
        frame=trace.tb_frame;name=frame.f_code.co_name
        if '/contact_v1/' in frame.f_code.co_filename:
            payload={'function':name,'line':trace.tb_lineno}
            for key in ('s','A','target','rhs','z','z_native','commands','next_native','lag','blocked','u'):
                if key in frame.f_locals:payload[key]=encode(frame.f_locals[key])
            if 'obs' in frame.f_locals:payload['observation']=encode(observation_state(frame.f_locals['obs']))
            frames.append(payload)
        trace=trace.tb_next
    write(dest/'payload.json',{'tick':body.tick,'integration':encode(integration(body)),'cache':native_cache_manifest(body.data),
      'science':science_state(port) if port else control_snapshot(body.controllers[0],{key:reg[key] for key in ('asset_hash','model_digest','input_hash')}),'rejected_call_frames':frames,'error':str(error)})

def preflight(root,anchor):
    root=Path(root);pre=validate(root)
    if anchor!=sha(root/'preregistration.json'):raise ValueError('preflight literal anchor mismatch')
    write(root/'preflight-start.json',{'anchor':anchor,'started':time.time()});budget=Budget(root,start=pre['created_unix']);budget.source_bytes=pre['source_bytes']
    for key in ('MPLCONFIGDIR','XDG_CACHE_HOME'):os.environ[key]=str(root/'cache'/key.lower())
    import mujoco as mj
    from ..contact_v1.native import model_digest,native_cache_manifest
    from ..contact_v1.contracts import encode
    from .geometry import static_preflight
    reset={};checks=[];model_hash=None
    try:
        if sha(pre['model_locator']['model_asset_path'])!=MODEL_SHA:raise ValueError('original MJB asset identity')
        with budget.native_guard():
            from ..contact_v1.native import native_cache_manifest
            for seed in (42,43,31042,31043):
                body=make_body(seed,budget);mh=model_digest(body.model)
                if model_hash is None:
                    model_hash=mh;mj.mj_saveModel(body.model,str(root/'model.mjb'));account_existing(root/'model.mjb')
                    if sha(root/'model.mjb')!=MODEL_SHA:raise ValueError('fresh native MJB does not match accepted model')
                elif model_hash!=mh:raise ValueError('seed model binding changed')
                reg={'model_digest':mh,'asset_hash':digest(pre['dependencies']),'input_hash':digest({'cases':pre['cases'],'active':[3000,25000],'dt':DT}),'experiment_binding':{'preregistration':anchor,'model':mh}}
                before=reset_record(body);port=candidate(body,reg,budget)
                budget.charge('static_neutral')
                neutral=port.adapter.angles(port.controller.state['phi'],np.zeros(6));budget.complete('static_neutral')
                if not np.array_equal(neutral,body.data.ctrl[port.adapter.indices]):raise ValueError('neutral anatomical conversion')
                if reset_record(body)!=before:raise ValueError('candidate initialization changed reset')
                reset[str(seed)]=before
                if seed==42:
                    result=static_preflight(body,port.adapter,budget)
                    checkpoint=budget.call('checkpoint',port.checkpoint);snapshot=science_state(port);cache=native_cache_manifest(body.data)
                    budget.call('restore',port.restore,checkpoint)
                    if science_state(port)!=snapshot or native_cache_manifest(body.data)!=cache or not np.array_equal(integration(body),checkpoint['integration']):raise ValueError('initial native restore mismatch')
                    export_checkpoint(root/'initial-checkpoint',checkpoint)
                    details={'binding':encode(port.adapter.binding.__dict__),'indices':port.adapter.indices.tolist(),'thorax':port.adapter.thorax,'bodies':list(port.adapter.bodies),'fly_body_count':len(port.adapter.bodies),
                      'legacy_controller':{'coupling':body.controllers[0]._base_coupling.tolist(),'phase_biases':body.controllers[0].cpg_network.phase_biases.tolist(),'release_end':body.controllers[0].release_end.tolist(),'allocation_joint_map':body.clearance_sensor.indices.tolist(),'swing_periods_strict_modulo':{leg:[0.,float(port.adapter.binding.beta[i])] for i,leg in enumerate(port.adapter.steps.legs)}}}
                    checks.append(result)
                write(root/f'reset-{seed}.json',before)
                budget.check()
            receipt={'passed':True,'checks':checks,'resources':budget.check(),'native_physics_calls':0,'accepted_intent_calls':0}
            write(root/'preflight-terminal.json',receipt)
            final={**reg,**details,'schema':'contact-mechanics-registration/v1','preregistration_sha256':anchor,'source_closure_sha256':sha(root/'source-closure.json'),'preflight_sha256':sha(root/'preflight-terminal.json'),'resets':{s:sha(root/f'reset-{s}.json') for s in reset},'model_sha256':MODEL_SHA,'ready':False,'attempt_start_unix':budget.start,'preflight_counts':budget.attempted,'preflight_completed':budget.completed,'preflight_timings':budget.timings}
            write(root/'registration.json',final)
        return {'registration_sha256':sha(root/'registration.json'),'preflight_passed':True,'ready':False}
    except BaseException as e:
        if not (root/'preflight-terminal.json').exists():write(root/'preflight-terminal.json',{'passed':False,'type':type(e).__name__,'message':str(e),'attempted':budget.attempted})
        raise
    finally:budget.persist('preflight-resources.json')

def capture_raw(body,binding,start):
    import mujoco as mj
    d=body.data;rows=[];owners={int(g):i for i,leg in enumerate(binding.foot_geoms) for g in leg}
    selected=[]
    for i in range(d.ncon):
        con=d.contact[i];g1=int(con.geom1);g2=int(con.geom2)
        if g1 in binding.fly_geoms and g2==binding.ground_geom:selected.append((i,g1,1))
        elif g2 in binding.fly_geoms and g1==binding.ground_geom:selected.append((i,g2,0))
    if len(selected)>512:raise ValueError('contact capacity no truncation')
    for index,geom,order in selected:
        con=d.contact[index];force=np.empty(6);mj.mj_contactForce(body.model,d,index,force)
        rows.append(pack(CONTACT,{'index':index,'geom':geom,'ground':binding.ground_geom,'leg':owners.get(geom,-1),'geom_order':order,'distance':con.dist,'point':con.pos,'frame':con.frame,'force':force,'interval_start':start,'interval_end':start+1}))
    return rows

def packet_rows(body,packet):
    result=[]
    for x in packet.rows:
        result.append(pack(CONTACT,{'index':x.index,'geom':x.geom,'ground':x.ground,'leg':x.leg,'geom_order':int(body.data.contact[x.index].geom1==x.geom),'distance':x.distance,'point':x.point,'frame':x.frame,'force':x.force,'interval_start':packet.tick,'interval_end':packet.tick+1}))
    return result

def legacy_state(body):
    from flygym_demo.complex_terrain.hybrid_controller import HybridControllerObservation
    c=body.controllers[0];obs=HybridControllerObservation.from_sim(body.sim,'fly-0')
    values={'thorax_position':body.data.xpos[body.body_ids[0]],'thorax_rotation':body.data.xmat[body.body_ids[0]],'targets':c.cpg_network.intrinsic_amps,'adhesion':body.data.ctrl[42:],
     'retraction':c.retraction_correction,'stumbling':c.stumbling_correction,'persistence':c.retraction_persistence_counter,'net_correction':c.last_info.get('net_corrections',np.zeros(6)),
     'sensed_clearance':c.last_clearance,'trigger_mask':c.last_trigger,'minimum_geom':c.last_minimum_geom,'minimum_vertex':c.last_minimum_vertex,
     'native_template':c.last_native_template,'native_observation':np.r_[obs.thorax_z,obs.tarsus5_z,obs.stumbling_contact_forces.ravel(),obs.fly_heading],
     'allocation':c.last_allocation,'allocation_diagnostics':c.last_allocation_diagnostics,'observation_tick':c.last_observation_tick,'relaxation_diagnostics':c.last_relaxation_diagnostics}
    return pack(LEGACY,values)

def safety(body,port):
    arrays=[body.data.qpos,body.data.qvel,body.data.qacc,body.data.qfrc_actuator,body.data.actuator_force,body.data.ctrl]
    if port is not None:arrays.extend((port.controller.state['theta'],port.controller.state['magnitude']))
    else:
        c=body.controllers[0];arrays.extend((c.cpg_network.curr_phases,c.cpg_network.curr_magnitudes,c.retraction_correction,c.stumbling_correction,c.retraction_persistence_counter))
    if not all(np.isfinite(x).all() for x in arrays) or np.max(np.abs(body.data.qvel))>1e6:raise FloatingPointError('unsafe native state')
    if abs(body.data.time-body.tick*DT)>1e-9:raise ValueError('native clock')

def core_row(body,port,u,count,offset):
    c=body.controllers[0]
    theta=c.cpg_network.curr_phases if port is None else port.controller.state['theta'];r=c.cpg_network.curr_magnitudes if port is None else port.controller.state['magnitude']
    obs=c.last_observation_tick if port is None else port.controller.state['last_tick']
    return pack(CORE,{'qpos':body.data.qpos,'qvel':body.data.qvel,'ctrl':body.data.ctrl,'force':body.data.actuator_force,'input':u,'theta':theta,'magnitude':r,'time':body.data.time,'action_tick':body.tick-1,'observation_tick':obs,'interval_present':body.tick>0,'contact_offset':offset,'contact_count':count})

def step(body,port,u,binding,budget):
    if port is None:
        from ..mechanical_v16 import step as old_step
        oldq=body.data.qpos.copy();oldv=body.data.qvel.copy();start=body.tick
        if np.mean(u)>1e-4:budget.charge('control_active')
        old_step(body,u)
        if np.mean(u)>1e-4:budget.complete('control_active')
        rows=capture_raw(body,binding,start)
    else:
        if np.mean(u)>1e-4:budget.charge('candidate_active');budget.charge('candidate_propose')
        prepared=port.prepare(u)
        if np.mean(u)>1e-4:budget.complete('candidate_propose')
        port.apply(prepared)
        if np.mean(u)>1e-4:budget.complete('candidate_active')
        body.drives[0]=u;saved=port.record_pre_step()
        body.sim.step();body.tick+=1
        packet=port.adapter.capture_completed(body.data,saved['qpos'],saved['qvel'],saved['tick']);port.record_completed(packet);rows=packet_rows(body,packet)
    safety(body,port);return rows

def sample(port,core,state,rows,budget):
    from ..contact_v1.native import native_cache_manifest
    from ..contact_v1.contracts import encode
    return {'core':encode(core),'state':encode(state),'contacts':encode(np.asarray(rows,dtype=float).reshape(-1,width(CONTACT))),'integration':encode(integration(port.body)),
      'native_cache':native_cache_manifest(port.body.data),'science':science_state(port)}

def run_trial(root,trial,reg,budget,restoration):
    from ..contact_v1.contracts import Binding,decode,encode
    from ..contact_v1.native import model_digest
    root=Path(root);dest=root/trial.stage/trial.name
    body=port=writers=None;error=None;kind=None;failing=None;secondary=[];setup_failed=True;started=time.monotonic()
    try:
        validate(root,final=True);body=make_body(trial.seed,budget)
        if model_digest(body.model)!=reg['model_digest']:raise ValueError('trial compiled model identity')
        if sha(root/f'reset-{trial.seed}.json')!=reg['resets'][str(trial.seed)] or reset_record(body)!=read(root/f'reset-{trial.seed}.json'):raise ValueError('trial reset identity')
        port=candidate(body,reg,budget) if trial.profile==PROFILE else None;binding=Binding(**decode(reg['binding']))
        writers=Writers(dest,trial,sha(root/'registration.json'),budget,metadata=metadata(root,trial,reg))
        initial=port.controller.checkpoint() if port is not None else control_snapshot(body.controllers[0],{key:reg[key] for key in ('asset_hash','model_digest','input_hash')})
        write(dest/'initial-controller.json',initial)
        setup_failed=False;budget.forecast('setup',time.monotonic()-started,1,budget.future_trials)
        blockstart=time.monotonic();lastblock=0
        writers.append(0,core_row(body,port,np.zeros(2),0,0),candidate_row(port.controller.state) if port else legacy_state(body),[])
        for k in range(40000):
            if k%100==0:budget.check()
            u=waveform(trial.case,k);rows=step(body,port,u,binding,budget);core=core_row(body,port,u,len(rows),writers.contact_offset);state=candidate_row(port.controller.state) if port else legacy_state(body)
            writers.append(k+1,core,state,rows)
            if trial.stage=='development' and trial.profile==PROFILE and trial.seed==42 and trial.case[0]=='straight-02':
                if body.tick==10000:
                    cp=budget.call('checkpoint',port.checkpoint);restoration.update(checkpoint=cp,expected=[],origin_model=body.model,source_trial=trial.identity);export_checkpoint(root/'active-checkpoint',cp)
                elif 10000<body.tick<=10100:
                    reference=sample(port,core,state,rows,budget);restoration['expected'].append(reference);write(root/'active-reference'/f'{body.tick}.json',reference)
            if (k+1)%1000==0 or (k+1==3100 and trial.profile==PROFILE and trial.case[1]>0):
                elapsed=time.monotonic()-blockstart;budget.forecast('runtime:'+trial.profile,elapsed,k+1-lastblock,40000-(k+1)+budget.future_runtime);budget.forecast_bytes(k+1-lastblock,40000-(k+1)+budget.future_reconstruction);blockstart=time.monotonic();lastblock=k+1
    except BaseException as exc:
        error=exc;kind=classify(exc,trial.profile);budget.finalizing=True
        if body is not None:
            failing=np.r_[body.tick,body.data.qpos,body.data.qvel,body.data.qacc,body.data.qfrc_actuator,body.data.ctrl,body.data.actuator_force]
            try:
                export_failure(dest/'failure-checkpoint',body,port,exc,reg)
                if port:write(dest/'rejected-state.json',{'action_tick':body.tick,'input':waveform(trial.case,body.tick).tolist(),'state':science_state(port),'error':str(exc)})
            except BaseException as retain:secondary.append({'stage':'failure_snapshot','type':type(retain).__name__,'message':str(retain)})
    completed=body.tick if body is not None else 0
    extra={'scheduled_ticks':40000,'completed_ticks':completed,'missing_remainder':40000-completed,'failure_kind':kind,
      'profile':trial.profile,'registration_sha256':sha(root/'registration.json'),'setup_failed':setup_failed,'secondary_failures':secondary}
    try:
        if writers is not None:
            terminal=writers.finish(error,extra,failing)
        elif not (dest/'trial-terminal.json').exists():
            write(dest/'trial-terminal.json',{**extra,'schema':'contact-mechanics-trial-terminal/v2','trial_id':trial.identity,'complete':False,
              'failure':{'type':type(error).__name__,'message':str(error)},'primary_failure_kind':kind,'failure_kind':'retention','retention_passed':False,
              'retention_failures':[{'stage':'setup','message':'no initialized evidence streams'}], 'streams':{},'retained_rows':{}})
        if secondary:raise RetentionError('failure snapshot retention failed: '+str(secondary)) from error
    finally:budget.finalizing=False
    if error is not None and kind!='controller_infeasible':raise error
    return {'trial':trial,'body':body,'port':port,'complete':error is None,'failure_kind':kind,'ticks':completed}

def compare_repeat(root,trial):
    from .io import stream_rows
    held=Path(root)/'heldout'/trial.name;repeat=Path(root)/'repeat'/trial.name
    for name,schema in (('core',CORE),('state',CANDIDATE),('contacts',CONTACT)):
        left=iter(stream_rows(held/name,schema));right=iter(stream_rows(repeat/name,schema));index=0
        while True:
            a=next(left,None);b=next(right,None)
            if a is None or b is None:
                if a is not None or b is not None:raise ValueError('repeat length '+name)
                break
            if a[0]!=b[0] or not np.array_equal(a[1],b[1]):
                write(repeat/'repeat-first-mismatch.json',{'stream':name,'row':index,'left_tick':a[0],'right_tick':b[0]});raise ValueError('repeat bitwise mismatch')
            index+=1
    write(repeat/'repeat-verification.json',{'passed':True,'compared':['core','state','contacts'],'ready':False})

def restore_test(root,destination,restoration,reg,budget):
    from ..contact_v1.contracts import encode,decode
    from .geometry import Geometry,prepare
    from .verify import DERIVED,Reference,candidate_state
    from .oracle import verify_candidate
    from .io import stream_rows,BudgetEvidence
    import mujoco as mj
    setup_started=time.monotonic()
    port=destination['port'];body=port.body;cp=restoration['checkpoint'];expected=restoration['expected']
    if len(expected)!=100:raise ValueError('missing natural checkpoint reference')
    dest=Path(root)/'restoration';dest.mkdir(exist_ok=False)
    write(dest/'binding.json',{'source_trial':restoration['source_trial'],'source_tick':10000,'destination_trial':destination['trial'].identity,'destination_tick':40000,'experiment_binding':reg['experiment_binding']})
    body.data.qpos[0]+=1;body.data.qvel[0]+=1;body.data.ctrl[0]+=1;port.controller.state['theta'][0]+=1;body.tick+=7;body.drives[:]=0
    budget.call('restore',port.restore,cp)
    if body.tick!=10000 or not np.array_equal(integration(body),cp['integration']):raise ValueError('immediate restoration equality')
    errors=[];offset=unpack(CORE,decode(expected[0]['core']))['contact_offset'][0]
    source=Path(root)/restoration['source_trial'];derived_reference={tick:row for tick,row in stream_rows(source/'derived',DERIVED) if 10001<=tick<=10100}
    if len(derived_reference)!=100:raise ValueError('missing independent physical reference')
    geometry=Geometry(body.model,port.adapter.binding,reg['thorax'],reg['bodies']);reference=Reference(geometry,port.adapter.steps)
    current=mj.MjData(body.model);prior=mj.MjData(body.model)
    packet=port.recorder_state['completed_interval'];prepare(body.model,prior,packet['qpos'],packet['qvel']);prepare(body.model,current,body.data.qpos,body.data.qvel)
    endpoint=geometry.endpoint(current,jacobians=True)
    from ..contact_v1.native import interval_from_state
    previous_rows=packet_rows(body,interval_from_state(packet))
    retained=[]
    budget.forecast('restore_setup',time.monotonic()-setup_started,1,0)
    budget.remaining['reconstruction']=100;budget.check_projection()
    for index in range(100):
        reconstruction_started=time.monotonic()
        if index%100==0:budget.check()
        before_core=core_row(body,port,np.array([.2,.2]),len(previous_rows),offset-len(previous_rows));before_state=candidate_row(port.controller.state)
        observation=geometry.observation(current,prior,endpoint,previous_rows,body.tick,body.data.actuator_force.copy())
        reconstruction_seconds=time.monotonic()-reconstruction_started;runtime_started=time.monotonic()
        rows=step(body,port,np.array([.2,.2]),port.adapter.binding,budget)
        core=core_row(body,port,np.array([.2,.2]),len(rows),offset);state=candidate_row(port.controller.state);actual=sample(port,core,state,rows,budget)
        runtime_seconds=time.monotonic()-runtime_started;reconstruction_started=time.monotonic()
        if actual!=expected[index]:
            write(dest/'first-mismatch.json',{'index':index,'actual':actual,'expected':expected[index]});raise ValueError('restoration bitwise continuation mismatch')
        budget.charge('independent_candidate');verify_candidate(candidate_state(before_core,before_state,port.adapter.indices),candidate_state(core,state,port.adapter.indices),observation,np.array([.2,.2]),port.adapter.binding,reference);budget.complete('independent_candidate')
        prior,current=current,prior;prepare(body.model,current,body.data.qpos,body.data.qvel);endpoint=geometry.endpoint(current,jacobians=index<99)
        normal,weighted,peak,error=geometry.interval_metrics(prior,rows,prior.qvel)
        derived=pack(DERIVED,{'height':endpoint.height,'distal':endpoint.distal,'ap':endpoint.ap,'position':endpoint.thorax_pos,'rotation':endpoint.thorax_rotation,'normal':normal,'weighted':weighted,'peak':peak})
        if not np.array_equal(derived,derived_reference[10001+index]):
            write(dest/'derived-first-mismatch.json',{'tick':body.tick,'actual':encode(derived),'expected':encode(derived_reference[10001+index])});raise ValueError('independent restored physical data mismatch')
        retained.append(derived);previous_rows=rows
        write(dest/f'actual-{index:03d}.json',actual);offset+=len(rows)
        budget.forecast('runtime:'+PROFILE,runtime_seconds,1,99-index)
        budget.forecast('reconstruction',reconstruction_seconds+time.monotonic()-reconstruction_started,1,99-index)
    finalization_started=time.monotonic()
    with (dest/'derived.npz').open('xb') as handle:np.savez_compressed(handle,ticks=np.arange(10001,10101,dtype=np.int64),values=np.asarray(retained))
    account_existing(dest/'derived.npz')
    write(dest/'verification.json',{'passed':True,'ticks':100,'native_cache_integration_science_raw_exact':True,'independently_derived_physical_bitwise':True,'independent_actions_checked':100,'source_destination_seeds_differ':True,'ready':False})
    budget.note_finalization(time.monotonic()-finalization_started);budget.forecast('restore_finalization',time.monotonic()-finalization_started,1,0)

def remaining_work(trials):
    values={'runtime:'+CONTROL:0,'runtime:'+PROFILE:0,'reconstruction':0,'setup':0,'analysis_finalization':0}
    for trial in trials:
        values['runtime:'+trial.profile]+=40000;values['reconstruction']+=40001;values['setup']+=1;values['analysis_finalization']+=1
    return values

def run(root,anchor):
    root=Path(root);reg=validate(root,final=True)
    if anchor!=sha(root/'registration.json'):raise ValueError('execution anchor')
    write(root/'execution-start.json',{'registration_sha256':anchor,'started':time.time()})
    for key in ('MPLCONFIGDIR','XDG_CACHE_HOME'):os.environ[key]=str(root/'cache'/key.lower())
    from ..contact_v1.native import model_digest
    from ..contact_v1.contracts import decode
    from flygym_demo.complex_terrain.preprogrammed import PreprogrammedSteps
    from .verify import verify_trial,panel_admission
    import mujoco as mj
    budget=Budget(root,start=reg['attempt_start_unix']);budget.stage='execution';budget.source_bytes=read(root/'preregistration.json')['source_bytes'];budget.attempted=reg['preflight_counts'].copy();budget.completed=reg['preflight_completed'].copy();budget.timings=deepcopy(reg['preflight_timings'])
    alltrials=[t for stage in ('development','heldout','repeat') for t in panel(stage)];status={t.identity:{'status':'blocked_conditional' if t.stage!='development' else 'scheduled'} for t in alltrials};restoration={};error=None;decisions={}
    try:
        with budget.native_guard():
            model=budget.call('model_load',mj.MjModel.from_binary_path,str(root/'model.mjb'))
            if model_digest(model)!=reg['model_digest']:raise ValueError('verification model digest')
            steps=PreprogrammedSteps()
            for stage in ('development','heldout'):
                reports={}
                stage_trials=panel(stage)
                for trial_index,trial in enumerate(stage_trials):
                    budget.future_runtime=40000*sum(t.profile==trial.profile for t in stage_trials[trial_index+1:]);budget.future_reconstruction=40001*len(stage_trials[trial_index+1:]);budget.future_trials=len(stage_trials)-trial_index-1
                    budget.set_remaining(remaining_work(stage_trials[trial_index:]))
                    budget.current=trial.identity;status[trial.identity]={'status':'started'};budget.check();outcome=run_trial(root,trial,reg,budget,restoration)
                    remaining=remaining_work(stage_trials[trial_index+1:]);remaining['reconstruction']+=outcome['ticks']+1;remaining['analysis_finalization']+=1;budget.set_remaining(remaining)
                    report=verify_trial(root,trial,reg,budget,model,steps);reports[trial.identity]=report
                    status[trial.identity]={'status':'complete' if outcome['complete'] else 'failed_incomplete','failure_kind':outcome['failure_kind'],'ticks':outcome['ticks'],'candidate_passed':report.get('candidate_passed',False)}
                decision=panel_admission(reports,stage);decisions[stage]=decision;write(root/f'{stage}-admission.json',decision)
                if not decision['passed']:break
            else:
                trial=panel('repeat')[0];budget.future_runtime=100;budget.future_reconstruction=101;budget.future_trials=0;work=remaining_work([trial]);work['runtime:'+PROFILE]+=100;work['reconstruction']+=101;work.update(repeat_compare=1,restore_setup=1,restore_finalization=1);budget.set_remaining(work);budget.current=trial.identity;status[trial.identity]={'status':'started'};outcome=run_trial(root,trial,reg,budget,restoration);budget.remaining['runtime:'+PROFILE]=100;budget.remaining['setup']=0
                report=verify_trial(root,trial,reg,budget,model,steps)
                status[trial.identity]={'status':'complete' if outcome['complete'] else 'failed_incomplete','ticks':outcome['ticks'],'candidate_passed':report.get('candidate_passed',False)}
                if not outcome['complete'] or not report['candidate_passed']:raise ValueError('repeat incomplete/failed')
                compare_started=time.monotonic();compare_repeat(root,trial);budget.forecast('repeat_compare',time.monotonic()-compare_started,1,0)
                if 'checkpoint' not in restoration:raise ValueError('active reference checkpoint absent')
                restore_test(root,outcome,restoration,reg,budget)
            return {'development_passed':decisions.get('development',{}).get('passed',False),'heldout_passed':decisions.get('heldout',{}).get('passed',False),'restoration_passed':(root/'restoration/verification.json').exists(),'ready':False}
    except BaseException as exc:error=exc;raise
    finally:
        final_error=None if error is None else {'type':type(error).__name__,'message':str(error)}
        for t in alltrials:
            path=root/t.stage/t.name/'trial-terminal.json'
            if status[t.identity]['status'] in ('scheduled','started') and path.exists():
                record=read(path);status[t.identity]={'status':'stopped','ticks':record.get('completed_ticks'),'failure_kind':record.get('failure_kind') or (classify(error,t.profile) if error else 'integration')}
            elif status[t.identity]['status']=='started':status[t.identity]={'status':'stopped_before_evidence','failure_kind':classify(error,t.profile) if error else 'integration'}
            elif status[t.identity]['status']=='scheduled' and error is not None:status[t.identity]={'status':'unstarted_due_stop'}
        write(root/'panel-terminal.json',{'registration_sha256':anchor,'trials':status,'error':final_error,'ready':False,'full_goal_complete':False,'physics_attempted':budget.attempted.get('mj_step',0)})
        budget.persist()
        write(root/'output-inventory.json',{str(p.relative_to(root)):sha(p) for p in sorted(root.rglob('*')) if p.is_file()})
