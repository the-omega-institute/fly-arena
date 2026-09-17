"""Exact numeric wire schemas and fixed trial identities (pure)."""
from dataclasses import dataclass
import numpy as np
from . import PROFILE, CONTROL
DT=.0001
TOL=5e-12
MODEL_SHA='c84909b93a562b21c045466499187b964af92530c88ac9e627867a689d7819d2'
CASES=(('zero',0.,0.),('straight-008',.08,0.),('straight-02',.2,0.),('straight-04',.4,0.),
 ('turn-negative-04',.2,-.4),('turn-positive-04',.2,.4),('turn-negative-08',.2,-.8),('turn-positive-08',.2,.8))
MODES=('SUPPORT','RELEASE_WAIT','LIFT','TRANSFER','LAND','REACQUIRE')
CORE=(('qpos',73),('qvel',72),('ctrl',48),('force',48),('input',2),('theta',6),('magnitude',6),
 ('time',1),('action_tick',1),('observation_tick',1),('interval_present',1),('contact_offset',1),('contact_count',1))
CONTACT=(('index',1),('geom',1),('ground',1),('leg',1),('geom_order',1),('distance',1),('point',3),('frame',9),('force',6),('interval_start',1),('interval_end',1))
CANDIDATE=tuple((key,6) for key in ('phi','modes','resume_modes','cycle','partial','clear_count','load_count','distal_count','wait_count','ap0','lateral0','release_height','release_magnitude','excursion','transfer_start','total_force','distal_force'))+(
 ('landing_xy',12),('native_reference',42),('correction',42),('z0',1),('initialized',1),('last_tick',1),('generation',1),
 ('body_velocity',3),('body_omega',3),('capture_point',2),('admitted',6),('release_veto',1),('positive_nonfoot',1),('phase_increment',6),('lag',6),('z',42),('residual_norm',6),('residual_max',6),
 ('requested_increment',42),('limited_increment',42),('before_ball',42),('after_ball',42),('range_flags',42))
# No shared physical duplication; fields required by the unchanged v16 verifier.
LEGACY=(('thorax_position',3),('thorax_rotation',9),('targets',6),('adhesion',6),('retraction',6),('stumbling',6),('persistence',6),('net_correction',6),('sensed_clearance',6),('trigger_mask',6),('minimum_geom',6),('minimum_vertex',6),('native_template',42),('native_observation',64),('allocation',42),('allocation_diagnostics',48),('observation_tick',1),('relaxation_diagnostics',30))
def slices(schema):
    result={}; n=0
    for key,size in schema: result[key]=slice(n,n+size); n+=size
    return result
def width(schema): return sum(n for _,n in schema)
def pack(schema,values):
    arrays=[np.asarray(values[k],dtype=np.float64).reshape(-1) for k,_ in schema]
    if any(len(a)!=n for a,(_,n) in zip(arrays,schema)):raise ValueError('per-field evidence width')
    row=np.concatenate(arrays)
    if row.shape!=(width(schema),) or not np.isfinite(row).all(): raise ValueError('nonfinite/schema evidence row')
    return row
def unpack(schema,row):
    row=np.asarray(row)
    if row.shape!=(width(schema),) or row.dtype!=np.float64 or not np.isfinite(row).all(): raise ValueError('invalid numeric row')
    return {k:row[s].copy() for k,s in slices(schema).items()}
@dataclass(frozen=True)
class Trial:
    stage:str
    profile:str
    seed:int
    case:tuple
    @property
    def name(self): return f'{self.profile}--{self.seed}--{self.case[0]}'
    @property
    def identity(self): return f'{self.stage}/{self.name}'
    def record(self): return dict(stage=self.stage,profile=self.profile,seed=self.seed,case=list(self.case),id=self.identity)
def panel(stage):
    if stage=='development': return [Trial(stage,p,s,c) for s in (42,43) for c in CASES for p in (CONTROL,PROFILE)]
    if stage=='heldout': return [Trial(stage,PROFILE,s,c) for s in (31042,31043) for c in CASES]
    if stage=='repeat': return [Trial(stage,PROFILE,31042,CASES[2])]
    raise ValueError('unknown stage')
def waveform(case,k):
    _,c,a=case
    return np.array([c*(1-a),c*(1+a)],dtype=np.float64) if 3000<=k<25000 else np.zeros(2)
