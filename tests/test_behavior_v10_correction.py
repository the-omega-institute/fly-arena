"""Synthetic runner fault injection only: no body construction or physics calls."""
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from flyarena.experiments import mechanical_v10 as runner
from flyarena.experiments import verify_v10


@pytest.fixture
def synthetic_runner(tmp_path, monkeypatch):
    assert Path(runner.__file__).resolve().is_relative_to(Path(__file__).resolve().parents[1]/'src')
    root=tmp_path/'experiment'
    root.mkdir()
    runner.write_json(root/'registration.json',{'compiled_arrays':{},'sources_sha256':'synthetic'})
    calls=SimpleNamespace(bodies=0,steps=0,finishes=[],reports=0,verifications=0)
    faults=set()
    physical=FloatingPointError('synthetic physical failure')

    def body(seed, profile):
        calls.bodies+=1
        return SimpleNamespace(model=None,tick=0,
            data=SimpleNamespace(**{key:np.zeros(1) for key in
                ['qpos','qvel','qacc','ctrl','actuator_force']}),
            controllers=[SimpleNamespace(cpg_network=SimpleNamespace(
                curr_phases=np.zeros(6),curr_magnitudes=np.zeros(6)))])

    def step(b,u):
        calls.steps+=1
        b.tick+=1
        if 'physical' in faults:
            if 'capture' in faults:
                del b.data.qacc
            raise physical

    class Budget:
        def __init__(self,root):
            self.steps=0
        def check(self):
            pass
        def report(self):
            calls.reports+=1
            if 'resources' in faults or ('execution_resources' in faults and calls.reports==33):
                raise OSError('synthetic resource report failure')
            return {'synthetic_steps':self.steps,'physical_seconds':0}

    original_finish=runner.NumericEvidence.finish
    original_init=runner.NumericEvidence.__init__

    def init(self,path,*args,**kwargs):
        if path.name+'_init' in faults:
            raise OSError('synthetic '+path.name+' initialization failure')
        original_init(self,path,*args,**kwargs)

    def finish(self,*args,**kwargs):
        stream=self.root.name
        calls.finishes.append(stream)
        if stream+'_throw' in faults:
            raise OSError('synthetic '+stream+' finish failure')
        if stream+'_flush' in faults:
            def broken():
                raise OSError('synthetic prefix failure')
            self.flush=broken
        terminal=original_finish(self,*args,**kwargs)
        if stream+'_incomplete' in faults:
            terminal['complete']=False
        if stream+'_retention' in faults:
            terminal['retention_failures']=[{'stage':'injected-retention'}]
        runner.write_json(self.root/'terminal.json',terminal)
        if stream+'_missing' in faults:
            return None
        if stream+'_malformed' in faults:
            return []
        return terminal

    def verify(*args):
        calls.verifications+=1
        return {'candidate_passed':False,'synthetic':True}

    monkeypatch.setattr(runner,'validate_freeze',lambda root:None)
    monkeypatch.setattr(runner,'new_body',body)
    monkeypatch.setattr(runner,'Observer',lambda b:SimpleNamespace(
        row=lambda u:(np.zeros(sum(n for _,n in runner.CORE)),np.zeros(360))))
    monkeypatch.setattr(runner,'step',step)
    monkeypatch.setattr(runner,'state_finite',lambda b:None)
    monkeypatch.setattr(runner,'integration',lambda b:np.zeros(2))
    # Ten synthetic ticks exercise both streams; production horizon is untouched.
    monkeypatch.setattr(runner,'range',lambda n:range(10) if n==40000 else range(n),raising=False)
    monkeypatch.setattr(runner,'Budget',Budget)
    monkeypatch.setattr(runner.NumericEvidence,'__init__',init)
    monkeypatch.setattr(runner.NumericEvidence,'finish',finish)
    monkeypatch.setattr(verify_v10,'verify_panel',verify)
    return root,calls,faults,physical


