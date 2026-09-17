"""Independent fullgraph byte reconstruction and coverage checks; oracle mode is one-shot."""
from __future__ import annotations
import argparse
from collections import OrderedDict
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import zlib
import numpy as np

N=165122
FIELDS={'v','current','refractory','delay','external','rates','tick','total_spikes','counts'}
EXACT={'counts','refractory','tick','total_spikes'}

def need(condition,message):
    if not condition:raise ValueError(message)

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def unique_pairs(pairs):
    out={}
    for key,value in pairs:
        need(key not in out,'duplicate JSON key');out[key]=value
    return out

def parse(raw):
    def invalid(value):raise ValueError('nonfinite JSON constant '+value)
    return json.loads(raw,object_pairs_hook=unique_pairs,parse_constant=invalid)

def exclusive_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as f:f.write(canonical(value)+b'\n');f.flush()

class Decoder:
    """Does not import the runner's codec, schema validator or comparison implementation."""
    def __init__(self,root,n=N):
        self.root=Path(root);self.n=n;self.cache=OrderedDict();self.cache_size=0;self.used=set()
    def array(self,key):
        need(type(key) is str and len(key)==64 and set(key)<=set('0123456789abcdef'),'non-object or chained reference')
        self.used.add(key)
        if key in self.cache:self.cache.move_to_end(key);return self.cache[key].copy()
        path=self.root/'objects'/key[:2]/(key+'.bin')
        need(path.is_file() and not path.is_symlink(),'missing object')
        need(path.stat().st_size<=self.n*8+4096,'object size bound')
        with path.open('rb') as f:
            head=f.readline(4097);need(head.endswith(b'\n') and len(head)<=4096,'header bound');payload=f.read(self.n*8+1)
        header=parse(head)
        need(type(header) is dict and set(header)=={'dtype','shape','bytes','codec','raw_sha256'},'object header keys')
        dtype=np.dtype(header['dtype']);shape=header['shape']
        need(type(header['dtype']) is str and dtype.str==header['dtype'],'canonical dtype')
        need(dtype.kind in 'fiu' and dtype.itemsize in (4,8),'object dtype')
        need(type(shape) is list and len(shape)<=1 and all(type(d) is int and 0<=d<=self.n for d in shape),'object shape')
        length=math.prod(shape)*dtype.itemsize
        need(type(header['bytes']) is int and header['bytes']==length and length<=self.n*8,'raw length bound')
        if header['codec']=='raw':raw=payload
        elif header['codec']=='zlib':
            decompressor=zlib.decompressobj();raw=decompressor.decompress(payload,length+1)
            need(decompressor.eof and not decompressor.unused_data and not decompressor.unconsumed_tail,'compressed framing/overrun')
        else:raise ValueError('unknown codec')
        need(len(raw)==length and hashlib.sha256(raw).hexdigest()==header['raw_sha256'],'raw integrity')
        descriptor={k:header[k] for k in ('dtype','shape','bytes')}
        need(hashlib.sha256(canonical(descriptor)+b'\0'+raw).hexdigest()==key,'object address')
        value=np.frombuffer(raw,dtype=dtype).reshape(shape).copy()
        self.cache[key]=value;self.cache_size+=value.nbytes
        while self.cache_size>32*1024**2:
            _,old=self.cache.popitem(last=False);self.cache_size-=old.nbytes
        return value.copy()
    def state(self,refs,steps=None):
        need(type(refs) is dict and set(refs)==FIELDS,'state reference keys')
        need(type(refs['delay']) is list and len(refs['delay'])==19,'complete delay ring')
        out={k:np.stack([self.array(v) for v in ref]) if k=='delay' else self.array(ref) for k,ref in refs.items()}
        validate(out,self.n,steps);return out

def validate(state,n,steps=None):
    need(set(state)==FIELDS,'state keys')
    for key,value in state.items():
        dtype='<i4' if key in ('counts','refractory') else '<i8' if key in ('tick','total_spikes') else '<f8'
        shape=() if key in ('tick','total_spikes') else (19,n) if key=='delay' else (n,)
        need(isinstance(value,np.ndarray) and value.dtype.str==dtype and value.shape==shape,'state dtype/shape '+key)
        need(np.isfinite(value).all(),'nonfinite state '+key)
    need(np.all((state['refractory']>=0)&(state['refractory']<=22)),'refractory range')
    need(np.all(state['rates']>=0) and int(state['tick'])>=0 and int(state['total_spikes'])>=0,'state bounds')
    need(np.all(state['counts']>=0),'negative events')
    if steps is not None:need(np.all(state['counts']<=steps),'event range')

