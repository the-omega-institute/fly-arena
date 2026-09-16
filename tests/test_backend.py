from types import SimpleNamespace
import numpy as np
import pytest
from flyarena.backend import CPUBrainBackend, V2_IDS, CAPABILITIES, backend_catalog
from flyarena.neural import Brain

def tiny_backend():
    groups={k:np.array([0],dtype=np.int32) for k in ['olfactory','projection','local','memory','readout','descending','visual','motor','olfactory_left']}
    groups['olfactory_right']=np.array([1],dtype=np.int32)
    g=SimpleNamespace(n=2,groups=groups,indptr=np.array([0,1,2],dtype=np.int64),post=np.array([1,0],dtype=np.int32),baseline_weights=lambda:np.array([.275,.275],dtype=np.float32))
    return CPUBrainBackend(Brain(g))

def test_cpu_port_stimulation_neural_output_checkpoint():
    a=tiny_backend();a.prepare(V2_IDS|{'capabilities':list(CAPABILITIES)})
    a.stimulate(.7,.2);assert a.brain.external.tolist()==pytest.approx([33.6,9.6])
    a.advance(100);state=a.checkpoint();a.advance(100);expected=a.checkpoint()
    a.restore(state);a.advance(100)
    for k,v in expected.items():np.testing.assert_array_equal(v,a.checkpoint()[k])
    rates=a.neural_output();rates[:]=999;assert not np.all(a.brain.rates==999)
    a.reset(99);a.stimulate(0,0);a.advance(1000)
    assert a.metrics()['total_spikes']==0 and not a.neural_output().any()

@pytest.mark.parametrize('key',list(V2_IDS))
def test_cpu_rejects_every_profile_mismatch(key):
    b=tiny_backend()
    with pytest.raises(ValueError,match=key):b.prepare(V2_IDS|{key:'unqualified'})
    missing=dict(V2_IDS);missing.pop(key)
    with pytest.raises(ValueError):b.prepare(missing)

def test_cpu_capabilities_and_atomic_restore():
    b=tiny_backend()
    with pytest.raises(ValueError):b.prepare(V2_IDS|{'capabilities':['cuda']})
    state=b.checkpoint();bad={k:v.copy() for k,v in state.items()};bad['v'][:]=2;bad['rates']=np.zeros(3)
    with pytest.raises(ValueError):b.restore(bad)
    np.testing.assert_array_equal(state['v'],b.brain.v)
    for raw in [(float('nan'),0),(-1,0),(2,0)]:
        with pytest.raises(ValueError):b.stimulate(*raw)
    assert not next(x for x in backend_catalog() if x['id']=='cuda')['available']
