"""Exclusive v11 retention. Independent of all v10 recorder implementations."""
from __future__ import annotations
import hashlib,json,os,sys,time,resource
from pathlib import Path
import numpy as np

ROOT=Path('/tmp/fly-arena-behavior-v11')
SCRATCH=Path('/tmp/fly-v11-realization')
OUT=ROOT/'var/behavior-v11/audit-01'
RAW=Path('/tmp/fly-arena-behavior-v10/var/behavior-v10/mechanical-01')
START=1789577628
DEADLINE=1789583028

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def json_bytes(value):
    return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()

def exclusive_json(path,value):
    content=json_bytes(value)  # Serialization failure must not create an empty receipt.
    with Path(path).open('xb') as f:
        f.write(content);f.flush();os.fsync(f.fileno())

def failure(exc,stage):
    return {'stage':stage,'type':type(exc).__name__,'message':str(exc)}

class Budget:
    def __init__(self):self.started=time.monotonic();self.checks=0
    def report(self):
        r=resource.getrusage(resource.RUSAGE_SELF)
        # Count all new task files in evidence/scratch; new source is tiny but counted.
        paths=[p for base in [ROOT/'var/behavior-v11',SCRATCH] for p in base.rglob('*') if p.is_file()]
        paths += [p for base in [ROOT/'src',ROOT/'tests',ROOT/'scripts',ROOT/'docs'] for p in base.rglob('*v11*') if p.is_file()]
        return {'wall_since_task_start_s':time.time()-START,'process_wall_s':time.monotonic()-self.started,
                'user_cpu_s':r.ru_utime,'system_cpu_s':r.ru_stime,'peak_rss_bytes':r.ru_maxrss if sys.platform=='darwin' else r.ru_maxrss*1024,
                'new_bytes':sum(p.stat().st_size for p in paths),'workers':1,'physical_seconds':0,'neural_seconds':0,'sweeps':0,'checks':self.checks}
    def check(self):
        self.checks+=1;r=self.report()
        if time.time()>DEADLINE or r['peak_rss_bytes']>8*1024**3 or r['new_bytes']>2*1024**3-64*1024**2:
            raise RuntimeError('registered hard cap/headroom reached: '+json.dumps(r))
        return r

class NumericChunks:
    """Only initialized finite rows; committed chunk receipt after durable close."""
    def __init__(self,path,width,metadata,chunk_size=1000):
        self.path=Path(path);self.path.mkdir(parents=True,exist_ok=False)
        self.width=width;self.values=np.empty((chunk_size,width),dtype=np.float64)
        self.ticks=np.empty(chunk_size,dtype=np.int64);self.n=0;self.total=0;self.committed=0
        self.files=[];self.errors=[];self.closed=False;self.last_tick=None
        exclusive_json(self.path/'start.json',{'schema':'numeric-start/v11','width':width,'metadata':metadata})
    def append(self,tick,values):
        if self.closed:raise RuntimeError('closed writer')
        v=np.asarray(values)
        if v.shape!=(self.width,) or v.dtype.kind not in 'fiu' or not np.isfinite(v).all():raise ValueError('invalid/nonfinite numeric row')
        if type(tick) is not int or (self.last_tick is not None and tick!=self.last_tick+1):raise ValueError('nonconsecutive tick')
        if self.n==len(self.ticks):self.flush()
        self.ticks[self.n]=tick;self.values[self.n]=v;self.n+=1;self.total+=1;self.last_tick=tick
    def flush(self):
        if not self.n:return
        name=f'chunk-{len(self.files):05d}.npz';p=self.path/name
        # A failed archive remains .partial and cannot be mistaken for committed data.
        partial=self.path/(name+'.partial')
        with partial.open('xb') as f:
            np.savez_compressed(f,ticks=self.ticks[:self.n],values=self.values[:self.n]);f.flush();os.fsync(f.fileno())
        os.link(partial,p);partial.unlink()
        receipt={'file':name,'sha256':sha(p),'rows':self.n,'first_tick':int(self.ticks[0]),'last_tick':int(self.ticks[self.n-1])}
        exclusive_json(self.path/(name+'.json'),receipt)
        self.files.append(receipt);self.committed+=self.n;self.n=0
    def finish(self,primary=None,extra=None):
        if self.closed:raise RuntimeError('duplicate finalization')
        self.closed=True
        try:
            self.flush()
        except BaseException as e:
            self.errors.append(failure(e,'flush'))
            try:
                with (self.path/'emergency-prefix.npz').open('xb') as f:
                    np.savez(f,ticks=self.ticks[:self.n],values=self.values[:self.n]);f.flush();os.fsync(f.fileno())
            except BaseException as e:self.errors.append(failure(e,'emergency-prefix'))
        result={'schema':'numeric-terminal/v11','complete':primary is None and not self.errors,
                'primary_failure':primary,'retention_failures':self.errors,'initialized_rows':self.total,
                'committed_rows':self.committed,'last_initialized_tick':self.last_tick,'files':self.files,'extra':extra}
        try:exclusive_json(self.path/'terminal.json',result)
        except BaseException as e:
            self.errors.append(failure(e,'terminal'));result['complete']=False
            try:
                SCRATCH.mkdir(exist_ok=True)
                exclusive_json(SCRATCH/(self.path.parent.name+'-'+self.path.name+'-failure-'+str(time.time_ns())+'.json'),result)
            except BaseException as e:
                self.errors.append(failure(e,'fallback-terminal'))
                print('TOTAL FILESYSTEM FAILURE: no durable terminal guarantee; '+json.dumps(result),file=sys.stderr)
        return result

def read_raw(path,rows,width,stride,inputs):
    path=Path(path);terminal=json.loads((path/'terminal.json').read_text())
    if not terminal['complete'] or terminal['primary_failure'] or terminal['retention_failures']:raise ValueError('incomplete raw stream')
    if terminal['initialized_rows']!=rows:raise ValueError('raw row horizon mismatch')
    ticks=[];values=[]
    names=sorted(n for n in terminal['files'] if n.startswith('chunk-'))
    if names!=[p.name for p in sorted(path.glob('chunk-*.npz'))]:raise ValueError('raw chunk inventory mismatch')
    for i,name in enumerate(names):
        p=path/name
        if name!=f'chunk-{i:05d}.npz' or sha(p)!=inputs[str(p)]['sha256'] or sha(p)!=terminal['files'][name]:raise ValueError('raw hash/order mismatch')
        with np.load(p,allow_pickle=False) as z:
            if set(z.files)!={'ticks','values'}:raise ValueError('unsafe raw schema')
            t=z['ticks'];v=z['values']
            if t.dtype!=np.int64 or v.dtype!=np.float64 or v.shape!=(len(t),width) or not np.isfinite(v).all():raise ValueError('raw dtype/shape/nonfinite')
            ticks.append(t);values.append(v)
    t=np.concatenate(ticks);v=np.concatenate(values)
    if not np.array_equal(t,np.arange(rows)*stride):raise ValueError('missing/duplicate ticks')
    return t,v

def slices(schema):
    i=0;out={}
    for name,n in schema:out[name]=slice(i,i+n);i+=n
    return out

def read_dense(path):
    term=json.loads((path/'terminal.json').read_text())
    if not term['complete']:raise ValueError('incomplete dense data')
    arrays=[]
    for item in term['files']:
        p=path/item['file']
        if sha(p)!=item['sha256']:raise ValueError('dense hash mismatch')
        with np.load(p,allow_pickle=False) as z:arrays.append(z['values'])
    return np.concatenate(arrays)