def compare(cpu,cuda,exact=False):
    validate(cpu,len(cpu['v']));validate(cuda,len(cpu['v']))
    for key in sorted(FIELDS):
        if exact or key in EXACT:np.testing.assert_array_equal(cpu[key],cuda[key],err_msg=key)
        else:np.testing.assert_allclose(cpu[key],cuda[key],atol=1e-10,rtol=1e-12,err_msg=key)

def grid(phase):
    if phase=='warmup':return [('initial',0,0),('advance',1,1)]
    if phase in ('primary','repeat'):return [('initial',0,0)]+[('advance',1,t) for t in range(1,801)]
    if phase=='chunk':
        rows=[('initial',0,0)];tick=0
        for length in (100,200,200,200,100):
            for steps in (7,19,length-26):tick+=steps;rows.append(('advance',steps,tick))
        return rows
    if phase=='restore':return [('discard-loaded',0,317)]+[('discard',1,t) for t in range(318,331)]+[('suffix-loaded',0,317)]+[('suffix',1,t) for t in range(318,801)]
    raise ValueError('unknown phase')

def read_phase(root,subject,backend,phase,binding=None):
    path=Path(root)/'records'/subject/backend/(phase+'.jsonl')
    need(path.stat().st_size<=32*1024**2,'phase metadata size bound')
    rows=[parse(line) for line in path.read_text().splitlines()];expected=grid(phase)
    need(len(rows)==len(expected),'phase coverage '+phase)
    for index,(row,(kind,steps,tick)) in enumerate(zip(rows,expected)):
        need(type(row) is dict and set(row)=={'index','kind','steps','tick','binding','arrays'},'record fields')
        need(type(row['index']) is int and row['index']==index and type(row['steps']) is int and type(row['tick']) is int,'record integer fields')
        need((row['kind'],row['steps'],row['tick'])==(kind,steps,tick),'record grid')
        if binding is not None:need(row['binding']==binding,'scientific binding')
    return rows

def check_tick_ledger(path,oracle=False):
    rows=[parse(line) for line in Path(path).read_text().splitlines()];entries=[];completed=set();pending=None
    for row in rows:
        if row.get('state')=='reserved':
            need(set(row)=={'index','backend','subject','phase','before_tick','steps','state'},'reservation fields')
            need(type(row['index']) is int and row['index']==len(entries) and pending is None,'reservation index/order')
            need(type(row['before_tick']) is int and type(row['steps']) is int and row['before_tick']>=0 and row['steps']>0,'reservation integer bounds')
            entries.append(row);pending=row['index']
        else:
            need(set(row)=={'index','state','after_tick'} and row['state']=='completed','completion fields')
            i=row['index'];need(type(i) is int and 0<=i<len(entries) and i not in completed,'completion index')
            need(i==pending and type(row['after_tick']) is int and row['after_tick']==entries[i]['before_tick']+entries[i]['steps'],'completion tick/order');completed.add(i);pending=None
    need(len(completed)==len(entries),'unresolved attempted steps')
    expected=[]
    for subject in ('wt','mutant'):
        if oracle:
            expected.extend((subject,'cpu','oracle',t,1) for t in range(800));continue
        for backend in ('cpu','cuda'):expected.extend([(subject,backend,'warmup',0,1)]+[(subject,backend,'primary',t,1) for t in range(800)])
        for phase in ('repeat','chunk','restore'):
            for backend in ('cpu','cuda'):
                if phase=='restore':
                    expected.extend((subject,backend,'restore-discard',t,1) for t in range(317,330))
                    expected.extend((subject,backend,'restore-suffix',t,1) for t in range(317,800))
                else:expected.extend((subject,backend,phase,tick-steps,steps) for _,steps,tick in grid(phase) if steps)
    observed=[(e['subject'],e['backend'],e['phase'],e['before_tick'],e['steps']) for e in entries]
    need(observed==expected,'exact phase/tick execution ledger')
    return {backend:sum(e['steps'] for e in entries if e['backend']==backend) for backend in ('cpu','cuda')}

def verify_manifest(root,files):
    for name,digest in files.items():
        relative=Path(name);need(not relative.is_absolute() and '..' not in relative.parts,'unsafe manifest path')
        path=Path(root)/name;need(path.is_file() and not path.is_symlink() and sha(path)==digest,'manifest mismatch: '+name)

