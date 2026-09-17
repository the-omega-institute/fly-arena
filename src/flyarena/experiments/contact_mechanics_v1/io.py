"""Exclusive evidence with explicit child failures and checked emergency prefixes."""
import hashlib,json,pathlib,time
import numpy as np
from ..evidence_v10 import NumericEvidence
from .schema import width,CORE,CONTACT,CANDIDATE,LEGACY,PROFILE
_ACTIVE_BUDGET=None
class RetentionError(RuntimeError):pass

def account_existing(path):
    if _ACTIVE_BUDGET is not None:_ACTIVE_BUDGET.known_bytes+=pathlib.Path(path).stat().st_size

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def write(path,value):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    payload=json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n'
    if _ACTIVE_BUDGET is not None and not _ACTIVE_BUDGET.finalizing:_ACTIVE_BUDGET.check(pending_memory=len(payload.encode()),pending_disk=len(payload.encode()))
    with path.open('x') as f:f.write(payload)
    account_existing(path)
def read(path):return json.loads(pathlib.Path(path).read_text())
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def numeric_archive(path,columns):
    with np.load(path,allow_pickle=False) as data:
        if set(data.files)!={'ticks','values'}:raise ValueError('chunk schema')
        ticks=data['ticks'];values=data['values']
        if ticks.dtype!=np.int64 or values.dtype!=np.float64 or values.shape!=(len(ticks),columns) or not np.isfinite(values).all() or np.any(ticks<0):raise ValueError('chunk dtype/shape/finite/domain')
        return ticks.copy(),values.copy()

def stream_rows(root,schema,*,allow_partial=False):
    root=pathlib.Path(root);terminal=read(root/'terminal.json')
    if type(terminal['complete']) is not bool or type(terminal['initialized_rows']) is not int or terminal['initialized_rows']<0:raise ValueError('stream terminal domain')
    if terminal['complete'] and (terminal.get('primary_failure') is not None or terminal.get('retention_failures')):raise ValueError('contradictory stream completion')
    if not allow_partial and not terminal['complete']:raise ValueError('incomplete stream')
    expected=sorted(name for name in terminal['files'] if name.startswith('chunk-'))
    if expected!=[f'chunk-{i:05d}.npz' for i in range(len(expected))]:raise ValueError('chunk order')
    for name,h in terminal['files'].items():
        if pathlib.Path(name).name!=name or sha(root/name)!=h:raise ValueError('retained file identity/hash')
    actual={p.name for p in root.glob('chunk-*.npz')};emergency=root/'emergency-prefix.npz';recovery_path=root/'recovery.json'
    recovery=None
    if emergency.exists() or actual!=set(expected):
        if not allow_partial or terminal['complete'] or not recovery_path.exists():raise ValueError('unbound emergency/orphan evidence')
        recovery=read(recovery_path)
        required={'schema','terminal_sha256','emergency','orphan_files','regular_rows','emergency_rows','initialized_rows','complete'}
        if set(recovery)!=required or recovery['schema']!='contact-mechanics-recovery/v1' or recovery['complete'] is not False or recovery['terminal_sha256']!=sha(root/'terminal.json'):raise ValueError('recovery schema/identity')
        if set(recovery['orphan_files'])!=actual-set(expected):raise ValueError('orphan chunk file set')
        for name,h in recovery['orphan_files'].items():
            if sha(root/name)!=h:raise ValueError('orphan chunk changed')
        if not emergency.exists() or recovery['emergency']!={'file':'emergency-prefix.npz','sha256':sha(emergency)}:raise ValueError('emergency prefix identity')
    count=0;last=-1
    for name in expected+(['emergency-prefix.npz'] if recovery else []):
        ticks,values=numeric_archive(root/name,width(schema))
        if recovery and name=='emergency-prefix.npz':
            if count!=recovery['regular_rows'] or len(ticks)!=recovery['emergency_rows']:raise ValueError('emergency row accounting')
        for tick,row in zip(ticks,values):
            if tick<last:raise ValueError('stream clock order')
            last=int(tick);count+=1;yield int(tick),row
    if count!=terminal['initialized_rows'] or recovery and count!=recovery['initialized_rows']:raise ValueError('retained row count mismatch')

