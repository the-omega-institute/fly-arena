from types import SimpleNamespace
import numpy as np
import pytest
from flyarena.neural import Brain
from flyarena.backend import CPUBrainBackend
from flyarena.experiments.embodied_v7 import EmbodiedBridge, RMAX
from flyarena.experiments.contact_v6 import LEGS

def bridge():
    groups={f'{a}_{l}':np.array([i*6+j],dtype=np.int32) for i,a in enumerate(('afferent','flexor','extensor')) for j,l in enumerate(LEGS)}
    graph=SimpleNamespace(n=20, groups={'olfactory_left':np.array([18]),'olfactory_right':np.array([19])})
    return EmbodiedBridge(CPUBrainBackend(Brain(graph,weights=np.zeros(0,dtype=np.float32))),groups)

def test_composition_clears_and_is_atomic():
    b=bridge(); b.stimulate(np.ones(6),(.55,.55))
    assert np.all(b.backend.brain.external[:6]==48)
    assert np.allclose(b.backend.brain.external[18:],48*.55/.85)
    before=b.checkpoint()
    with pytest.raises(ValueError): b.stimulate(np.ones(6),(np.nan,0))
    assert all(np.array_equal(v,b.checkpoint()[k]) for k,v in before.items())
    b.stimulate(np.zeros(6)); assert not b.backend.brain.external.any()

def test_rates_ceiling_and_no_clipping():
    b=bridge(); b.backend.brain.rates[6:12]=RMAX
    assert np.allclose(b.readout()[1],.1)
    for invalid in (-1,RMAX+1,np.inf):
        b.backend.brain.rates[6]=invalid
        with pytest.raises(ValueError): b.readout()

def test_group_copy_and_overlap():
    b=bridge()
    with pytest.raises(ValueError): b.groups['afferent_LF'][0]=3
    groups=dict(b.groups); groups['afferent_LF']=groups['flexor_LF']
    with pytest.raises(ValueError): EmbodiedBridge(b.backend,groups)

@pytest.mark.parametrize('key,value',[('tick',np.array(1.5)),('total_spikes',np.array(-1)),('refractory',np.full(20,23,dtype=np.int32)),('rates',np.full(20,-1.)),('held_command',np.ones(6))])
def test_restore_atomic(key,value):
    b=bridge(); initial=b.checkpoint(); bad=b.checkpoint(); bad['v'][:]=30; bad[key]=value
    with pytest.raises(ValueError): b.restore(bad)
    assert all(np.array_equal(v,b.checkpoint()[k]) for k,v in initial.items())