def expected_binding(package,subject,policy):
    data=package/'inputs/data/connectome'
    def identity(a):return {'dtype':a.dtype.str,'shape':list(a.shape),'sha256':hashlib.sha256(a.tobytes()).hexdigest()}
    arrays={key:np.load(data/(key+'.npy'),mmap_mode='r',allow_pickle=False) for key in ('ids','indptr','post')}
    with np.load(data/'groups.npz',allow_pickle=False) as groups:
        graph={'n':N,**{key:identity(value) for key,value in arrays.items()},'groups':{key:identity(groups[key]) for key in groups.files}}
    spec=policy['subjects'][subject];artifact=parse((package/'inputs/var/artifacts'/spec['artifact_id']/'manifest.json').read_bytes())
    return {'schema':'neural-binding/v1','graph_sha256':hashlib.sha256(canonical(graph)).hexdigest(),'weights_sha256':spec['weights_sha256'],
            'model_sha256':hashlib.sha256(canonical(artifact['phenotype']['model'])).hexdigest(),
            'oracle_sha256':policy['accepted_source_sha256']['src/flyarena/neural.py'],'tau_ms':20.,'threshold_mv':-45.,'sensor_id':'bilateral-current-v2'}

def verify_artifacts(package,root,registration_sha256):
    package=Path(package);root=Path(root)
    need(sha(package/'registration.json')==registration_sha256,'registration anchor')
    registration=parse((package/'registration.json').read_bytes());verify_manifest(package,registration['files'])
    need(sha(root/'registration.json')==sha(package/'registration.json'),'retained registration')
    policy=parse((package/'source/scripts/cuda_fullgraph_policy.json').read_bytes())
    need(sha(package/'source/scripts/cuda_fullgraph_policy.json')==registration['policy_sha256'],'frozen policy')
    verify_manifest(package/'source',policy['accepted_source_sha256'])
    need(parse((root/'policy.json').read_bytes())==policy,'retained policy')
    need(parse((root/'runner-terminal.json').read_bytes())['status']=='runner-complete-unverified','runner not complete')
    need(parse((root/'environment.json').read_bytes())==parse((package/'environment/environment-manifest.json').read_bytes()),'runtime environment identity')
    verify_resources(root)
    decoder=Decoder(root);observations=0;bindings={};bitwise_equal=True
    for subject in ('wt','mutant'):
        binding=expected_binding(package,subject,policy);bindings[subject]=binding;primary={}
        frozen=parse((root/'input-bindings.json').read_bytes());need(frozen['bindings'][subject]==binding and frozen['canonical_graph_manifest_sha256']==policy['graph_manifest_sha256'] and frozen['canonical_graph_sha256']==policy['graph_sha256'],'prospective input binding')
        for backend in ('cpu','cuda'):
            primary[backend]=read_phase(root,subject,backend,'primary',binding)
            previous=None
            for row in primary[backend]:
                state=decoder.state(row['arrays'],row['steps']);need(int(state['tick'])==row['tick'],'array/metadata tick')
                if previous is None:need(int(state['total_spikes'])==0 and np.all(state['counts']==0),'initial counters')
                else:need(int(state['total_spikes'])==previous+int(state['counts'].sum(dtype=np.int64)),'event total identity')
                previous=int(state['total_spikes']);observations+=1
            checkpoint=parse((root/'checkpoints'/subject/(backend+'.json')).read_bytes())
            need(set(checkpoint)=={'schema','binding','arrays'} and checkpoint['schema']=='neural-checkpoint/v1' and checkpoint['binding']==binding,'checkpoint sidecar')
            compare(decoder.state(checkpoint['arrays']),decoder.state(primary[backend][317]['arrays']),True)
            for phase in ('warmup','repeat','chunk','restore'):
                rows=read_phase(root,subject,backend,phase,binding)
                for row in rows:
                    state=decoder.state(row['arrays'],row['steps'] if row['steps'] else None);need(int(state['tick'])==row['tick'],'array/metadata tick')
                    expected=decoder.state(primary[backend][row['tick']]['arrays'])
                    if phase=='chunk' and row['steps']:
                        counts=np.zeros(N,dtype=np.int64)
                        for tick in range(row['tick']-row['steps']+1,row['tick']+1):counts+=decoder.array(primary[backend][tick]['arrays']['counts'])
                        expected['counts']=counts.astype(np.int32)
                    compare(expected,state,True);observations+=1
        for tick in range(801):
            cpu=decoder.state(primary['cpu'][tick]['arrays']);cuda=decoder.state(primary['cuda'][tick]['arrays']);compare(cpu,cuda)
            bitwise_equal=bitwise_equal and all(cpu[key].tobytes()==cuda[key].tobytes() for key in FIELDS)
    expected_records={str(Path('records')/s/b/(p+'.jsonl')) for s in ('wt','mutant') for b in ('cpu','cuda') for p in ('warmup','primary','repeat','chunk','restore')}
    need({str(p.relative_to(root)) for p in (root/'records').rglob('*') if p.is_file()}==expected_records,'unexpected phase files')
    objects={p.stem for p in (root/'objects').rglob('*.bin')}
    need(objects==decoder.used,'unreferenced or missing objects')
    counts=check_tick_ledger(root/'ticks.jsonl');need(counts=={'cpu':5794,'cuda':5794},'runner totals')
    return {'status':'artifact-verified','observations':observations,'runner_ticks':counts,'new_neural_ticks':0,'bindings':bindings,'primary_bitwise_equal':bitwise_equal,
            'claim':'full arrays/events reconstructed; no oracle replay in artifact-only mode'}