class BudgetEvidence(NumericEvidence):
    def __init__(self,*a,budget,**kw):
        self.budget=budget
        columns=a[1];chunk_size=kw.get('chunk_size',1000);budget.check(pending_memory=chunk_size*(columns*8+8),pending_disk=chunk_size*(columns*8+8))
        super().__init__(*a,**kw);self.released=False
        budget.pending_buffers+=self.values.nbytes+self.ticks.nbytes
    def flush(self):
        if self.n:self.budget.check(pending_memory=self.n*(self.width*8+8)+65536,pending_disk=65536)
        before=self.chunk;super().flush()
        if self.chunk>before:
            size=(self.root/f'chunk-{before:05d}.npz').stat().st_size;self.budget.known_bytes+=size;self.budget.stream_bytes+=size
    def finish(self,error=None,**kwargs):
        terminal=super().finish(error,**kwargs)
        emergency=self.root/'emergency-prefix.npz'
        expected={name for name in terminal['files'] if name.startswith('chunk-')}
        orphans={p.name:sha(p) for p in self.root.glob('chunk-*.npz') if p.name not in expected}
        if emergency.exists() or orphans:
            if terminal['complete'] or not emergency.exists():raise RetentionError('unrecoverable emergency prefix')
            regular_rows=sum(len(numeric_archive(self.root/name,self.width)[0]) for name in expected)
            emergency_rows=len(numeric_archive(emergency,self.width)[0])
            if regular_rows+emergency_rows!=terminal['initialized_rows']:raise RetentionError('emergency initialized row count')
            write(self.root/'recovery.json',{'schema':'contact-mechanics-recovery/v1','terminal_sha256':sha(self.root/'terminal.json'),
              'emergency':{'file':emergency.name,'sha256':sha(emergency)},'orphan_files':orphans,'regular_rows':regular_rows,
              'emergency_rows':emergency_rows,'initialized_rows':terminal['initialized_rows'],'complete':False})
            account_existing(emergency)
        return terminal
    def release(self):
        if not self.released:self.budget.pending_buffers-=self.values.nbytes+self.ticks.nbytes;self.released=True

class Writers:
    def __init__(self,dest,trial,registration,budget,*,metadata=None):
        self.dest=pathlib.Path(dest);self.budget=budget;self.items={};self.contact_offset=0;self.trial=trial
        meta={**trial.record(),'registration_sha256':registration} if metadata is None else metadata
        try:
            for name,schema in (('core',CORE),('contacts',CONTACT),('state',CANDIDATE if trial.profile==PROFILE else LEGACY)):
                self.items[name]=BudgetEvidence(self.dest/name,width(schema),metadata=meta,budget=budget)
        except BaseException as error:
            self.finish(error,{'scheduled_ticks':40000,'completed_ticks':0,'retained_endpoint_rows':0,'missing_remainder':40000,'failure_kind':'integration','setup_failed':True})
            raise
    def append(self,tick,core,state,contacts):
        self.items['core'].append(tick,core);self.items['state'].append(tick,state)
        for row in contacts:self.items['contacts'].append(tick,row)
        self.contact_offset+=len(contacts)
    def finish(self,error,extra,failing=None):
        previous=self.budget.finalizing;self.budget.finalizing=True;failures=list(extra.get('secondary_failures',[]));terminals={};started=time.monotonic()
        try:
            for name,w in self.items.items():
                try:
                    terminal=w.finish(error,failing_values=failing if name=='core' else None,extra=extra);terminals[name]=terminal
                    if terminal.get('retention_failures'):failures.extend({'stream':name,**r} for r in terminal['retention_failures'])
                    if error is None and not terminal.get('complete'):failures.append({'stream':name,'message':'child evidence incomplete'})
                except BaseException as exc:failures.append({'stream':name,'type':type(exc).__name__,'message':str(exc)})
            if set(terminals)!={'core','contacts','state'}:failures.append({'stage':'initialization','message':'not all streams finalized'})
            complete=error is None and not failures and all(t['complete'] for t in terminals.values())
            rows={name:t['initialized_rows'] for name,t in terminals.items()}
            value={**extra,'schema':'contact-mechanics-trial-terminal/v2','trial_id':self.trial.identity,'complete':complete,'failure':None if error is None else {'type':type(error).__name__,'message':str(error)},
              'primary_failure_kind':extra.get('failure_kind'),'failure_kind':'retention' if failures else extra.get('failure_kind'),
              'retention_failures':failures,'retention_passed':not failures,'streams':terminals,'retained_rows':rows}
            write(self.dest/'trial-terminal.json',value)
        finally:
            for w in self.items.values():w.release()
            self.budget.finalizing=previous;self.budget.note_finalization(time.monotonic()-started)
        if failures:raise RetentionError('retention failure: '+str(failures))
        return value
