"""Frozen fullgraph CUDA experiment; accepted recurrence and adapters stay untouched."""
from __future__ import annotations
import argparse
import ctypes
import ctypes.util
import base64
import csv
import io
import zipfile
from types import SimpleNamespace
from collections import OrderedDict
from dataclasses import asdict
import gc
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import resource
import shutil
import struct
import sys
import threading
import time
import zlib
import numpy as np

SCHEMA = 'cuda-fullgraph/v1'
N = 165122
E = 25563197
SUBJECTS = ('wt', 'mutant')
STATE_KEYS = {'v','current','refractory','delay','external','rates','tick','total_spikes'}
EXACT = {'counts','refractory','tick','total_spikes'}
SEGMENTS = ((0,100,0.,0.),(100,300,1.,0.),(300,500,0.,1.),(500,700,1.,1.),(700,800,0.,0.))
CHUNKS = tuple((start+offset,steps) for start,end,_,_ in SEGMENTS for offset,steps in ((0,7),(7,19),(26,end-start-26)))
GIB = 1024**3
EVIDENCE_CAP = 24*GIB
RESERVE = 256*1024**2
SOURCE_NAMES = ('src/flyarena/neural.py','src/flyarena/optional_backend.py','src/flyarena/cuda_ordered.py','src/flyarena/compiler.py','src/flyarena/connectome.py','src/flyarena/common.py','src/flyarena/contracts.py','src/flyarena/__init__.py','scripts/cuda_policy.json','scripts/run_cuda_fullgraph.py','scripts/verify_cuda_fullgraph.py','scripts/cuda_fullgraph_policy.json','tests/test_cuda_fullgraph.py')