def verify_resource_samples(root,report,sample_name):
    """Reconstruct either process's resource evidence independently of runner code."""
    gib=1024**3
    def number(value,label):
        need(type(value) in (int,float) and math.isfinite(value) and value>=0,label)
        return value
    need(report['error'] is None,'resource monitor error')
    for key in ('hard_cgroup_charged_memory_cap_bytes','os_ru_maxrss_bytes','sampled_board_baseline',
                'samples','sampled_rss_peak','sampled_board_peak_lower_bound'):
        need(type(report[key]) is int and report[key]>=0,'resource integer '+key)
    need(0<report['hard_cgroup_charged_memory_cap_bytes']<=4*gib,'host hard cap')
    need(report['os_ru_maxrss_bytes']<=4*gib,'OS RSS peak cap')
    group=report['cgroup'];need(type(group) is str and Path(group).is_relative_to('/sys/fs/cgroup') and group==str(Path(group)) and '..' not in Path(group).parts,'cgroup identity')
    need(type(report['process_id']) is int and report['process_id']>0 and report['cgroup_process_ids']==[report['process_id']],'exclusive cgroup identity')
    need(number(report['cadence_target_seconds'],'cadence target')==.01,'cadence target')
    elapsed=number(report['elapsed_seconds'],'elapsed time')
    compute=number(report['compute_elapsed_seconds'],'compute time');stage=number(report['stage_elapsed_seconds'],'stage time')
    age=number(report['last_sample_age_seconds'],'last sample age')
    need(elapsed<=compute<=14400 and compute<=stage<=28800 and age<1,'resource wall/cadence cap')
    count=0;rss_peak=0;used_peak=0;last=None;gap=0.
    with (Path(root)/sample_name).open() as stream:
        for line in stream:
            need(line.endswith('\n'),'partial resource sample')
            row=parse(line);need(set(row)=={'seconds','rss','device_used','device_free'},'resource sample fields')
            seconds=number(row['seconds'],'sample time')
            need(seconds<=elapsed and (seconds<1 if last is None else seconds>=last),'sample time/order')
            if last is not None:gap=max(gap,seconds-last)
            last=seconds;count+=1
            for key in ('rss','device_used','device_free'):
                need(type(row[key]) is int and row[key]>=0,'sample memory integer')
            need(row['rss']<=int(3.5*gib) and row['device_free']>=gib,'sample memory guard')
            need(row['device_used']-report['sampled_board_baseline']<=3*gib,'sample board delta')
            rss_peak=max(rss_peak,row['rss']);used_peak=max(used_peak,row['device_used'])
    need(count==report['samples'] and count>0 and rss_peak==report['sampled_rss_peak'] and used_peak==report['sampled_board_peak_lower_bound'],'sample summary')
    need(rss_peak<=report['os_ru_maxrss_bytes'],'OS/sample peak consistency')
    need(gap<1 and math.isclose(gap,number(report['largest_sample_gap_seconds'],'sample gap'),abs_tol=1e-6),'sample cadence summary')
    need(elapsed-last<1 and math.isclose(elapsed-last,age,abs_tol=.001),'last sample coverage')
    return report

def verify_oracle_resources(root):
    root=Path(root);terminal=parse((root/'oracle-terminal.json').read_bytes())
    return verify_resource_samples(root,terminal['resources'],'oracle-resource-samples.jsonl')

