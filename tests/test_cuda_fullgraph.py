"""Nonphysical tests: hand-authored bytes and accounting only; no backend imports."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import zlib
import numpy as np
import pytest

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
def module(name):
    spec=importlib.util.spec_from_file_location(name,SCRIPTS/(name+'.py'));result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
runner=module('run_cuda_fullgraph');verifier=module('verify_cuda_fullgraph')

def state(n=3,tick=0):
    result={key:np.zeros(n,dtype='<f8') for key in ('v','current','external','rates')}
    result.update(refractory=np.zeros(n,dtype='<i4'),counts=np.zeros(n,dtype='<i4'),delay=np.arange(19*n,dtype='<f8').reshape(19,n),tick=np.array(tick,dtype='<i8'),total_spikes=np.array(0,dtype='<i8'))
    return result

@pytest.mark.parametrize('dtype',['<f8','>f8','<i4','>i4','<i8','>i8'])
def test_roundtrip_dtype_shape_bytes(tmp_path,dtype):
    store=runner.ObjectStore(tmp_path,n=3);a=np.array([-1,0,1],dtype=dtype);key=store.put(a)
    for decoded in (runner.ObjectStore(tmp_path,n=3,readonly=True).get(key),verifier.Decoder(tmp_path,n=3).array(key)):
        assert decoded.dtype.str==a.dtype.str and decoded.shape==a.shape and decoded.tobytes()==a.tobytes()

def test_all_delay_rows_and_scalars(tmp_path):
    original=state();store=runner.ObjectStore(tmp_path,n=3);refs=store.encode(original)
    assert len(refs['delay'])==19 and len(set(refs['delay']))==19
    for actual in (runner.ObjectStore(tmp_path,n=3,readonly=True).decode(refs),verifier.Decoder(tmp_path,n=3).state(refs)):
        for key in original:assert actual[key].dtype==original[key].dtype and actual[key].shape==original[key].shape and actual[key].tobytes()==original[key].tobytes()

def test_signed_zero_distinct_objects_but_same_runtime_equal(tmp_path):
    a=state();b=state();b['v'][0]=-0.
    store=runner.ObjectStore(tmp_path,n=3);ar=store.encode(a);br=store.encode(b)
    assert ar['v']!=br['v'];runner.compare(a,b,True);verifier.compare(a,b,True)
    stats=runner.DifferenceStats();stats.add(a,b,7)
    assert stats.fields['v']['numerically_different_elements']==0 and stats.fields['v']['first_tick']==7

def test_scalar_signed_zero_diagnostic():
    # Scalar floats are valid codec objects; DifferenceStats also handles them without a view error.
    stats=runner.DifferenceStats();stats.add({'x':np.array(0.)},{'x':np.array(-0.)},0)
    assert stats.fields['x']['first_flat_index']==0 and stats.fields['x']['max_ulp']==1

def test_tolerance_orientation_is_cpu_first():
    a=state();b=state();a['v'][0]=100.;b['v'][0]=100.0000000002
    # The public policy implementation is tested against NumPy's explicitly ordered call.
    for compare in (runner.compare,verifier.compare):
        expected=True
        try:np.testing.assert_allclose(a['v'],b['v'],atol=1e-10,rtol=1e-12)
        except AssertionError:expected=False
        if expected:compare(a,b)
        else:
            with pytest.raises(AssertionError):compare(a,b)
    a['counts'][0]=1
    with pytest.raises(AssertionError):runner.compare(a,b)

def test_numeric_diagnostics_include_operands_and_infinite_relative():
    stats=runner.DifferenceStats();a=state();b=state();a['current'][1]=1e-13;stats.add(a,b,12)
    d=stats.fields['current'];assert d['first_cpu']==1e-13 and d['first_cuda']==0. and d['relative_infinite']
    json.dumps(stats.fields,allow_nan=False)

@pytest.mark.parametrize('damage',['corrupt','truncate','missing','extra','bomb','header','trailing_zlib'])
def test_reject_damaged_object_independently(tmp_path,damage):
    store=runner.ObjectStore(tmp_path,n=3);key=store.put(np.zeros(3,dtype='<f8'));path=store._path(key)
    header,payload=path.read_bytes().split(b'\n',1);meta=json.loads(header)
    if damage=='corrupt':path.write_bytes(header+b'\n'+payload[:-1]+bytes([payload[-1]^1]))
    elif damage=='truncate':path.write_bytes(header+b'\n'+payload[:-2])
    elif damage=='missing':path.unlink()
    elif damage=='extra':meta['extra']=1;path.write_bytes(runner.canonical(meta)+b'\n'+payload)
    elif damage=='bomb':path.write_bytes(header+b'\n'+zlib.compress(b'X'*10000))
    elif damage=='header':path.write_bytes(b'x'*4097+b'\n')
    else:path.write_bytes(header+b'\n'+payload+b'extra')
    for read in (lambda:runner.ObjectStore(tmp_path,n=3,readonly=True).get(key),lambda:verifier.Decoder(tmp_path,n=3).array(key)):
        with pytest.raises((ValueError,zlib.error)):read()

@pytest.mark.parametrize('change',['missing','extra','delay_rows','cycle','dtype','nonfinite'])
def test_state_refusal(tmp_path,change):
    store=runner.ObjectStore(tmp_path,n=3);refs=store.encode(state())
    if change=='missing':del refs['v']
    elif change=='extra':refs['surprise']=refs['v']
    elif change=='delay_rows':refs['delay'].pop()
    elif change=='cycle':refs['v']={'base':refs['v']}
    elif change=='dtype':refs['v']=store.put(np.zeros(3,dtype='<i4'))
    else:refs['v']=store.put(np.array([np.nan,0.,0.]))
    for read in (lambda:runner.ObjectStore(tmp_path,n=3,readonly=True).decode(refs),lambda:verifier.Decoder(tmp_path,n=3).state(refs)):
        with pytest.raises(ValueError):read()

def test_fresh_writer_budget_and_prefix(tmp_path):
    store=runner.ObjectStore(tmp_path,n=3,cap=200);a=np.array([1.,2.,3.]);key=store.put(a);before=store.bytes
    assert store.put(a)==key and store.bytes==before
    with pytest.raises(ValueError):store.put(a+4)
    assert store.get(key).tobytes()==a.tobytes()
    with pytest.raises(ValueError):runner.ObjectStore(tmp_path,n=3)

def test_tick_ledger_failed_advance_preserves_reservation(tmp_path):
    ledger=runner.TickLedger(tmp_path/'ticks.jsonl',{'cpu':2,'cuda':0});i=ledger.reserve('cpu','wt','primary',0,1)
    with pytest.raises(ValueError):ledger.completed(i,2)
    assert ledger.entries[0]['state']=='reserved'
    ledger.completed(i,1);ledger.reserve('cpu','wt','primary',1,1)
    with pytest.raises(ValueError):ledger.reserve('cpu','wt','primary',2,1)
    ledger.close();rows=[json.loads(x) for x in (tmp_path/'ticks.jsonl').read_text().splitlines()]
    assert [r['state'] for r in rows]==['reserved','completed','reserved']

def test_phase_schedule_exact_budget():
    assert sum(steps for _,steps in runner.CHUNKS)==800 and len(runner.CHUNKS)==15
    for start,steps in runner.CHUNKS:assert len({runner.stimulus(t) for t in range(start,start+steps)})==1
    assert [runner.stimulus(t) for t in (0,99,100,299,300,499,500,699,700,799)]==[(0,0),(0,0),(1,0),(1,0),(0,1),(0,1),(1,1),(1,1),(0,0),(0,0)]
    total=sum(steps for phase in ('warmup','primary','repeat','chunk','restore') for _,steps,_ in verifier.grid(phase))
    assert total==2897 and total*2==5794 and total*4+1600==13188
    for value in (-1,800,True):
        with pytest.raises(ValueError):runner.stimulus(value)

def test_recorder_failure_prefix_and_loaded_counts(tmp_path):
    store=runner.ObjectStore(tmp_path,n=3);record=runner.Recorder(tmp_path,store,'wt','cpu','restore')
    first=state(tick=317);first['counts'][0]=1;record.append(first,'discard-loaded',0,{'id':'fixed'})
    bad=state(tick=318);bad['counts'][0]=2
    with pytest.raises(ValueError):record.append(bad,'discard',1,{'id':'fixed'})
    record.close();rows=[json.loads(x) for x in record.path.read_text().splitlines()]
    assert len(rows)==1 and verifier.Decoder(tmp_path,n=3).state(rows[0]['arrays'])['counts'][0]==1

def test_independent_grid_rejects_missing_duplicate_or_shifted(tmp_path):
    p=tmp_path/'records/wt/cpu/warmup.jsonl';p.parent.mkdir(parents=True)
    rows=[dict(index=i,kind=k,steps=s,tick=t,binding={},arrays={}) for i,(k,s,t) in enumerate(verifier.grid('warmup'))]
    p.write_text(''.join(json.dumps(r)+'\n' for r in rows));assert len(verifier.read_phase(tmp_path,'wt','cpu','warmup'))==2
    for broken in (rows[:-1],rows+[rows[-1]],[rows[0],{**rows[1],'tick':2}]):
        p.write_text(''.join(json.dumps(r)+'\n' for r in broken))
        with pytest.raises(ValueError):verifier.read_phase(tmp_path,'wt','cpu','warmup')

def test_actual_free_ledger_tracks_pending_allocations_and_cap():
    ledger=runner.AllocationLedger(cap=10);ledger.allocated(1,4);ledger.allocated(2,6)
    assert ledger.current==ledger.peak==10
    # Merely dropping a Python array creates no accounting event; only actual driver free reduces live bytes.
    ledger.freed(1);assert ledger.current==6 and ledger.peak==10
    ledger.allocated(3,5)
    with pytest.raises(ValueError):ledger.check()
    with pytest.raises(ValueError):ledger.freed(999)
    with pytest.raises(ValueError):ledger.allocated(2,1)

def test_transport_failure_blocks_before_scientific_import(tmp_path):
    receipt=tmp_path/'failed.json';receipt.write_text(json.dumps({'status':'timeout','neural_ticks':0,'gpu_ticks':0}))
    proc=subprocess.run([sys.executable,str(SCRIPTS/'run_cuda_fullgraph.py'),'run','--package',str(tmp_path/'absent'),'--registration-sha256','none','--transport',str(receipt)],capture_output=True,text=True)
    assert proc.returncode!=0 and '64MiB transport preflight did not pass' in proc.stderr and not (tmp_path/'output').exists()

def test_no_neural_imports_and_optimized_guards():
    code="import importlib.util,sys; p=sys.argv[1]; s=importlib.util.spec_from_file_location('v',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);m.Decoder('/missing',3).array({'base':'cycle'})"
    proc=subprocess.run([sys.executable,'-O','-c',code,str(SCRIPTS/'verify_cuda_fullgraph.py')],capture_output=True,text=True)
    assert proc.returncode!=0 and 'non-object or chained reference' in proc.stderr
    assert not any(name.startswith(('flyarena','numba.cuda')) for name in sys.modules)

def test_inventory_detects_extra_changed_or_missing_files(tmp_path):
    (tmp_path/'payload').write_bytes(b'actual retained bytes')
    inventory={'schema':'fullgraph-inventory/v1','files':{'payload':{'bytes':21,'sha256':verifier.sha(tmp_path/'payload')}}}
    # Compute the size rather than assuming a literal's character count.
    inventory['files']['payload']['bytes']=(tmp_path/'payload').stat().st_size
    verifier.exclusive_json(tmp_path/'inventory.json',inventory);anchor=verifier.sha(tmp_path/'inventory.json');verifier.verify_inventory(tmp_path,anchor)
    (tmp_path/'extra').write_text('x')
    with pytest.raises(ValueError):verifier.verify_inventory(tmp_path,anchor)
    (tmp_path/'extra').unlink();(tmp_path/'payload').write_text('corrupt')
    with pytest.raises(ValueError):verifier.verify_inventory(tmp_path,anchor)

def test_duplicate_json_keys_rejected():
    with pytest.raises(ValueError):verifier.parse('{"x":1,"x":2}')

def test_policy_orientation_asymmetric_at_boundary():
    cpu=state();cuda=state();cuda['v'][0]=1e-10+5e-23
    for compare in (runner.compare,verifier.compare):
        compare(cpu,cuda)
        with pytest.raises(AssertionError):compare(cuda,cpu)

def test_successful_registered_transport_schema_and_no_payload_retry():
    attempt={'status':'passed','payload_started':True,'last_phase':'download','bytes_each_direction':64*1024**2,
             'payload_sha256':'60fe5376281a77b981ba0776f661a00043515b39e6edbaa2b08ee31751227f8a','upload_seconds':10.,'download_seconds':11.}
    receipt={'status':'passed','attempts':[attempt],'sequence':0,'neural_ticks':0,'gpu_ticks':0,'timeout_seconds_per_direction':120}
    runner.validate_transport(receipt)
    invalid=copy.deepcopy(receipt);invalid['attempts']=[copy.deepcopy(attempt),attempt]
    with pytest.raises(ValueError):runner.validate_transport(invalid)
    invalid=copy.deepcopy(receipt);invalid['attempts'][0]['upload_seconds']=121
    with pytest.raises(ValueError):runner.validate_transport(invalid)

def test_driver_observer_fake_calls_and_preallocation_cap(tmp_path):
    import ctypes
    from types import SimpleNamespace
    calls=[]
    def allocate(pointer,size):calls.append(('allocate',size));pointer._obj.value=123
    def free(pointer):calls.append(('free',pointer))
    fake=SimpleNamespace(cuMemAlloc=allocate,cuMemFree=free)
    observer=runner.DriverObserver.__new__(runner.DriverObserver);observer.driver=fake;observer.saved={};observer.ledger=runner.AllocationLedger(cap=8,path=tmp_path/'allocations.jsonl')
    observer.install();pointer=ctypes.c_uint64();fake.cuMemAlloc(ctypes.byref(pointer),4)
    assert observer.ledger.current==4
    with pytest.raises(ValueError):fake.cuMemAlloc(ctypes.byref(pointer),8)
    assert calls==[('allocate',4)]
    fake.cuMemFree(123);assert observer.ledger.current==0 and observer.ledger.peak==4
    observer.close();assert fake.cuMemAlloc is allocate and fake.cuMemFree is free
    rows=[json.loads(line) for line in (tmp_path/'allocations.jsonl').read_text().splitlines()]
    assert [row['event'] for row in rows]==['allocate','free']

def test_full_accounting_ledger_and_duplicate_completion(tmp_path):
    ledger=runner.TickLedger(tmp_path/'ticks.jsonl')
    def enter(subject,backend,phase,tick,steps):
        index=ledger.reserve(backend,subject,phase,tick,steps);ledger.completed(index,tick+steps)
    for subject in runner.SUBJECTS:
        for backend in ('cpu','cuda'):
            enter(subject,backend,'warmup',0,1)
            for tick in range(800):enter(subject,backend,'primary',tick,1)
        for phase in ('repeat','chunk','restore'):
            for backend in ('cpu','cuda'):
                if phase=='repeat':
                    for tick in range(800):enter(subject,backend,phase,tick,1)
                elif phase=='chunk':
                    for tick,steps in runner.CHUNKS:enter(subject,backend,phase,tick,steps)
                else:
                    for tick in range(317,330):enter(subject,backend,'restore-discard',tick,1)
                    for tick in range(317,800):enter(subject,backend,'restore-suffix',tick,1)
    with pytest.raises(ValueError):ledger.completed(len(ledger.entries)-1,800)
    ledger.close();assert verifier.check_tick_ledger(tmp_path/'ticks.jsonl')=={'cpu':5794,'cuda':5794}
    lines=(tmp_path/'ticks.jsonl').read_text().splitlines();lines.pop();(tmp_path/'ticks.jsonl').write_text('\n'.join(lines)+'\n')
    with pytest.raises(ValueError):verifier.check_tick_ledger(tmp_path/'ticks.jsonl')

def test_resource_receipt_recomputed_from_authored_events(tmp_path):
    gib=1024**3
    sample={'seconds':0.,'rss':100,'device_used':1000,'device_free':2*gib}
    report=authored_resources(tmp_path,'resource-samples.jsonl');report.update(samples=1,largest_sample_gap_seconds=0.,last_sample_age_seconds=.02)
    ledger=runner.AllocationLedger(path=tmp_path/'driver-allocations.jsonl');ledger.allocated(123,4);ledger.freed(123);ledger.file.close()
    terminal={'resources':report,'driver_allocation':ledger.report()}
    (tmp_path/'resource-samples.jsonl').write_text(json.dumps(sample)+'\n');(tmp_path/'runner-terminal.json').write_text(json.dumps(terminal))
    verifier.verify_resources(tmp_path)
    sample['device_free']=gib-1;(tmp_path/'resource-samples.jsonl').write_text(json.dumps(sample)+'\n')
    with pytest.raises(ValueError):verifier.verify_resources(tmp_path)

def test_nonfinite_record_retains_full_offending_arrays(tmp_path):
    store=runner.ObjectStore(tmp_path,n=3);record=runner.Recorder(tmp_path,store,'wt','cpu','primary');bad=state(tick=1);bad['v'][1]=np.nan
    with pytest.raises(ValueError):record.append(bad,'advance',1,{})
    record.close();folder=tmp_path/'invalid-record-state';meta=json.loads((folder/'state.json').read_text())
    assert set(meta['arrays'])==set(bad) and np.isnan(np.load(folder/'v.npy',allow_pickle=False)[1])
    assert np.load(folder/'delay.npy',allow_pickle=False).tobytes()==bad['delay'].tobytes()

def test_advance_exception_retains_state_and_unresolved_reservation(tmp_path):
    from types import SimpleNamespace
    class FailingAPI:
        def checkpoint(self):return {'state':{k:v for k,v in state().items() if k!='counts'}}
        def advance(self,steps):raise RuntimeError('authored API failure before work')
    ledger=runner.TickLedger(tmp_path/'ticks.jsonl');guard=SimpleNamespace(output=tmp_path,check=lambda observer:None)
    with pytest.raises(RuntimeError,match='authored API failure'):
        runner.checked_advance(FailingAPI(),'cpu','wt','primary',1,ledger,guard,None)
    ledger.close();assert ledger.counts=={'cpu':1,'cuda':0} and ledger.entries[0]['state']=='reserved'
    saved=json.loads((tmp_path/'advance-failure-state/state.json').read_text())
    assert set(saved['arrays'])==runner.STATE_KEYS and saved['counts'].startswith('unavailable')


def authored_resources(root,name='oracle-resource-samples.jsonl'):
    samples=[{'seconds':t,'rss':100,'device_used':1000,'device_free':2*runner.GIB} for t in (0.,.01)]
    (root/name).write_text(''.join(json.dumps(row)+'\n' for row in samples))
    return dict(error=None,hard_cgroup_charged_memory_cap_bytes=4*runner.GIB,os_ru_maxrss_bytes=200,
                sampled_board_baseline=900,samples=2,sampled_rss_peak=100,sampled_board_peak_lower_bound=1000,
                cgroup='/sys/fs/cgroup/authored',process_id=123,cgroup_process_ids=[123],cadence_target_seconds=.01,
                largest_sample_gap_seconds=.01,elapsed_seconds=.02,compute_elapsed_seconds=.1,
                stage_elapsed_seconds=.2,last_sample_age_seconds=.01)


@pytest.mark.parametrize('failure',['postguard','wrong_tick','snapshot','ledger','telemetry','postsync'])
def test_completed_call_failure_retains_returned_arrays(tmp_path,failure):
    from types import SimpleNamespace
    class API:
        tick=0
        syncs=0
        def checkpoint(self):
            if failure=='snapshot' and self.tick:raise RuntimeError('authored snapshot failure')
            return {'state':{k:v for k,v in state(tick=self.tick).items() if k!='counts'}}
        def advance(self,steps):self.tick=2 if failure=='wrong_tick' else 1;return np.array([1,0,1],dtype='<i4')
        def synchronize(self):
            self.syncs+=1
            if failure=='postsync' and self.syncs==2:raise RuntimeError('authored postsync failure')
    class Guard:
        output=tmp_path
        calls=0
        def check(self,observer):
            self.calls+=1
            if failure=='postguard' and self.calls==2:raise RuntimeError('authored postguard failure')
    api=API();api.stream=api;api.device_state={}
    ledger=runner.TickLedger(tmp_path/'ticks.jsonl')
    if failure=='ledger':ledger.completed=lambda *a:(_ for _ in ()).throw(RuntimeError('authored ledger failure'))
    kind='cuda' if failure in ('telemetry','postsync') else 'cpu'
    with pytest.raises((ValueError,RuntimeError,AttributeError)) as caught:
        runner.checked_advance(api,kind,'wt','primary',1,ledger,Guard(),SimpleNamespace(live_array_peak=0))
    receipt=caught.value.failure_capture;folder=tmp_path/'advance-failure-state'
    assert receipt['counts']=='returned' and np.load(folder/'counts.npy').tolist()==[1,0,1]
    if failure=='snapshot':
        assert set(receipt['unavailable'])==runner.STATE_KEYS and receipt['acquisition_errors']
    else:
        assert receipt['complete'] and np.load(folder/'tick.npy').item()==api.tick
        assert np.load(folder/'delay.npy').tobytes()==state()['delay'].tobytes()
    accounting=ledger.summary();ledger.close()
    completed=1 if failure in ('postguard','telemetry') else 0
    assert accounting['completed'][kind]==completed and accounting['unresolved'][kind]==1-completed
    assert (accounting['actual_executed_ticks'] is None)==(completed==0)


def test_capture_error_does_not_replace_original(tmp_path,monkeypatch):
    from types import SimpleNamespace
    class API:
        def checkpoint(self):return {'state':state()}
        def advance(self,steps):raise RuntimeError('original advance error')
    monkeypatch.setattr(runner,'preserve_unchecked_state',lambda *a:(_ for _ in ()).throw(OSError('authored capture write error')))
    ledger=runner.TickLedger(tmp_path/'ticks.jsonl')
    with pytest.raises(RuntimeError,match='original advance error') as caught:
        runner.checked_advance(API(),'cpu','wt','primary',1,ledger,SimpleNamespace(output=tmp_path,check=lambda *a:None),None)
    ledger.close()
    assert 'authored capture write error' in caught.value.failure_capture['capture_errors'][0]


@pytest.mark.parametrize('failure',['quota','write','flush','serialize'])
def test_recorder_failure_retains_previous_prefix_and_actual_state(tmp_path,monkeypatch,failure):
    record=runner.Recorder(tmp_path,runner.ObjectStore(tmp_path,n=3),'wt','cpu','primary')
    record.append(state(),'initial',0,{})
    prefix=record.path.read_bytes();actual=state(tick=1);actual['counts'][2]=1
    if failure=='quota':record.store.cap=1
    elif failure=='serialize':
        original=runner.canonical
        def encode(value):
            if isinstance(value,dict) and 'index' in value:raise RuntimeError('authored serialization failure')
            return original(value)
        monkeypatch.setattr(runner,'canonical',encode)
    else:
        real=record.file
        class Broken:
            def write(self,value):
                if failure=='write':real.write(value[:9]);real.flush();raise OSError('authored record write failure')
                return real.write(value)
            def flush(self):raise OSError('authored record flush failure')
            def close(self):real.close()
        record.file=Broken()
    with pytest.raises((ValueError,RuntimeError,OSError)) as caught:record.append(actual,'advance',1,{})
    record.close();receipt=caught.value.failure_capture
    assert receipt['complete'] and receipt['completed_record_prefix']==1
    assert record.path.read_bytes().startswith(prefix) and len(record.rows)==1
    assert np.load(tmp_path/'invalid-record-state/counts.npy').tolist()==[0,0,1]


def test_failure_reserve_omissions_and_write_errors_are_explicit(tmp_path,monkeypatch):
    monkeypatch.setattr(runner,'RESERVE',1)
    receipt=runner.preserve_unchecked_state(tmp_path/'budget-failure',state(),{})
    assert not receipt['complete'] and all(not a['retained'] and a['omission'] for a in receipt['arrays'].values())
    monkeypatch.setattr(runner,'RESERVE',256*1024**2)
    monkeypatch.setattr(runner.np,'save',lambda *a,**kw:(_ for _ in ()).throw(OSError('authored raw write failure')))
    receipt=runner.preserve_unchecked_state(tmp_path/'write-failure',state(),{})
    assert not receipt['complete'] and len(receipt['capture_errors'])==9


def test_ledger_summary_uses_retained_prefix_and_marks_partial_tail(tmp_path):
    ledger=runner.TickLedger(tmp_path/'ticks.jsonl');i=ledger.reserve('cpu','wt','oracle',0,1);ledger.completed(i,1)
    ledger.reserve('cpu','wt','oracle',1,1);ledger.counts['cpu']=999
    assert ledger.summary()['reserved']['cpu']==2
    ledger.file.write('{"partial":');ledger.file.flush()
    summary=ledger.summary();ledger.close()
    assert summary['completed']['cpu']==1 and summary['unresolved']['cpu']==1
    assert not summary['accounting_complete'] and summary['actual_executed_ticks'] is None


def mock_oracle(tmp_path,monkeypatch,failure):
    from types import SimpleNamespace,ModuleType
    package=tmp_path/'package';package.mkdir();root=tmp_path/'output';root.mkdir()
    (package/'registration.json').write_text(json.dumps({'stage_started_epoch':runner.time.time()}))
    (root/'runner-start.json').write_text(json.dumps({'epoch':runner.time.time()}))
    weights=np.zeros(1,dtype='<f4');spec={'artifact_id':'authored','weights_sha256':hashlib.sha256(weights.tobytes()).hexdigest()}
    monkeypatch.setitem(sys.modules,'run_cuda_fullgraph',runner)
    monkeypatch.setattr(runner,'load_policy',lambda:{'device_uuid':'authored','subjects':{s:spec for s in runner.SUBJECTS}})
    monkeypatch.setattr(runner,'verify_runtime',lambda *a:None)
    class Guard:
        def __init__(self,task,output,*a,**kw):self.output=output
        def check(self,*a):pass
        def close(self):
            report=authored_resources(root)
            if failure=='late_error':report['error']='authored monitoring failure'
            if failure=='high_rss':report['os_ru_maxrss_bytes']=5*runner.GIB
            if failure=='missing_samples':(root/'oracle-resource-samples.jsonl').unlink()
            if failure=='tampered_samples':(root/'oracle-resource-samples.jsonl').write_text('{}\n')
            if failure=='close_exception':raise RuntimeError('authored close failure')
            return report
    monkeypatch.setattr(runner,'ResourceGuard',Guard)
    monkeypatch.setattr(verifier,'verify_artifacts',lambda *a:{'status':'artifact-verified','bindings':{s:{} for s in runner.SUBJECTS}})
    monkeypatch.setattr(verifier,'read_phase',lambda *a:[{'arrays':i} for i in range(801)])
    monkeypatch.setattr(verifier,'Decoder',lambda *a:SimpleNamespace(state=lambda tick:state(tick=tick)))
    monkeypatch.setattr(verifier,'N',3)
    class API:
        tick=0
        def __init__(self,*a,**kw):pass
        def reset(self,*a):self.tick=0
        def stimulate(self,*a):pass
        def checkpoint(self):
            if failure=='snapshot' and self.tick==2:raise RuntimeError('authored oracle snapshot failure')
            value=state(tick=self.tick)
            if self.tick==1 and failure in ('mismatch','nonfinite'):value['v'][0]=1 if failure=='mismatch' else np.nan
            del value['counts'];return {'state':value}
        def advance(self,steps):
            if failure=='interrupted' and self.tick==1:raise RuntimeError('authored oracle advance failure')
            self.tick+=1;return np.zeros(3,dtype='<i4')
    for name in ('flyarena','flyarena.connectome','flyarena.compiler','flyarena.optional_backend'):
        monkeypatch.setitem(sys.modules,name,ModuleType(name))
    sys.modules['flyarena.connectome'].Connectome=lambda *a,**kw:None
    sys.modules['flyarena.compiler'].Compiler=lambda *a:SimpleNamespace(load_weights=lambda *a:(weights,{}))
    sys.modules['flyarena.optional_backend'].CheckedCPUBackend=API
    # oracle inserts this registered path; keep the test process's import state isolated.
    monkeypatch.setattr(sys,'path',sys.path.copy())
    return SimpleNamespace(package=str(package),output=str(root),registration_sha256='authored'),root


@pytest.mark.parametrize('failure',['interrupted','snapshot','mismatch','nonfinite'])
def test_oracle_failed_prefix_accounting_and_raw_retention(tmp_path,monkeypatch,failure):
    args,root=mock_oracle(tmp_path,monkeypatch,failure)
    with pytest.raises((RuntimeError,AssertionError,ValueError)):verifier.oracle(args)
    terminal=json.loads((root/'oracle-terminal.json').read_text())
    assert terminal['status']=='blocked' and terminal['new_neural_ticks']==1
    unresolved=failure in ('interrupted','snapshot')
    assert terminal['reserved_oracle_ticks']=={'cpu':2 if unresolved else 1,'cuda':0}
    assert terminal['completed_oracle_ticks']=={'cpu':1,'cuda':0}
    assert terminal['unresolved_oracle_ticks']=={'cpu':int(unresolved),'cuda':0}
    assert (terminal['actual_oracle_ticks'] is None)==unresolved
    assert not (root/'inventory.json').exists()
    folder=root/('advance-failure-state' if unresolved else 'oracle-failure')
    receipt=json.loads((folder/'state.json').read_text())
    if failure=='interrupted':assert receipt['counts'].startswith('unavailable') and set(receipt['arrays'])==runner.STATE_KEYS
    elif failure=='snapshot':assert receipt['counts']=='returned' and set(receipt['unavailable'])==runner.STATE_KEYS
    else:
        assert receipt['complete'] and set(receipt['arrays'])==verifier.FIELDS
        if failure=='nonfinite':assert np.isnan(np.load(folder/'v.npy')[0])
    before=(root/'oracle-ticks.jsonl').read_bytes()
    with pytest.raises(FileExistsError):verifier.oracle(args)
    assert (root/'oracle-ticks.jsonl').read_bytes()==before


@pytest.mark.parametrize('failure',['none','late_error','high_rss','missing_samples','tampered_samples','close_exception','summary'])
def test_oracle_final_resource_gate_before_success_inventory(tmp_path,monkeypatch,failure):
    args,root=mock_oracle(tmp_path,monkeypatch,failure)
    if failure=='summary':
        original=runner.TickLedger.summary
        def incomplete(ledger):
            value=original(ledger);value.update(accounting_complete=False,accounting_error='authored unreadable tail');return value
        monkeypatch.setattr(runner.TickLedger,'summary',incomplete)
    if failure=='none':
        result=verifier.oracle(args)
        assert result['status']=='oracle-and-artifact-verified'
        verifier.verify_inventory(root,result['inventory_sha256']);verifier.verify_oracle_resources(root)
        # Exercise the real artifact-only dispatcher; only preregistered large-artifact reads are mocked.
        monkeypatch.setattr(verifier,'__file__',str(Path(args.package)/'source/scripts/verify_cuda_fullgraph.py'))
        monkeypatch.setattr(sys,'argv',['verify','artifact-only','--package',args.package,'--output',args.output,'--registration-sha256','authored','--inventory-sha256',result['inventory_sha256']])
        verifier.main()
        (root/'oracle-resource-samples.jsonl').unlink()
        monkeypatch.setattr(verifier,'verify_inventory',lambda *a:None)
        with pytest.raises(FileNotFoundError):verifier.main()
    else:
        with pytest.raises((ValueError,KeyError,FileNotFoundError,RuntimeError)):verifier.oracle(args)
    terminal=json.loads((root/'oracle-terminal.json').read_text())
    assert terminal['new_neural_ticks']==1600 and terminal['unresolved_oracle_ticks']=={'cpu':0,'cuda':0}
    assert (root/'inventory.json').exists()==(failure=='none')
    assert terminal['status']==('oracle-and-artifact-verified' if failure=='none' else 'blocked')
    if failure=='summary':assert terminal['error']=='final oracle accounting incomplete'
    elif failure!='none':assert terminal['resource_closure_error']


@pytest.mark.parametrize('damage',['error','rss','negative','nan','cgroup','process','cadence','gap','age','compute','stage','count','missing','tampered'])
def test_oracle_resource_reconstruction_rejects_damage_under_optimized_python(tmp_path,damage):
    report=authored_resources(tmp_path)
    updates={'error':('error','authored'),'rss':('os_ru_maxrss_bytes',5*runner.GIB),'negative':('sampled_board_baseline',-1),
             'nan':('elapsed_seconds',float('nan')),'cgroup':('cgroup','/untrusted'),
             'process':('cgroup_process_ids',[123,456]),'cadence':('cadence_target_seconds',.1),
             'gap':('largest_sample_gap_seconds',1.),'age':('last_sample_age_seconds',1.),
             'compute':('compute_elapsed_seconds',14401),'stage':('stage_elapsed_seconds',28801),'count':('samples',3)}
    if damage in updates:key,value=updates[damage];report[key]=value
    if damage=='missing':(tmp_path/'oracle-resource-samples.jsonl').unlink()
    if damage=='tampered':(tmp_path/'oracle-resource-samples.jsonl').write_text('{"seconds":0,"rss":-1,"device_used":1000,"device_free":2147483648}\n')
    (tmp_path/'oracle-terminal.json').write_text(json.dumps({'status':'oracle-and-artifact-verified','resources':report}))
    code="import importlib.util,sys;s=importlib.util.spec_from_file_location('v',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);m.verify_oracle_resources(sys.argv[2])"
    proc=subprocess.run([sys.executable,'-O','-c',code,str(SCRIPTS/'verify_cuda_fullgraph.py'),str(tmp_path)],capture_output=True,text=True)
    assert proc.returncode!=0,proc.stdout+proc.stderr


def test_oracle_capture_and_close_errors_do_not_mask_nonfinite_failure(tmp_path,monkeypatch):
    args,root=mock_oracle(tmp_path,monkeypatch,'nonfinite')
    monkeypatch.setattr(runner,'preserve_unchecked_state',lambda *a:(_ for _ in ()).throw(OSError('authored capture failure')))
    original=runner.ResourceGuard.close
    def broken_close(guard):
        report=original(guard);report['error']='authored late monitor failure';return report
    monkeypatch.setattr(runner.ResourceGuard,'close',broken_close)
    with pytest.raises(ValueError,match='nonfinite state v'):verifier.oracle(args)
    terminal=json.loads((root/'oracle-terminal.json').read_text())
    assert terminal['error']=='nonfinite state v' and terminal['new_neural_ticks']==1
    assert terminal['failure_capture']['capture_errors']==['OSError: authored capture failure']
    assert 'resource monitor error' in terminal['resource_closure_error']


def test_resource_cgroup_namespace_root_is_valid(tmp_path):
    report=authored_resources(tmp_path);report['cgroup']='/sys/fs/cgroup'
    verifier.verify_resource_samples(tmp_path,report,'oracle-resource-samples.jsonl')
