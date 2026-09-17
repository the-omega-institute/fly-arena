"""Versioned saved traversal closure. Hashes bind evidence, not its authenticity."""
from pathlib import Path
import numpy as np
from .io import read,write,sha,digest
from .schema import *
SEAL_SCHEMA='contact-mechanics-native-verification/v2'
SEAL_FILES=('core/terminal.json','state/terminal.json','contacts/terminal.json','derived/terminal.json','analysis-verification.json','trial-terminal.json')
STREAMS=('core','state','contacts','derived')
CONTEXT_KEYS=('registration_sha256','preregistration_sha256','source_closure_sha256','reset_sha256')
SEAL_KEYS={'schema','trial','context','files','stream_starts','initial_controller_sha256','single_native_reconstruction','coverage'}

def registration_context(root):
    from .registration import SOURCE,protocol
    root=Path(root);reg=read(root/'registration.json');pre=read(root/'preregistration.json');closure=read(root/'source-closure.json')
    if reg.get('schema')!='contact-mechanics-registration/v1' or pre.get('schema')!='contact-mechanics-preregistration/v1':raise ValueError('saved registration schema')
    if reg.get('preregistration_sha256')!=sha(root/'preregistration.json') or reg.get('source_closure_sha256')!=sha(root/'source-closure.json'):raise ValueError('saved preregistration/source anchor')
    if any(pre.get(key)!=value for key,value in protocol().items()):raise ValueError('saved registered schedule/schema/limits')
    if not isinstance(closure,dict) or not closure or closure!=pre.get('source') or Path(pre.get('source_root','')).resolve()!=SOURCE.resolve():raise ValueError('saved source closure identity')
    required=set(read(SOURCE/'docs/contact-mechanics-v1/accepted-source-manifest.json'))
    required.update(str(p.relative_to(SOURCE)) for p in (SOURCE/'src/flyarena/experiments/contact_mechanics_v1').glob('*.py'))
    if not required<=set(closure):raise ValueError('saved source closure missing mandatory payloads')
    for path,h in closure.items():
        p=SOURCE/path
        if not p.resolve().is_relative_to(SOURCE.resolve()) or sha(p)!=h:raise ValueError('saved source changed: '+path)
    if reg.get('model_sha256')!=MODEL_SHA or pre.get('model_locator',{}).get('registered_model_mjb_sha256')!=MODEL_SHA:raise ValueError('saved model identity')
    if reg.get('preflight_sha256')!=sha(root/'preflight-terminal.json') or read(root/'preflight-terminal.json').get('passed') is not True:raise ValueError('saved preflight identity')
    if pre.get('plan_sha256')!=sha(root/'approved-plan.md') or pre.get('plan_sha256')!=sha(SOURCE/'docs/contact-mechanics-v1/approved-plan.md'):raise ValueError('saved plan identity')
    from ..contact_v1.contracts import Binding,decode
    binding=Binding(**decode(reg['binding']));binding.validate()
    if (binding.model_hash,binding.asset_hash,binding.input_hash)!=(reg.get('model_digest'),reg.get('asset_hash'),reg.get('input_hash')):raise ValueError('saved compiled binding identity')
    if reg.get('experiment_binding')!={'preregistration':sha(root/'preregistration.json'),'model':reg.get('model_digest')}:raise ValueError('saved experiment binding')
    if reg.get('asset_hash')!=digest(pre.get('dependencies')) or reg.get('input_hash')!=digest({'cases':pre['cases'],'active':[3000,25000],'dt':DT}):raise ValueError('saved dependency/input identity')
    if set(reg.get('resets',{}))!={'42','43','31042','31043'}:raise ValueError('saved reset denominator')
    for seed,h in reg['resets'].items():
        if sha(root/f'reset-{seed}.json')!=h:raise ValueError('saved reset changed')
    return reg,pre

def context(root,trial,reg):
    root=Path(root)
    return {'registration_sha256':sha(root/'registration.json'),'preregistration_sha256':reg['preregistration_sha256'],
      'source_closure_sha256':reg['source_closure_sha256'],'reset_sha256':reg['resets'][str(trial.seed)]}
def metadata(root,trial,reg):return {**trial.record(),**context(root,trial,reg)}
def active_actions(trial,completed):return max(0,min(completed,25000)-3000) if trial.case[1]>0 else 0