def candidate_row(state):
    required={'phi','modes','resume_modes','cycle','partial','clear_count','load_count','distal_count','wait_count','ap0','lateral0','release_height','release_magnitude','excursion','transfer_start','total_force','distal_force','landing_xy','native_reference','correction','z0','initialized','last_tick','generation','diagnostics'}
    if not required<=set(state):raise ValueError('missing candidate state fields')
    d=state['diagnostics']; value={k:state[k] for k,_ in CANDIDATE if k in state}
    for k in ('modes','resume_modes'): value[k]=[MODES.index(x) for x in state[k]]
    value['z0']=0. if state['z0'] is None else state['z0']
    for k,n in CANDIDATE:
        if k not in value: value[k]=np.zeros(n)
    if state['initialized'] and not d: raise ValueError('missing initialized diagnostics')
    if d:
        for k in ('body_velocity','body_omega','capture_point','release_veto','positive_nonfoot','phase_increment','lag'): value[k]=d[k]
        value['admitted']=np.array([i in d['admitted'] for i in range(6)])
        for k in ('z','requested_increment','limited_increment','before_ball','after_ball','range_flags'): value[k]=np.array([leg[k] for leg in d['legs']])
        value['residual_norm']=[np.linalg.norm(leg['residual']) for leg in d['legs']]
        value['residual_max']=[np.max(np.abs(leg['residual']),initial=0.) for leg in d['legs']]
    return pack(CANDIDATE,value)
def state_from_rows(core,row):
    c=unpack(CORE,core); s=unpack(CANDIDATE,row)
    for k in ('modes','resume_modes'):
        if np.any(s[k]!=np.floor(s[k])) or np.any(s[k]<0) or np.any(s[k]>=len(MODES)): raise ValueError('mode encoding')
        s[k]=[MODES[int(i)] for i in s[k]]
    integer_fields=('cycle','clear_count','load_count','distal_count','wait_count','last_tick','generation')
    for k in integer_fields:
        if np.any(s[k]!=np.floor(s[k])) or np.any(np.abs(s[k])>2**53): raise ValueError('integer encoding '+k)
    for k in ('partial','initialized','admitted','release_veto','positive_nonfoot','range_flags'):
        if np.any((s[k]!=0)&(s[k]!=1)): raise ValueError('Boolean encoding '+k)
    for k in ('cycle','clear_count','load_count','distal_count','wait_count'):
        if np.any(s[k]<0): raise ValueError('negative counter '+k)
        s[k]=s[k].astype(np.int64)
    if s['last_tick'][0]<-1 or s['generation'][0]<0:raise ValueError('state clock domain')
    if any(np.any(s[k]>30) for k in ('clear_count','load_count','distal_count')) or np.any(s['wait_count']>500):raise ValueError('counter bound')
    s['partial']=s['partial'].astype(bool);s['theta']=c['theta'];s['magnitude']=c['magnitude']
    for k in ('native_reference','correction','z','requested_increment','limited_increment','before_ball','after_ball','range_flags'):s[k]=s[k].reshape(6,7)
    s['landing_xy']=s['landing_xy'].reshape(6,2)
    for k in ('z0','last_tick','generation','initialized'):s[k]=s[k][0].item()
    s['initialized']=bool(s['initialized']);s['last_tick']=int(s['last_tick']);s['generation']=int(s['generation'])
    if not s['initialized']:s['z0']=None
    return s
BEHAVIOR_ERRORS=frozenset(('stall: active gate wait exceeded500','phase_lag: pi/2 exceeded','intent increment/magnitude','native template outside compiled ranges','native reference outside limits','post-projection norm/rate bound'))
def classify(error,profile):
    if profile==PROFILE and type(error).__name__=='ContractError' and str(error) in BEHAVIOR_ERRORS:return 'controller_infeasible'
    if isinstance(error,FloatingPointError):return 'unsafe'
    if type(error).__name__=='ResourceStop':return 'resource'
    if type(error).__name__=='RetentionError':return 'retention'
    return 'integration'
def exact_grid(ticks):
    if ticks.dtype!=np.int64 or not np.array_equal(ticks,np.arange(len(ticks),dtype=np.int64)):raise ValueError('endpoint grid')