def require(condition, message):
    if not condition:
        raise ValueError(message)

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def sha_file(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()

def write_json(path,value,exclusive=True):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb' if exclusive else 'wb') as f:
        f.write(canonical(value)+b'\n');f.flush();os.fsync(f.fileno())

def stimulus(tick):
    require(type(tick) is int and 0<=tick<800,'schedule tick invalid')
    for start,end,left,right in SEGMENTS:
        if start<=tick<end:return left,right
    raise ValueError('schedule incomplete')

def state_schema(n):
    return {**{key:('<f8',(n,)) for key in ('v','current','external','rates')},
            'refractory':('<i4',(n,)),'delay':('<f8',(19,n)),
            'tick':('<i8',()),'total_spikes':('<i8',()),'counts':('<i4',(n,))}

def validate_state(state,n,steps=None):
    require(isinstance(state,dict) and set(state)==STATE_KEYS|{'counts'},'state field set')
    for key,(dtype,shape) in state_schema(n).items():
        a=state[key]
        require(isinstance(a,np.ndarray) and a.dtype.str==dtype and a.shape==shape,key+' dtype/shape')
        require(np.isfinite(a).all(),key+' nonfinite')
    require(np.all((state['refractory']>=0)&(state['refractory']<=22)),'refractory bounds')
    require(np.all(state['rates']>=0),'negative rates')
    require(int(state['tick'])>=0 and int(state['total_spikes'])>=0,'negative counter')
    require(np.all(state['counts']>=0),'negative counts')
    if steps is not None:require(np.all(state['counts']<=steps),'count exceeds compared interval')

class ObjectStore:
    """Typed lossless vector objects; byte identity alone permits object reuse."""
    def __init__(self,root,n=N,cap=EVIDENCE_CAP-RESERVE-256*1024**2,readonly=False):
        self.root=Path(root);self.n=n;self.cap=cap;self.readonly=readonly
        self.directory=self.root/'objects';self.bytes=0;self.io_seconds=0.;self.cache=OrderedDict();self.cache_bytes=0
        if not readonly:
            self.directory.mkdir(parents=True,exist_ok=True)
            require(not any(self.directory.iterdir()), 'writer requires fresh object directory')
        self.known={}
    def _path(self,key):
        require(isinstance(key,str) and len(key)==64 and all(c in '0123456789abcdef' for c in key),'invalid object key')
        return self.directory/key[:2]/(key+'.bin')
    def _remember(self,key,a):
        if key in self.cache:return
        a.flags.writeable=False;self.cache[key]=a;self.cache_bytes+=a.nbytes
        while self.cache_bytes>64*1024**2:
            _,v=self.cache.popitem(last=False);self.cache_bytes-=v.nbytes
    def put(self,array):
        require(not self.readonly,'read-only store')
        started=time.perf_counter();a=np.asarray(array)
        require(a.dtype.kind in 'fiu' and a.dtype.itemsize in (4,8) and a.ndim<=1,'unsupported object array')
        require(a.size<=self.n,'object too large')
        raw=a.tobytes(order='C');meta={'dtype':a.dtype.str,'shape':list(a.shape),'bytes':len(raw)}
        key=hashlib.sha256(canonical(meta)+b'\0'+raw).hexdigest();path=self._path(key)
        if path.exists():
            saved=self.get(key)
            require(saved.dtype==a.dtype and saved.shape==a.shape and saved.tobytes()==raw,'content address collision')
        else:
            compressed=zlib.compress(raw,1)
            codec='zlib' if len(compressed)<len(raw) else 'raw';payload=compressed if codec=='zlib' else raw
            header={**meta,'codec':codec,'raw_sha256':hashlib.sha256(raw).hexdigest()}
            encoded=canonical(header)+b'\n'+payload
            require(self.bytes+len(encoded)<=self.cap,'evidence object budget exhausted')
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as f:f.write(encoded)
            self.bytes+=len(encoded);self.known[key]={'bytes':len(encoded),'sha256':hashlib.sha256(encoded).hexdigest()}
            self._remember(key,np.frombuffer(raw,dtype=a.dtype).reshape(a.shape).copy())
        self.io_seconds+=time.perf_counter()-started
        return key
    def get(self,key):
        self._path(key)  # Validate before dictionary membership; references cannot be chains.
        if key in self.cache:
            self.cache.move_to_end(key);return self.cache[key]
        path=self._path(key);require(path.is_file() and not path.is_symlink(),'missing/nonregular object')
        require(path.stat().st_size<=self.n*8+4096,'oversized object')
        with path.open('rb') as f:
            line=f.readline(4097);require(len(line)<=4096 and line.endswith(b'\n'),'object header bound')
            header=json.loads(line);payload=f.read(self.n*8+1)
        require(set(header)=={'dtype','shape','bytes','codec','raw_sha256'},'object header fields')
        dtype=np.dtype(header['dtype']);shape=header['shape']
        require(dtype.kind in 'fiu' and dtype.itemsize in (4,8) and isinstance(shape,list) and len(shape)<=1 and all(type(v) is int and 0<=v<=self.n for v in shape),'object dtype/shape')
        size=math.prod(shape)*dtype.itemsize
        require(type(header['bytes']) is int and size==header['bytes'] and size<=self.n*8,'object byte declaration')
        if header['codec']=='raw':raw=payload
        elif header['codec']=='zlib':
            decompressor=zlib.decompressobj();raw=decompressor.decompress(payload,size+1)
            require(decompressor.eof and not decompressor.unused_data and not decompressor.unconsumed_tail,'invalid/trailing/oversized compressed stream')
        else:raise ValueError('unsupported object codec')
        require(len(raw)==size and hashlib.sha256(raw).hexdigest()==header['raw_sha256'],'object raw integrity')
        meta={k:header[k] for k in ('dtype','shape','bytes')}
        require(hashlib.sha256(canonical(meta)+b'\0'+raw).hexdigest()==key,'object address integrity')
        a=np.frombuffer(raw,dtype=dtype).reshape(shape).copy();self._remember(key,a);return a
    def encode(self,state):
        validate_state(state,self.n)
        return {key:[self.put(row) for row in value] if key=='delay' else self.put(value) for key,value in state.items()}
    def decode(self,refs):
        require(isinstance(refs,dict) and set(refs)==STATE_KEYS|{'counts'},'record array references')
        require(isinstance(refs['delay'],list) and len(refs['delay'])==19,'delay row count')
        out={key:np.stack([self.get(v) for v in value]) if key=='delay' else self.get(value).copy() for key,value in refs.items()}
        validate_state(out,self.n);return out

def preserve_unchecked_state(folder,state,metadata,task_root=None):
    """Bounded failure reserve; raw arrays may be invalid, and omissions are explicit."""
    folder=Path(folder);root=folder.parent
    receipt={**metadata,'arrays':{},'unavailable':{},'capture_errors':[],
             'complete':False,'receipt_path':str(folder/'state.json')}
    available=state if isinstance(state,dict) else {}
    for key in sorted(STATE_KEYS|{'counts'}):
        value=available.get(key)
        if isinstance(value,np.ndarray):
            receipt['arrays'][key]={'dtype':value.dtype.str,'shape':list(value.shape),
                                    'raw_bytes':value.nbytes,'retained':False}
        else:receipt['unavailable'][key]='array unavailable'
    try:
        folder.mkdir(parents=True,exist_ok=False)
        evidence_bytes=sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
        failure_bytes=sum(p.stat().st_size for p in root.rglob('*') if p.is_file() and
                          any('failure' in part or part=='invalid-record-state' for part in p.relative_to(root).parts[:-1]))
        task_bytes=evidence_bytes if task_root is None else sum(p.stat().st_size for p in Path(task_root).rglob('*') if p.is_file())
        # Keep 1 MiB for receipts, even if normal evidence exhausted its quota.
        remaining=max(0,min(RESERVE-failure_bytes,EVIDENCE_CAP-evidence_bytes,
                            32*GIB-task_bytes,shutil.disk_usage(root).free-20*GIB)-1024**2)
        for key,record in receipt['arrays'].items():
            value=available[key];path=folder/(key+'.npy')
            try:
                require(not value.dtype.hasobject,'object array cannot be retained safely')
                require(value.nbytes+4096<=remaining,'failure reserve/disk budget exhausted')
                with path.open('xb') as stream:
                    np.save(stream,value,allow_pickle=False);stream.flush();os.fsync(stream.fileno())
                record.update(retained=True,bytes=path.stat().st_size,sha256=sha_file(path))
            except Exception as exc:
                record['omission']=type(exc).__name__+': '+str(exc)
                if path.exists():record['partial_bytes']=path.stat().st_size
                receipt['capture_errors'].append(key+': '+str(exc))
            finally:
                if path.exists():remaining-=path.stat().st_size
        receipt['complete']=not receipt['unavailable'] and all(r['retained'] for r in receipt['arrays'].values())
        write_json(folder/'state.json',receipt)
    except Exception as exc:
        receipt['capture_errors'].append(type(exc).__name__+': '+str(exc))
        receipt['receipt_write_unavailable']=True
    return receipt

def capture_failure(error,folder,state,metadata,task_root=None):
    """Capture failures never replace the original execution/recording error."""
    try:receipt=preserve_unchecked_state(folder,state,metadata,task_root)
    except BaseException as exc:
        receipt={'complete':False,'receipt_write_unavailable':True,
                 'capture_errors':[type(exc).__name__+': '+str(exc)]}
    error.failure_capture=receipt
    return receipt

class Recorder:
    def __init__(self,root,store,subject,backend,phase):
        self.path=Path(root)/'records'/subject/backend/(phase+'.jsonl');self.path.parent.mkdir(parents=True,exist_ok=True)
        self.file=self.path.open('x');self.store=store;self.rows=[];self.phase=phase
    def append(self,state,kind,steps,binding):
        try:
            validate_state(state,self.store.n,None if kind.endswith('-loaded') else steps)
            record={'index':len(self.rows),'kind':kind,'steps':steps,'tick':int(state['tick']),'binding':binding,'arrays':self.store.encode(state)}
            self.file.write(canonical(record).decode()+'\n');self.file.flush();os.fsync(self.file.fileno())
            self.rows.append(record);return record
        except BaseException as exc:
            capture_failure(exc,self.store.root/'invalid-record-state',state,
                            {'phase':self.phase,'kind':kind,'steps':steps,'binding':binding,
                             'completed_record_prefix':len(self.rows),'record_path':str(self.path),
                             'final_row_may_be_partial':True,'original_error':str(exc)})
            raise
    def close(self):self.file.close()

def snapshot(backend,counts):
    state=backend.checkpoint()['state'];state['counts']=np.asarray(counts,dtype=np.int32).copy();return state

def compare(expected,actual,exact=False):
    validate_state(expected,len(expected['v']));validate_state(actual,len(expected['v']))
    for key in sorted(expected):
        a,b=expected[key],actual[key]
        if exact or key in EXACT:np.testing.assert_array_equal(a,b,err_msg=key)
        else:np.testing.assert_allclose(a,b,atol=1e-10,rtol=1e-12,err_msg=key)

class DifferenceStats:
    def __init__(self):self.fields={}
    def add(self,expected,actual,tick):
        for key in expected:
            a,b=expected[key],actual[key]
            if a.tobytes()==b.tobytes():continue
            numeric=a!=b;count=int(np.count_nonzero(numeric));indices=np.flatnonzero(numeric.ravel())
            index=int(indices[0]) if len(indices) else int(np.flatnonzero(a.reshape(-1).view(np.uint8)!=b.reshape(-1).view(np.uint8))[0]//a.dtype.itemsize)
            rec=self.fields.setdefault(key,{'first_tick':tick,'first_flat_index':index,'first_cpu':a.ravel()[index].item(),'first_cuda':b.ravel()[index].item(),'byte_distinct_observations':0,'numerically_different_elements':0,'max_abs':0.,'max_relative':0.,'max_ulp':0})
            rec['byte_distinct_observations']+=1;rec['numerically_different_elements']+=count
            if a.dtype.kind=='f':
                delta=np.abs(a-b);rec['max_abs']=max(rec['max_abs'],float(delta.max(initial=0)))
                relative=np.divide(delta,np.abs(b),out=np.zeros_like(delta),where=b!=0);rec['max_relative']=max(rec['max_relative'],float(relative.max(initial=0)));rec['relative_infinite']=rec.get('relative_infinite',False) or bool(np.any((b==0)&(delta!=0)))
                ua=a.view(np.uint64);ub=b.view(np.uint64);oa=np.where((ua>>63)!=0,~ua,ua|(np.uint64(1)<<np.uint64(63)));ob=np.where((ub>>63)!=0,~ub,ub|(np.uint64(1)<<np.uint64(63)))
                ulp=np.maximum(oa,ob)-np.minimum(oa,ob);rec['max_ulp']=max(rec['max_ulp'],int(ulp.max(initial=0)))

class TickLedger:
    def __init__(self,path,caps=None):
        self.path=Path(path);self.file=self.path.open('x');self.counts={'cpu':0,'cuda':0};self.caps=caps or {'cpu':5794,'cuda':5794};self.entries=[]
    def _write(self,entry):
        self.file.write(canonical(entry).decode()+'\n');self.file.flush();os.fsync(self.file.fileno())
    def reserve(self,backend,subject,phase,before,steps):
        require(type(steps) is int and steps>0 and type(before) is int and before>=0,'invalid reserved steps/tick')
        require(backend in self.counts and subject in SUBJECTS,'unknown ledger runtime/subject')
        require(self.counts[backend]+steps<=self.caps[backend],'tick budget exhausted')
        require(not self.entries or self.entries[-1]['state']=='completed','unresolved prior advance')
        e={'index':len(self.entries),'backend':backend,'subject':subject,'phase':phase,'before_tick':before,'steps':steps,'state':'reserved'}
        self._write(e);self.counts[backend]+=steps;self.entries.append(e);return e['index']
    def completed(self,index,after):
        require(type(index) is int and 0<=index<len(self.entries),'completion index')
        e=self.entries[index];require(e['state']=='reserved','duplicate completion');require(type(after) is int and after==e['before_tick']+e['steps'],'advance tick mismatch')
        self._write({'index':index,'state':'completed','after_tick':after});e['state']='completed'
    def summary(self):
        """Reconstruct only the retained valid journal prefix, including unresolved calls."""
        reserved={'cpu':0,'cuda':0};completed={'cpu':0,'cuda':0};entries=[];error=None
        try:
            with self.path.open() as stream:
                for line in stream:
                    require(line.endswith('\n'),'partial ledger line')
                    row=json.loads(line);index=row['index']
                    if row['state']=='reserved':
                        require(index==len(entries) and (not entries or entries[-1]['state']=='completed'),'reservation sequence')
                        require(row['backend'] in reserved and type(row['steps']) is int and row['steps']>0,'reservation value')
                        entries.append(row);reserved[row['backend']]+=row['steps']
                    else:
                        require(row['state']=='completed' and type(index) is int and index==len(entries)-1 and index>=0,'completion sequence')
                        e=entries[index];require(e['state']=='reserved' and row['after_tick']==e['before_tick']+e['steps'],'completion tick')
                        e['state']='completed';completed[e['backend']]+=e['steps']
        except Exception as exc:error=type(exc).__name__+': '+str(exc)
        unresolved={k:reserved[k]-completed[k] for k in reserved}
        return {'reserved':reserved,'completed':completed,'unresolved':unresolved,
                'accounting_complete':error is None,'accounting_error':error,
                'actual_executed_ticks':completed if error is None and not any(unresolved.values()) else None,
                'semantics':'completed ticks are confirmed returns; unresolved calls may have partially executed; invalid journals give only a known prefix'}
    def close(self):self.file.close()

class AllocationLedger:
    """Requested bytes observed at actual driver allocations/frees, including pending frees."""
    def __init__(self, cap=2*GIB,path=None):
        self.file=None if path is None else Path(path).open('x')
        self.cap=cap;self.live={};self.current=0;self.peak=0;self.allocations=0;self.frees=0;self.error=None
    def allocated(self,address,size):
        require(type(address) is int and address>0 and address not in self.live,'unknown/reused allocation address')
        require(type(size) is int and size>0,'allocation size')
        self.live[address]=size;self.current+=size;self.peak=max(self.peak,self.current);self.allocations+=1
        if self.file is not None:self.file.write(canonical({'event':'allocate','address':address,'bytes':size,'current':self.current}).decode()+'\n');self.file.flush()
        if self.current>self.cap:self.error='tracked CUDA allocation cap exceeded'
    def freed(self,address):
        require(address in self.live,'untracked actual CUDA free')
        size=self.live.pop(address);self.current-=size;self.frees+=1
        if self.file is not None:self.file.write(canonical({'event':'free','address':address,'bytes':size,'current':self.current}).decode()+'\n');self.file.flush()
    def check(self):require(self.error is None,self.error)
    def report(self):
        return {'current_requested_bytes':self.current,'peak_requested_bytes':self.peak,
                'allocations':self.allocations,'actual_frees':self.frees,
                'scope':'cuMemAlloc/cuMemFree requested bytes; excludes context/library/physical allocator overhead'}

class DriverObserver:
    """Observe default Numba ctypes driver routes. Unsupported routes stop before allocation."""
    def __init__(self,path=None):
        from numba.cuda.cudadrv import driver as module
        require(not module.USE_NV_BINDING,'unvalidated NVIDIA binding allocation route')
        self.module=module;self.driver=module.driver;self.ledger=AllocationLedger(path=path);self.saved={};self.live_array_peak=0
    def install(self):
        # Resolve the same driver functions Numba uses before replacing only observation wrappers.
        for name in ('cuMemAlloc','cuMemFree','cuMemAllocManaged','cuMemHostAlloc','cuMemAllocHost','cuMemAllocAsync'):
            try:self.saved[name]=getattr(self.driver,name)
            except Exception:
                if name in ('cuMemAlloc','cuMemFree'):raise
        def alloc(pointer,size):
            require(self.ledger.current+int(size)<=self.ledger.cap,'tracked CUDA allocation cap would be exceeded')
            result=self.saved['cuMemAlloc'](pointer,size)
            self.ledger.allocated(int(pointer._obj.value),int(size));return result
        def free(pointer):
            address=int(getattr(pointer,'value',pointer));result=self.saved['cuMemFree'](pointer)
            self.ledger.freed(address);return result
        self.driver.cuMemAlloc=alloc;self.driver.cuMemFree=free
        for name in self.saved:
            if name not in ('cuMemAlloc','cuMemFree'):
                def unsupported(*args,_name=name,**kwargs):raise RuntimeError('unobserved allocation route: '+_name)
                setattr(self.driver,name,unsupported)
    def preflight(self):
        from numba import cuda
        require(type(cuda.current_context().memory_manager).__name__=='NumbaCUDAMemoryManager','custom memory manager')
        before=self.ledger.current;a=cuda.device_array(1,dtype=np.int32);cuda.synchronize()
        require(self.ledger.current==before+4,'allocation observation failed')
        del a;gc.collect();cuda.current_context().memory_manager.deallocations.clear()
        require(self.ledger.current==before,'actual deferred free observation failed')
    def drain(self):
        from numba import cuda
        cuda.synchronize();gc.collect();cuda.current_context().memory_manager.deallocations.clear();self.ledger.check()
        require(self.ledger.current==0,'backend allocations still live at boundary')
    def close(self):
        for name,original in self.saved.items():setattr(self.driver,name,original)
        if self.ledger.file is not None:self.ledger.file.close()

class ResourceGuard:
    """10ms telemetry; cgroup memory.max is the hard host cap, samples are lower bounds."""
    def __init__(self,task,output,uuid,started_epoch,sample_name='resource-samples.jsonl',compute_epoch=None):
        self.task=Path(task);self.output=Path(output);self.started=time.monotonic();self.stage_epoch=started_epoch
        self.compute_epoch=time.time() if compute_epoch is None else compute_epoch
        self.stop=threading.Event();self.error=None;self.samples=0;self.rss_peak=0;self.used_peak=0;self.max_gap=0.;self.last=None
        require(sys.platform=='linux','runtime guard requires Linux procfs and cgroup v2')
        group=[s.split(':',2)[2] for s in Path('/proc/self/cgroup').read_text().splitlines() if s.startswith('0::')]
        require(len(group)==1,'cgroup v2 unavailable')
        self.cgroup=Path('/sys/fs/cgroup')/group[0].lstrip('/')
        maximum=(self.cgroup/'memory.max').read_text().strip()
        require(maximum!='max' and int(maximum)<=4*GIB,'no enforced <=4GiB task cgroup memory cap')
        require((self.cgroup/'cgroup.procs').read_text().split()==[str(os.getpid())],'task cgroup must contain only this process')
        self.hardcap=int(maximum)
        self.lib=ctypes.CDLL(ctypes.util.find_library('nvidia-ml') or 'libnvidia-ml.so.1')
        self._nv('nvmlInit_v2')
        self.handle=ctypes.c_void_p();self._nv('nvmlDeviceGetHandleByUUID',uuid.encode(),ctypes.byref(self.handle))
        class Memory(ctypes.Structure):_fields_=[('total',ctypes.c_ulonglong),('free',ctypes.c_ulonglong),('used',ctypes.c_ulonglong)]
        self.Memory=Memory;self.baseline=self.memory()[1]
        self.file=(self.output/sample_name).open('x')
        self.sample();self.thread=threading.Thread(target=self._loop,daemon=True);self.thread.start()
    def _nv(self,name,*args):require(getattr(self.lib,name)(*args)==0,'NVML '+name+' failed')
    def memory(self):
        value=self.Memory();self._nv('nvmlDeviceGetMemoryInfo',self.handle,ctypes.byref(value));return int(value.free),int(value.used)
    def exclusive(self):
        # Fail closed on unsupported process enumeration; never infer exclusivity from low memory.
        class Process(ctypes.Structure):
            _fields_=[('pid',ctypes.c_uint),('used',ctypes.c_ulonglong),('gpu',ctypes.c_uint),('compute',ctypes.c_uint)]
        for name in ('nvmlDeviceGetComputeRunningProcesses_v2','nvmlDeviceGetGraphicsRunningProcesses_v2'):
            count=ctypes.c_uint(64);rows=(Process*64)();self._nv(name,self.handle,ctypes.byref(count),rows)
            require(count.value<=64,'device process count overflow')
            require(all(rows[i].pid==os.getpid() for i in range(count.value)),'device not exclusive')
    def sample(self):
        now=time.monotonic();rss=int(Path('/proc/self/statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')
        free,used=self.memory();self.samples+=1;self.rss_peak=max(self.rss_peak,rss);self.used_peak=max(self.used_peak,used)
        if self.last is not None:self.max_gap=max(self.max_gap,now-self.last)
        self.last=now;self.file.write(canonical({'seconds':now-self.started,'rss':rss,'device_used':used,'device_free':free}).decode()+'\n')
        require(rss<=int(3.5*GIB),'sampled host RSS guard');require(free>=GIB,'device free reserve')
        require(used-self.baseline<=3*GIB,'sampled task board delta guard')
        require(time.time()-self.compute_epoch<=14400 and time.time()-self.stage_epoch<=28800,'wall-time cap')
    def _loop(self):
        while not self.stop.wait(.01):
            try:self.sample()
            except Exception as exc:self.error=str(exc);self.stop.set()
    def check(self,observer=None):
        require(self.error is None,self.error);require(time.monotonic()-self.last<1,'telemetry sampler stale')
        require(shutil.disk_usage(self.task).free>=20*GIB,'disk free floor')
        self.exclusive()
        if observer is not None:observer.ledger.check()
    def disk_check(self):
        task_bytes=sum(p.stat().st_size for p in self.task.rglob('*') if p.is_file())
        evidence_bytes=sum(p.stat().st_size for p in self.output.rglob('*') if p.is_file())
        require(task_bytes<32*GIB and evidence_bytes<EVIDENCE_CAP-RESERVE,'task/evidence byte cap')
        self.check()
    def close(self):
        self.stop.set();self.thread.join();self.file.flush();os.fsync(self.file.fileno());self.file.close()
        report={'samples':self.samples,'cadence_target_seconds':.01,'largest_sample_gap_seconds':self.max_gap,
                'sampled_rss_peak':self.rss_peak,'os_ru_maxrss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                'sampled_board_baseline':self.baseline,'sampled_board_peak_lower_bound':self.used_peak,
                'hard_cgroup_charged_memory_cap_bytes':self.hardcap,'cgroup':str(self.cgroup),'error':self.error,
                'process_id':os.getpid(),'cgroup_process_ids':[os.getpid()],
                'elapsed_seconds':time.monotonic()-self.started,'compute_elapsed_seconds':time.time()-self.compute_epoch,
                'stage_elapsed_seconds':time.time()-self.stage_epoch,
                'last_sample_age_seconds':time.monotonic()-self.last}
        self._nv('nvmlShutdown');return report

def read_rows(root,subject,backend,phase):
    path=Path(root)/'records'/subject/backend/(phase+'.jsonl')
    return [json.loads(line) for line in path.read_text().splitlines()]

def checked_advance(backend,kind,subject,phase,steps,ledger,guard,observer):
    guard.check(observer)
    before=int(backend.checkpoint()['state']['tick']);index=ledger.reserve(kind,subject,phase,before,steps)
    counts=None;state=None;returned=False
    try:
        if kind=='cuda':backend.stream.synchronize()
        start=time.perf_counter_ns();counts=backend.advance(steps);returned=True
        if kind=='cuda':backend.stream.synchronize()
        seconds=(time.perf_counter_ns()-start)/1e9
        state=snapshot(backend,counts);ledger.completed(index,int(state['tick']))
        if kind=='cuda':observer.live_array_peak=max(observer.live_array_peak,sum(a.nbytes for a in (*backend.device_state.values(),backend.events,backend.in_ptr,backend.in_pre,backend.in_weights)))
        guard.check(observer);return state,seconds
    except BaseException as exc:
        available={} if state is None else state.copy();capture_errors=[]
        quality='snapshot after returned advance' if state is not None else 'checkpoint at exception; counters may precede partial call'
        if state is None:
            try:available.update(backend.checkpoint()['state'])
            except BaseException as capture_error:capture_errors.append('checkpoint: '+str(capture_error))
            if kind=='cuda':
                try:
                    for name,device in backend.device_state.items():available[name]=device.copy_to_host(stream=backend.stream)
                    backend.stream.synchronize()
                except BaseException as capture_error:capture_errors.append('device download: '+str(capture_error))
        if returned:
            try:available['counts']=np.asarray(counts).copy()
            except BaseException as capture_error:capture_errors.append('returned counts: '+str(capture_error))
        receipt=capture_failure(exc,guard.output/'advance-failure-state',available,
                               {'phase':phase,'subject':subject,'backend':kind,'reserved_steps':steps,
                                'counts':'returned' if returned else 'unavailable: advance did not return',
                                'state_quality':quality,'acquisition_errors':capture_errors,'original_error':str(exc)},
                               getattr(guard,'task',None))
        raise

def experiment_subject(subject,graph,weights,root,store,ledger,guard,observer):
    from flyarena.optional_backend import create_backend
    timing=[];difference=DifferenceStats()
    def construct(kind):
        guard.check(observer);start=time.perf_counter();b=create_backend(kind,graph,weights=weights,tau_scale=1.,threshold_shift=0.)
        timing.append({'backend':kind,'phase':'construction','seconds':time.perf_counter()-start})
        b.prepare(b.binding)
        require(asdict(b.binding)==json.loads((Path(root)/'input-bindings.json').read_text())['bindings'][subject],'prospective scientific binding mismatch')
        if kind=='cuda':
            layout={key:hashlib.sha256(getattr(b,key).copy_to_host(stream=b.stream).tobytes()).hexdigest() for key in ('in_ptr','in_pre','in_weights')}
            b.stream.synchronize();path=Path(root)/'incoming-layout'/subject/(kind+'.json')
            if path.exists():require(json.loads(path.read_text())==layout,'incoming layout changed')
            else:write_json(path,layout)
        return b
    def release(b,kind):
        if kind=='cuda':b.stream.synchronize()
        # Caller drops its reference before draining pending allocations.
    def advance(b,kind,phase,steps=1):return checked_advance(b,kind,subject,phase,steps,ledger,guard,observer)
    def record(rec,b,state,steps,kind='advance'):
        return rec.append(state,kind,steps,asdict(b.binding))
    def reference(kind,tick):return store.decode(primary[kind][tick]['arrays'])
    def check(cpu,actual,exact=False):
        try:compare(cpu,actual,exact)
        except Exception:
            # Reserved failure bytes permit complete operands even at the normal payload ceiling.
            store.cap=EVIDENCE_CAP-256*1024**2
            write_json(Path(root)/'failure-operands.json',{'expected':store.encode(cpu),'actual':store.encode(actual)})
            raise
    primary={}
    for kind in ('cpu','cuda'):
        b=construct(kind);rec=Recorder(root,store,subject,kind,'warmup')
        try:
            b.reset(0);b.stimulate(0.,0.);record(rec,b,snapshot(b,np.zeros(N,dtype=np.int32)),0,'initial')
            state,seconds=advance(b,kind,'warmup');record(rec,b,state,1)
            timing.append({'backend':kind,'phase':'warmup_including_first_JIT','seconds':seconds})
            if kind=='cuda':capture_codegen(root)
        finally:rec.close()
        b.reset(0);rec=Recorder(root,store,subject,kind,'primary')
        try:
            state=snapshot(b,np.zeros(N,dtype=np.int32));record(rec,b,state,0,'initial')
            if kind=='cuda':check(reference('cpu',0),state)
            for tick in range(800):
                if tick in (0,100,300,500,700):b.stimulate(*stimulus(tick))
                state,_=advance(b,kind,'primary');record(rec,b,state,1)
                if kind=='cuda':
                    cpu=reference('cpu',tick+1);difference.add(cpu,state,tick+1);check(cpu,state)
                if tick+1==317:
                    write_json(Path(root)/'checkpoints'/subject/(kind+'.json'),{'schema':'neural-checkpoint/v1','binding':asdict(b.binding),'arrays':rec.rows[-1]['arrays']})
                if (tick+1)%25==0:guard.disk_check()
            primary[kind]=rec.rows
        finally:rec.close()
        release(b,kind);del b;gc.collect()
        if kind=='cuda':observer.drain()
    for phase in ('repeat','chunk','restore'):
        for kind in ('cpu','cuda'):
            b=construct(kind);rec=Recorder(root,store,subject,kind,phase)
            try:
                if phase=='restore':
                    saved=json.loads((Path(root)/'checkpoints'/subject/(kind+'.json')).read_text())
                    state=store.decode(saved['arrays']);checkpoint={'schema':saved['schema'],'binding':saved['binding'],'state':{k:v for k,v in state.items() if k!='counts'}}
                    for label,ticks in (('discard',range(317,330)),('suffix',range(317,800))):
                        b.restore(checkpoint);loaded=snapshot(b,state['counts']);record(rec,b,loaded,0,label+'-loaded');check(state,loaded,True)
                        for tick in ticks:
                            b.stimulate(*stimulus(tick));actual,_=advance(b,kind,'restore-'+label)
                            record(rec,b,actual,1,label);check(reference(kind,tick+1),actual,True)
                            if (tick+1)%25==0:guard.disk_check()
                else:
                    b.reset(0);initial=snapshot(b,np.zeros(N,dtype=np.int32));record(rec,b,initial,0,'initial');check(reference(kind,0),initial,True)
                    calls=CHUNKS if phase=='chunk' else tuple((t,1) for t in range(800))
                    for tick,steps in calls:
                        stimulus_seconds=0.
                        if tick in (0,100,300,500,700):
                            start=time.perf_counter_ns();b.stimulate(*stimulus(tick));stimulus_seconds=(time.perf_counter_ns()-start)/1e9
                        actual,seconds=advance(b,kind,phase,steps);record(rec,b,actual,steps)
                        expected=reference(kind,tick+steps)
                        if phase=='chunk':
                            expected['counts']=sum((store.get(primary[kind][i]['arrays']['counts']).astype(np.int64) for i in range(tick+1,tick+steps+1)),np.zeros(N,dtype=np.int64)).astype(np.int32)
                            timing.append({'backend':kind,'phase':'chunk','start_tick':tick,'steps':steps,'stimulus_seconds':stimulus_seconds,'advance_seconds':seconds})
                        check(expected,actual,True)
                        if phase=='chunk' or (tick+1)%25==0:guard.disk_check()
            finally:rec.close()
            release(b,kind);del b;gc.collect()
            if kind=='cuda':observer.drain()
    write_json(Path(root)/('timing-'+subject+'.json'),timing)
    write_json(Path(root)/('differences-'+subject+'.json'),difference.fields)


def load_policy():return json.loads(Path(__file__).with_name('cuda_fullgraph_policy.json').read_text())

def validate_transport(receipt):
    require(receipt.get('status')=='passed','64MiB transport preflight did not pass')
    attempts=receipt.get('attempts');require(type(attempts) is list and 1<=len(attempts)<=2,'transport attempts')
    if len(attempts)==2:require(attempts[0]['payload_started'] is False,'payload retry forbidden')
    final=attempts[-1]
    require(final.get('status')=='passed' and final.get('payload_started') is True and final.get('last_phase')=='download','transport completion')
    require(final.get('bytes_each_direction')==64*1024**2,'transport size')
    require(final.get('payload_sha256')=='60fe5376281a77b981ba0776f661a00043515b39e6edbaa2b08ee31751227f8a','transport payload identity')
    for key in ('upload_seconds','download_seconds'):
        value=final.get(key);require(type(value) in (int,float) and math.isfinite(value) and 0<value<=120,'transport directional deadline')
    require(receipt.get('sequence')==0 and receipt.get('neural_ticks')==0 and receipt.get('gpu_ticks')==0 and receipt.get('timeout_seconds_per_direction')==120,'transport scope')


def capture_codegen(root):
    from flyarena import cuda_ordered
    emitted={}
    for name in ('_neurons','_arrivals'):
        kernel=getattr(cuda_ordered,name)
        for signature,ptx in kernel.inspect_asm().items():
            identity=hashlib.sha256(str(signature).encode()).hexdigest()[:16]
            path=Path(root)/'ptx'/(name+'-'+identity+'.ptx');path.parent.mkdir(exist_ok=True)
            if path.exists():require(path.read_text()==ptx,'emitted PTX changed')
            else:path.write_text(ptx)
            emitted[str(path.relative_to(root))]={'signature':str(signature),'sha256':sha_file(path)}
    path=Path(root)/'ptx.json'
    if path.exists():require(json.loads(path.read_text())==emitted,'kernel specializations changed')
    else:write_json(path,emitted)

def verify_files(root,files):
    for name,expected in files.items():
        path=Path(name);require(not path.is_absolute() and '..' not in path.parts,'unsafe manifest path')
        candidate=Path(root)/path;require(candidate.is_file() and not candidate.is_symlink(),'manifest missing/nonregular file')
        require(sha_file(candidate)==expected,'file hash mismatch: '+name)

def prepare(args):
    """Stage immutable originals; the run command uses unchanged Compiler.load_weights."""
    policy=load_policy();source=Path(__file__).resolve().parents[1];package=Path(args.package)
    require(not package.exists(),'fresh package required');package.mkdir(parents=True)
    verify_files(source,policy['accepted_source_sha256'])
    graph_path=Path(args.data)/'connectome';require(sha_file(graph_path/'manifest.json')==policy['graph_manifest_sha256'],'graph manifest identity')
    manifest=json.loads((graph_path/'manifest.json').read_text());verify_files(graph_path,manifest['files'])
    require(manifest['sha256']==policy['graph_sha256'] and manifest['neuron_count']==N and manifest['edge_count']==E,'fullgraph identity')
    require(sha_file(args.subjects)==policy['subjects_sha256'],'subjects file identity')
    files={}
    def copy(origin,name):
        destination=package/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(origin,destination);files[name]=sha_file(destination)
        require(sum(p.stat().st_size for p in package.rglob('*') if p.is_file())<=GIB,'input/source package cap')
        require(shutil.disk_usage(package).free>=20*GIB,'local disk free floor')
    for name in SOURCE_NAMES:copy(source/name,'source/'+name)
    for name in ('manifest.json',*manifest['files']):copy(graph_path/name,'inputs/data/connectome/'+name)
    copy(args.subjects,'inputs/subjects.json')
    for subject,spec in policy['subjects'].items():
        artifact=Path(args.artifacts)/'artifacts'/spec['artifact_id']
        for name,key in (('manifest.json','manifest_sha256'),('mutations.npz','mutations_sha256')):
            require(sha_file(artifact/name)==spec[key],'artifact identity');copy(artifact/name,'inputs/var/artifacts/'+spec['artifact_id']+'/'+name)
    # Freeze the accepted runtime references without importing the device runtime locally.
    for name in ('environment-manifest.json','compilation-libraries.json','wheel-manifest.json'):
        require(sha_file(Path(args.accepted_evidence)/name)==policy['accepted_environment_files'][name],'accepted environment reference identity')
        copy(Path(args.accepted_evidence)/name,'environment/'+name)
    registration={'schema':SCHEMA,'files':files,'stage_started_epoch':args.stage_started_epoch,'policy_sha256':sha_file(source/'scripts/cuda_fullgraph_policy.json'),
                  'base_commit':policy['base_commit'],'scientific_ticks':0,'package_bytes':sum(p.stat().st_size for p in package.rglob('*') if p.is_file())}
    write_json(package/'registration.json',registration)
    return {'registration_sha256':sha_file(package/'registration.json'),'package_bytes':registration['package_bytes'],'scientific_ticks':0}


def verify_runtime(package,policy):
    require(sys.version_info[:3]==(3,12,3),'Python version mismatch')
    require('NUMBA_ENABLE_CUDASIM' not in os.environ,'simulator environment present')
    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS'):
        require(os.environ.get(key)=='1','one numerical thread required: '+key)
    require(os.environ.get('PYTHONDONTWRITEBYTECODE')=='1','bytecode must be disabled')
    for key in ('NUMBA_CACHE_DIR','TMPDIR','XDG_CACHE_HOME'):
        location=Path(os.environ.get(key,'/'));require(location.is_relative_to(package.parent),'cache outside task: '+key)
    expected=json.loads((package/'environment/environment-manifest.json').read_text())
    for name,version in expected['packages'].items():require(importlib.metadata.version(name)==version,'package version mismatch: '+name)
    root=Path(sys.prefix).parent
    libraries=json.loads((package/'environment/compilation-libraries.json').read_text());verify_files(root,libraries)
    wheels=json.loads((package/'environment/wheel-manifest.json').read_text())
    for name,record in wheels.items():
        candidates=[root/'wheels'/name,root/'wheelhouse'/name]
        path=next((p for p in candidates if p.is_file()),candidates[0])
        require(path.is_file() and path.stat().st_size==record['bytes'] and sha_file(path)==record['sha256'],'accepted wheel unavailable/mismatch: '+name)
        distribution=importlib.metadata.distribution(name.split('-')[0])
        with zipfile.ZipFile(path) as archive:
            records=[member for member in archive.namelist() if member.endswith('.dist-info/RECORD')]
            require(len(records)==1,'wheel RECORD identity')
            for relative,digest,length in csv.reader(io.StringIO(archive.read(records[0]).decode())):
                if not relative.endswith(('.py','.so','.bc','.pyd','.dll')):continue
                require('.data/' not in relative,'unsupported relocated importable wheel payload')
                installed=Path(distribution.locate_file(relative));require(installed.is_file(),'installed wheel payload missing')
                algorithm,encoded=digest.split('=',1);require(algorithm=='sha256','wheel payload hash algorithm')
                expected_hash=base64.urlsafe_b64decode(encoded+'='*((-len(encoded))%4)).hex()
                require(installed.stat().st_size==int(length) and sha_file(installed)==expected_hash,'installed wheel payload differs: '+relative)
    from numba import config,cuda
    require(not config.ENABLE_CUDASIM and cuda.is_available(),'actual CUDA unavailable')
    device=cuda.get_current_device();uuid=str(device.uuid)
    require(uuid==policy['device_uuid'] and list(device.compute_capability)==[8,9],'device identity')
    from numba.cuda.cudadrv import driver,runtime,nvvm
    require(list(driver.driver.get_version())==expected['driver_version'],'driver API mismatch')
    require(list(runtime.runtime.get_version())==expected['runtime_version'],'runtime API mismatch')
    require(list(nvvm.NVVM().get_version())==expected['nvvm_version'],'NVVM version mismatch')
    return expected


def run(args):
    # Transport must pass before importing any neural/backend/driver module or allocating a graph.
    receipt=json.loads(Path(args.transport).read_text());validate_transport(receipt)
    package=Path(args.package).resolve();registration_path=package/'registration.json'
    require(sha_file(registration_path)==args.registration_sha256,'unanchored registration')
    registration=json.loads(registration_path.read_text());verify_files(package,registration['files'])
    policy=load_policy();require(registration['policy_sha256']==sha_file(Path(__file__).with_name('cuda_fullgraph_policy.json')),'registered policy')
    require(Path(__file__).resolve()==package/'source/scripts/run_cuda_fullgraph.py','run registered source in place')
    require(type(registration['stage_started_epoch']) in (int,float) and math.isfinite(registration['stage_started_epoch']) and 0<=time.time()-registration['stage_started_epoch']<28800,'stage wall cap expired/invalid')
    output=package.parent/'output';output.mkdir();write_json(output/'registration.json',registration)
    write_json(output/'transport.json',receipt);write_json(output/'policy.json',policy)
    write_json(output/'runner-start.json',{'epoch':time.time(),'registration_sha256':args.registration_sha256,'neural_ticks_at_start':0})
    observer=guard=ledger=None;terminal={'status':'blocked','ticks':{'cpu':0,'cuda':0}}
    try:
        # A real hard cgroup cap and pre-context board baseline are required before CUDA import.
        guard=ResourceGuard(package.parent,output,policy['device_uuid'],registration['stage_started_epoch']);guard.check()
        environment=verify_runtime(package,policy);write_json(output/'environment.json',environment)
        observer=DriverObserver(output/'driver-allocations.jsonl');observer.install();observer.preflight();guard.check(observer)
        sys.path.insert(0,str(package/'source/src'))
        from flyarena.connectome import Connectome
        from flyarena.compiler import Compiler
        graph=Connectome(package/'inputs/data',verify=True)
        require(graph.n==N and graph.e==E and graph.manifest['sha256']==policy['graph_sha256'],'graph dimensions/identity')
        compiler=Compiler(graph);store=ObjectStore(output);ledger=TickLedger(output/'ticks.jsonl')
        constants={name:struct.pack('<d',value).hex() for name,value in {'dt':.1,'rest':-52.,'threshold':-45.,'external_scale':48.,'syn_decay':np.exp(-.1/5),'mem_decay':np.exp(-.1/20),'rate_decay':np.exp(-.1/50)}.items()}
        write_json(output/'constants.json',constants)
        imported={name:{'path':str(Path(module.__file__).resolve()),'sha256':sha_file(module.__file__)} for name,module in tuple(sys.modules.items()) if getattr(module,'__file__',None) and Path(module.__file__).is_file()}
        write_json(output/'imported-before-ticks.json',imported)
        for name,record in imported.items():
            if name=='flyarena' or name.startswith('flyarena.'):
                require(Path(record['path']).is_relative_to(package/'source/src'),'unregistered scientific module import')
        weights_by_subject={}
        for subject in SUBJECTS:
            spec=policy['subjects'][subject];weights,artifact=compiler.load_weights(spec['artifact_id'],package/'inputs/var')
            require(hashlib.sha256(weights.tobytes()).hexdigest()==spec['weights_sha256'],'compiled weight identity')
            params=artifact['phenotype']['neuron_parameters'];require(params=={'tau_scale':1.0,'threshold_shift_mv':0.0},'intrinsic parameters')
            weights_by_subject[subject]=weights
        del weights
        from flyarena.optional_backend import ScientificBinding,array_identity,digest
        from flyarena.neural import PROFILE
        graph_identity={'n':graph.n,'ids':array_identity(graph.ids),'indptr':array_identity(graph.indptr),'post':array_identity(graph.post),'groups':{key:array_identity(value) for key,value in graph.groups.items()}}
        bindings={subject:asdict(ScientificBinding('neural-binding/v1',digest(graph_identity),policy['subjects'][subject]['weights_sha256'],digest(PROFILE),policy['accepted_source_sha256']['src/flyarena/neural.py'],20.,-45.)) for subject in SUBJECTS}
        write_json(output/'input-bindings.json',{'canonical_graph_manifest_sha256':policy['graph_manifest_sha256'],'canonical_graph_sha256':policy['graph_sha256'],'bindings':bindings})
        for subject in SUBJECTS:
            experiment_subject(subject,graph,weights_by_subject.pop(subject),output,store,ledger,guard,observer);gc.collect()
        require(ledger.counts=={'cpu':5794,'cuda':5794},'runner exact tick accounting')
        terminal.update(status='runner-complete-unverified',ticks=ledger.counts,evidence_io_seconds=store.io_seconds)
    except Exception as exc:
        terminal.update(error_type=type(exc).__name__,error=str(exc))
        if hasattr(exc,'failure_capture'):terminal['failure_capture']=exc.failure_capture
        raise
    finally:
        if ledger is not None:
            accounting=ledger.summary();terminal.update(tick_accounting=accounting,ticks_reserved=accounting['reserved'],ticks_completed=accounting['completed'],ticks=accounting['completed'],unresolved_reserved_ticks=accounting['unresolved']);ledger.close()
        if observer is not None:terminal['driver_allocation']=observer.ledger.report();terminal['live_device_arrays_sampled_peak']=observer.live_array_peak;observer.close()
        if guard is not None:
            try:terminal['resources']=guard.close()
            except Exception as exc:terminal.update(status='blocked',resource_closure_error=str(exc))
        write_json(output/'runner-terminal.json',terminal)
    return terminal


def main():
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='command',required=True)
    staging=commands.add_parser('prepare');staging.add_argument('--package',required=True);staging.add_argument('--data',required=True);staging.add_argument('--artifacts',required=True)
    staging.add_argument('--subjects',required=True);staging.add_argument('--accepted-evidence',required=True);staging.add_argument('--stage-started-epoch',type=float,required=True)
    execute=commands.add_parser('run');execute.add_argument('--package',required=True);execute.add_argument('--registration-sha256',required=True);execute.add_argument('--transport',required=True)
    args=parser.parse_args();print(json.dumps(prepare(args) if args.command=='prepare' else run(args),sort_keys=True,allow_nan=False))

if __name__=='__main__':main()