def check_terminal(terminal,trial):
    if terminal.get('schema')!='contact-mechanics-trial-terminal/v2' or terminal.get('trial_id')!=trial.identity:raise ValueError('trial terminal schema/identity')
    for key in ('completed_ticks','scheduled_ticks','missing_remainder'):
        if type(terminal.get(key)) is not int:raise ValueError('trial terminal integer domain')
    n=terminal['completed_ticks']
    if not 0<=n<=40000 or terminal['scheduled_ticks']!=40000 or terminal['missing_remainder']!=40000-n:raise ValueError('trial full denominator')
    if not isinstance(terminal.get('retention_failures'),list):raise ValueError('trial retention failures domain')
    if type(terminal.get('complete')) is not bool or type(terminal.get('retention_passed')) is not bool:raise ValueError('trial terminal flags')
    if terminal['retention_passed']!= (not terminal.get('retention_failures')):raise ValueError('retention flag disagreement')
    if terminal['complete'] and (n!=40000 or terminal.get('failure') is not None or terminal.get('failure_kind') is not None or not terminal['retention_passed']):raise ValueError('contradictory trial completion')
    if not terminal['complete'] and terminal.get('failure_kind') not in ('controller_infeasible','integration','unsafe','resource','retention'):raise ValueError('failed trial classification')
    if not terminal['complete'] and terminal.get('failure') is None and not terminal['retention_failures']:raise ValueError('failed terminal lacks failure evidence')
    return n+1

def validate_stream_terminals(dest,terminal,rows,contacts):
    expected_counts={'core':rows,'state':rows,'contacts':contacts,'derived':rows}
    keys={'schema','complete','primary_failure','retention_failures','initialized_rows','files','wall_seconds','extra'}
    for name in STREAMS:
        t=read(dest/name/'terminal.json')
        if set(t)!=keys or t['schema']!='numeric-evidence-terminal/v10' or type(t['complete']) is not bool:raise ValueError('numeric terminal schema')
        if t['retention_failures'] or t['initialized_rows']!=expected_counts[name]:raise ValueError('incomplete retained numeric closure')
        if name=='derived':
            if not t['complete'] or t['primary_failure'] is not None:raise ValueError('incomplete reconstruction stream')
        else:
            if t!=terminal['streams'].get(name) or t['complete']!=terminal['complete']:raise ValueError('parent/child terminal disagreement')
            if (t['primary_failure'] is None)!=terminal['complete']:raise ValueError('child primary failure disagreement')
    if terminal.get('retained_rows')!={k:expected_counts[k] for k in ('core','state','contacts')}:raise ValueError('trial retained row accounting')

def check_core(trial,tick,core,state,offset,contact_count):
    c=unpack(CORE,core)
    for key in ('action_tick','observation_tick','interval_present','contact_offset','contact_count'):
        if np.any(c[key]!=np.floor(c[key])) or np.any(np.abs(c[key])>2**53):raise ValueError('fractional/out-of-domain physical clock')
    observation=min(tick-1,24999) if trial.case[1]>0 and tick>3000 else -1
    if (abs(c['time'][0]-tick*DT)>1e-9 or c['action_tick'][0]!=tick-1 or c['observation_tick'][0]!=observation
        or c['interval_present'][0]!=int(tick>0) or c['contact_offset'][0]!=offset or c['contact_count'][0]!=contact_count):raise ValueError('physical/action/observation/interval clock')
    expected=waveform(trial.case,tick-1) if tick else np.zeros(2)
    if not np.array_equal(c['input'],expected):raise ValueError('registered waveform')
    if trial.profile==PROFILE:
        value=state_from_rows(core,state)
        if value['last_tick']!=observation or value['generation']!=active_actions(trial,tick) or value['initialized']!=(observation>=0):raise ValueError('candidate state clock')
    else:
        value=unpack(LEGACY,state)
        if value['observation_tick'][0]!=observation:raise ValueError('control state clock')
        for key in ('persistence','minimum_geom','minimum_vertex'):
            if np.any(value[key]!=np.floor(value[key])) or np.any(value[key]<(-1 if key.startswith('minimum_') else 0)) or np.any(np.abs(value[key])>2**53):raise ValueError('control integer domain')
        for key in ('adhesion','trigger_mask'):
            if np.any((value[key]!=0)&(value[key]!=1)):raise ValueError('control Boolean domain')
    return c