def verify_resources(root):
    root=Path(root);terminal=parse((root/'runner-terminal.json').read_bytes())
    verify_resource_samples(root,terminal['resources'],'resource-samples.jsonl')
    live={};current=peak=allocations=frees=0
    with (root/'driver-allocations.jsonl').open() as stream:
        for line in stream:
            row=parse(line);need(set(row)=={'event','address','bytes','current'},'allocation event fields')
            address=row['address'];size=row['bytes'];need(type(address) is int and address>0 and type(size) is int and size>0,'allocation value')
            if row['event']=='allocate':
                need(address not in live,'allocation address reuse');live[address]=size;current+=size;allocations+=1
            elif row['event']=='free':
                need(address in live and live.pop(address)==size,'untracked/size-mismatched free');current-=size;frees+=1
            else:raise ValueError('allocation event type')
            peak=max(peak,current);need(current==row['current'] and peak<=2*1024**3,'allocation cap/accounting')
    recorded=terminal['driver_allocation']
    need(not live and current==recorded['current_requested_bytes']==0 and peak==recorded['peak_requested_bytes'],'allocation final/peak')
    need(allocations==recorded['allocations'] and frees==recorded['actual_frees'],'allocation event counts')


def verify_inventory(root,digest):
    root=Path(root);need(sha(root/'inventory.json')==digest,'inventory external anchor')
    inventory=parse((root/'inventory.json').read_bytes());need(set(inventory)=={'schema','files'} and inventory['schema']=='fullgraph-inventory/v1','inventory schema')
    actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p!=root/'inventory.json'}
    need(actual==set(inventory['files']),'inventory exact file set')
    for name,record in inventory['files'].items():
        path=root/name;need(not path.is_symlink() and path.stat().st_size==record['bytes'] and sha(path)==record['sha256'],'inventory file integrity')
    return inventory