@pytest.mark.parametrize('injected,expected_stages',[
    ({'core_incomplete'},{'core-terminal'}),
    ({'geometry_incomplete'},{'geometry-terminal'}),
    ({'core_retention'},{'core-terminal'}),
    ({'geometry_retention'},{'geometry-terminal'}),
    ({'core_throw'},{'core-finish'}),
    ({'geometry_throw'},{'geometry-finish'}),
    ({'core_flush'},{'core-terminal'}),
    ({'geometry_flush'},{'geometry-terminal'}),
    ({'resources'},{'trial-resources','execution-resources'}),
    ({'core_malformed'},{'core-finish'}),
    ({'geometry_missing'},{'geometry-terminal'}),
    ({'physical','core_throw','geometry_throw','resources'},
     {'core-finish','geometry-finish','trial-resources','execution-resources'}),
    ({'physical','capture','core_throw'},{'failing-state','core-finish','geometry-terminal'}),
])
def test_failure_stops_runner_before_second_trial(synthetic_runner,capsys,injected,expected_stages):
    root,calls,faults,physical=synthetic_runner
    faults.update(injected)
    with pytest.raises((RuntimeError,FloatingPointError)) as caught:
        runner.run(root)
    assert calls.bodies==1 and calls.verifications==0
    assert calls.steps==(1 if 'physical' in faults else 10)
    assert calls.finishes==['core','geometry']
    assert 'completed' not in capsys.readouterr().out
    terminal=json.loads((root/'execution-terminal.json').read_text())
    assert terminal['outcome']=='failed' and terminal['decision'] is None
    assert expected_stages <= {f['stage'] for f in terminal['retention_failures']}
    trial=json.loads(next(root.glob('development/*/trial-terminal.json')).read_text())
    assert trial['complete'] is False
    if 'physical' in faults:
        assert caught.value is physical
        assert terminal['primary_failure']['message']==str(physical)
        assert trial['primary_failure']['message']==str(physical)
        assert caught.value.primary_failure['message']==str(physical)
    else:
        assert terminal['primary_failure'] is None
        assert trial['primary_failure'] is None
    assert expected_stages <= {f['stage'] for f in caught.value.retention_failures}


def test_partial_stream_initialization_finalizes_existing_core(synthetic_runner):
    root,calls,faults,_=synthetic_runner
    faults.add('geometry_init')
    with pytest.raises(OSError,match='geometry initialization'):
        runner.run(root)
    assert calls.bodies==1 and calls.steps==0 and calls.finishes==['core']
    terminal=json.loads((root/'execution-terminal.json').read_text())
    assert terminal['outcome']=='failed'
    assert terminal['primary_failure']['type']=='OSError'
    assert next(root.glob('development/*/core/terminal.json')).exists()


@pytest.mark.parametrize('resource_failure',[False,True])
def test_execution_resource_failure_and_successful_negative_panel(synthetic_runner,resource_failure):
    root,calls,faults,_=synthetic_runner
    if resource_failure:
        faults.add('execution_resources')
        with pytest.raises(RuntimeError,match='finalization failed'):
            runner.run(root)
    else:
        runner.run(root)
    terminal=json.loads((root/'execution-terminal.json').read_text())
    assert calls.bodies==32 and calls.steps==320 and calls.verifications==1
    assert terminal['decision']['candidate_passed'] is False
    assert terminal['outcome']==('failed' if resource_failure else 'completed')
    assert terminal['primary_failure'] is None
    assert bool(terminal['retention_failures'])==resource_failure


def test_terminal_write_failures_retain_primary_and_attempt_all_streams(synthetic_runner,monkeypatch):
    root,calls,faults,physical=synthetic_runner
    faults.update({'physical','core_throw'})
    original_write=runner.write_json
    attempts=[]
    def write(path,value):
        attempts.append(path.name)
        if path.name in {'trial-terminal.json','execution-terminal.json'}:
            raise OSError('synthetic terminal disk failure')
        original_write(path,value)
    monkeypatch.setattr(runner,'write_json',write)
    with pytest.raises(FloatingPointError) as caught:
        runner.run(root)
    assert caught.value is physical and calls.bodies==1
    assert calls.finishes==['core','geometry']
    assert 'trial-terminal.json' in attempts and 'execution-terminal.json' in attempts
    assert {'core-finish','trial-terminal','execution-terminal'} <= {
        f['stage'] for f in physical.retention_failures}
    assert not (root/'execution-terminal.json').exists()