def validate_reset_row(root,trial,core,state=None,reg=None):
    from ..contact_v1.contracts import decode
    reset=decode(read(Path(root)/f'reset-{trial.seed}.json'));c=unpack(CORE,core)
    for name in ('qpos','qvel','ctrl','theta','magnitude'):
        if not np.array_equal(c[name],reset[name]):raise ValueError('saved reset/core mismatch: '+name)
    if state is not None and reg is not None:
        initial=read(Path(root)/trial.stage/trial.name/'initial-controller.json')
        if trial.profile==PROFILE:
            from ..contact_v1.contracts import Binding,STATE_VERSION
            if set(initial)!={'version','binding','state'} or initial['version']!=STATE_VERSION or initial['binding']!=Binding(**decode(reg['binding'])).token():raise ValueError('initial candidate binding/schema')
            value=decode(initial['state'])
            if not np.array_equal(candidate_row(value),state) or not np.array_equal(value['theta'],c['theta']) or not np.array_equal(value['magnitude'],c['magnitude']):raise ValueError('initial candidate numeric state')
        else:
            if initial.get('schema')!='contact-mechanics-v16-numeric-state/v1' or initial.get('reference_identity')!={k:reg[k] for k in ('asset_hash','model_digest','input_hash')} or initial.get('reference_sha256')!=digest(initial.get('reference')) or initial.get('portable_native_restore') is not False:raise ValueError('initial control numeric identity')
            cpg=decode(initial['cpg'])
            if not np.array_equal(cpg['curr_phases'],c['theta']) or not np.array_equal(cpg['curr_magnitudes'],c['magnitude']):raise ValueError('initial control numeric state')

def write_seal(root,trial,reg,result):
    dest=Path(root)/trial.stage/trial.name
    coverage={k:result[k] for k in ('endpoint_rows_checked','contacts_checked','active_actions_checked')}
    seal={'schema':SEAL_SCHEMA,'trial':trial.record(),'context':context(root,trial,reg),
      'files':{name:sha(dest/name) for name in SEAL_FILES},'stream_starts':{name:sha(dest/name/'start.json') for name in STREAMS},
      'initial_controller_sha256':sha(dest/'initial-controller.json'),'single_native_reconstruction':True,'coverage':coverage}
    write(dest/'numeric-verification-seal.json',seal)

def validate_seal(root,trial,reg,terminal,rows,contacts):
    dest=Path(root)/trial.stage/trial.name;seal=read(dest/'numeric-verification-seal.json')
    if set(seal)!=SEAL_KEYS or seal['schema']!=SEAL_SCHEMA or seal['single_native_reconstruction'] is not True:raise ValueError('native seal schema/pass marker')
    if seal['trial']!=trial.record() or seal['context']!=context(root,trial,reg):raise ValueError('native seal registration/trial/reset/source identity')
    if set(seal['files'])!=set(SEAL_FILES) or set(seal['stream_starts'])!=set(STREAMS):raise ValueError('native seal exact file set')
    for name,h in seal['files'].items():
        if sha(dest/name)!=h:raise ValueError('native seal evidence changed')
    for name,h in seal['stream_starts'].items():
        if sha(dest/name/'start.json')!=h or read(dest/name/'start.json')!=metadata(root,trial,reg):raise ValueError('native seal stream start identity')
    if sha(dest/'initial-controller.json')!=seal['initial_controller_sha256']:raise ValueError('initial controller identity')
    if terminal.get('registration_sha256')!=sha(Path(root)/'registration.json'):raise ValueError('trial final registration identity')
    if not terminal['retention_passed']:raise ValueError('native seal lacks retention closure')
    validate_stream_terminals(dest,terminal,rows,contacts)
    expected={'endpoint_rows_checked':rows,'contacts_checked':contacts,'active_actions_checked':active_actions(trial,terminal['completed_ticks'])}
    if seal['coverage']!=expected or any(type(v) is not int or v<0 for v in seal['coverage'].values()):raise ValueError('native verification coverage')
    saved=read(dest/'analysis-verification.json')
    if saved.get('trial_id')!=trial.identity or saved.get('independent_numeric_pass') is not True or saved.get('integration_passed') is not True or saved.get('retention_passed') is not True:raise ValueError('native saved verification status')
    if any(saved.get(k)!=v for k,v in expected.items()):raise ValueError('saved verification coverage mismatch')
    return saved