def oracle(args):
    """Only this mode imports the unchanged CPU backend. Exclusive marker forbids a replay."""
    import run_cuda_fullgraph as runner
    root=Path(args.output);package=Path(args.package)
    # Claim the one attempt before any recurrence; a failed attempt cannot be restarted.
    exclusive_json(root/'oracle-start.json',{'epoch':time.time(),'registration_sha256':args.registration_sha256,'maximum_ticks':1600})
    ledger=guard=None;result={'status':'blocked','new_neural_ticks':0};failure=None;replay_complete=False
    try:
        policy=runner.load_policy();registration=parse((package/'registration.json').read_bytes())
        compute_started=parse((root/'runner-start.json').read_bytes())['epoch']
        need(time.time()-compute_started<14400,'runner plus verifier wall cap')
        guard=runner.ResourceGuard(package.parent,root,policy['device_uuid'],registration['stage_started_epoch'],sample_name='oracle-resource-samples.jsonl',compute_epoch=compute_started)
        result=verify_artifacts(package,root,args.registration_sha256);result['status']='blocked'
        runner.verify_runtime(package,policy);sys.path.insert(0,str(package/'source/src'))
        from flyarena.connectome import Connectome
        from flyarena.compiler import Compiler
        from flyarena.optional_backend import CheckedCPUBackend
        graph=Connectome(package/'inputs/data',verify=True);compiler=Compiler(graph);decoder=Decoder(root)
        ledger=runner.TickLedger(root/'oracle-ticks.jsonl',{'cpu':1600,'cuda':0})
        for subject in ('wt','mutant'):
            spec=policy['subjects'][subject];weights,_=compiler.load_weights(spec['artifact_id'],package/'inputs/var')
            need(hashlib.sha256(weights.tobytes()).hexdigest()==spec['weights_sha256'],'oracle weights')
            backend=CheckedCPUBackend(graph,weights=weights,tau_scale=1.,threshold_shift=0.);backend.reset(0)
            cpu=read_phase(root,subject,'cpu','primary',result['bindings'][subject]);cuda=read_phase(root,subject,'cuda','primary',result['bindings'][subject])
            initial=backend.checkpoint()['state'];initial['counts']=np.zeros(N,dtype=np.int32)
            try:compare(initial,decoder.state(cpu[0]['arrays']),True)
            except BaseException as exc:
                runner.capture_failure(exc,root/'oracle-failure',initial,{'subject':subject,'tick':0,'cpu':cpu[0]['arrays'],'expected_object_root':'..','original_error':str(exc)},package.parent)
                raise
            for tick in range(800):
                guard.check();need(time.time()-compute_started<14400,'compute wall cap')
                if tick in (0,100,300,500,700):
                    pair=(0.,0.) if tick in (0,700) else (1.,0.) if tick==100 else (0.,1.) if tick==300 else (1.,1.)
                    backend.stimulate(*pair)
                state,_=runner.checked_advance(backend,'cpu',subject,'oracle',1,ledger,guard,None)
                try:compare(state,decoder.state(cpu[tick+1]['arrays']),True);compare(state,decoder.state(cuda[tick+1]['arrays']))
                except BaseException as exc:
                    runner.capture_failure(exc,root/'oracle-failure',state,
                                           {'subject':subject,'tick':tick+1,'cpu':cpu[tick+1]['arrays'],
                                            'cuda':cuda[tick+1]['arrays'],'expected_object_root':'..','original_error':str(exc)},package.parent)
                    raise
            del backend,weights
        check_tick_ledger(root/'oracle-ticks.jsonl',oracle=True)
        replay_complete=True
    except BaseException as exc:
        failure=exc;result.update(status='blocked',error_type=type(exc).__name__,error=str(exc))
        if hasattr(exc,'failure_capture'):result['failure_capture']=exc.failure_capture
    finally:
        accounting={'reserved':{'cpu':0,'cuda':0},'completed':{'cpu':0,'cuda':0},
                    'unresolved':{'cpu':0,'cuda':0},'accounting_complete':True,'actual_executed_ticks':{'cpu':0,'cuda':0}}
        if ledger is not None:
            accounting=ledger.summary()
            try:ledger.close()
            except BaseException as exc:
                result['ledger_closure_error']=str(exc)
                if failure is None:failure=exc
        result.update(tick_accounting=accounting,reserved_oracle_ticks=accounting['reserved'],
                      completed_oracle_ticks=accounting['completed'],unresolved_oracle_ticks=accounting['unresolved'],
                      new_neural_ticks=accounting['completed']['cpu'],actual_oracle_ticks=accounting['actual_executed_ticks'])
        if guard is not None:
            try:
                result['resources']=guard.close()
                verify_resource_samples(root,result['resources'],'oracle-resource-samples.jsonl')
            except BaseException as exc:
                result['resource_closure_error']=type(exc).__name__+': '+str(exc)
                if failure is None:failure=exc
        if failure is None and replay_complete:
            try:
                need(accounting['accounting_complete'] and accounting['completed']=={'cpu':1600,'cuda':0}
                     and accounting['unresolved']=={'cpu':0,'cuda':0},'final oracle accounting incomplete')
            except BaseException as exc:failure=exc
        if failure is None and replay_complete:
            result.update(status='oracle-and-artifact-verified',total_cpu_ticks=7394,total_cuda_ticks=5794,
                          claim='registered 800-tick fullgraph recurrence policy only; no embodiment or public admission')
        else:
            result['status']='blocked'
            if failure is not None:result.update(error_type=type(failure).__name__,error=str(failure))
        exclusive_json(root/'oracle-terminal.json',result)
    if failure is not None:raise failure
    need(result['status']=='oracle-and-artifact-verified','oracle did not complete')
    files={str(p.relative_to(root)):{'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(root.rglob('*')) if p.is_file()}
    exclusive_json(root/'inventory.json',{'schema':'fullgraph-inventory/v1','files':files})
    result['inventory_sha256']=sha(root/'inventory.json');return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=('artifact-only','oracle'))
    parser.add_argument('--package',required=True);parser.add_argument('--output',required=True);parser.add_argument('--registration-sha256',required=True)
    parser.add_argument('--inventory-sha256');args=parser.parse_args()
    need(Path(__file__).resolve()==Path(args.package).resolve()/'source/scripts/verify_cuda_fullgraph.py','verify registered source in place')
    if args.mode=='oracle':result=oracle(args)
    else:
        need(args.inventory_sha256 is not None,'artifact-only requires externally anchored closed inventory')
        verify_inventory(args.output,args.inventory_sha256);result=verify_artifacts(args.package,args.output,args.registration_sha256)
        need(parse((Path(args.output)/'oracle-terminal.json').read_bytes())['status']=='oracle-and-artifact-verified','missing completed oracle')
        check_tick_ledger(Path(args.output)/'oracle-ticks.jsonl',oracle=True)
        verify_oracle_resources(args.output)
    print(json.dumps(result,sort_keys=True,allow_nan=False))

if __name__=='__main__':main()
