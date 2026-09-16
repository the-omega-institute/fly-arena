"""Input contracts and causal gate boundary tests; no scientific candidate fitting."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from flyarena.experiments.contact_presence_v8 import ContactPresenceBridge,RMAX
from flyarena.experiments.binary_fixture_v8 import BinaryFixture
from flyarena.experiments.contact_v6 import LEGS

class FakeBackend:
    def __init__(self):
        self.brain=SimpleNamespace(graph=SimpleNamespace(n=20,groups={'olfactory_left':np.array([18]),'olfactory_right':np.array([19])}),external=np.zeros(20))
        self.rates=np.zeros(20)
    def neural_output(self):return self.rates.copy()

def make_bridge():
    groups={a+'_'+l:np.array([j*6+i]) for j,a in enumerate(['afferent','flexor','extensor']) for i,l in enumerate(LEGS)}
    return ContactPresenceBridge(FakeBackend(),groups)

def test_presence_and_odor_rebuilt_once():
    b=make_bridge();b.backend.brain.external[:]=13
    b.stimulate([0,np.nextafter(0.,1.),.001,1,100,0],(.55,.55))
    assert np.array_equal(b.backend.brain.external[:6],[0,48,48,48,48,0])
    assert np.all(b.backend.brain.external[6:18]==0)
    odor=b.backend.brain.external[18:].copy();b.stimulate(np.ones(6),(.55,.55),True)
    assert np.all(b.backend.brain.external[:18]==0) and np.array_equal(odor,b.backend.brain.external[18:])

@pytest.mark.parametrize('ratios',[[0]*5,[-1]*6,[np.nan]*6,[np.inf]*6])
def test_invalid_inputs_fail_closed(ratios):
    with pytest.raises(ValueError):make_bridge().stimulate(ratios)

def test_rate_only_unclipped_motor_and_clamp():
    b=make_bridge();b.backend.rates[6:12]=RMAX/2;b.backend.rates[12:18]=RMAX/4
    pools,cmd=b.readout();assert np.allclose(cmd,.025,atol=1e-17)
    b.backend.brain.external[:]=48;assert np.array_equal(b.readout()[1],cmd)
    assert np.all(b.readout(True)[1]==0)
    b.backend.rates[0]=RMAX+1
    with pytest.raises(ValueError):b.readout()

def test_nonoverlapping_groups_rejected():
    b=make_bridge();g=dict(b.groups);g['afferent_LF']=g['flexor_LF']
    with pytest.raises(ValueError):ContactPresenceBridge(FakeBackend(),g)

def test_whole_intervals_and_same_direction():
    path=Path(__file__).resolve().parents[1]/'scripts/verify_contact_v8.py'
    spec=importlib.util.spec_from_file_location('independent_verify_v8',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    x=np.r_[0,np.full(6,.02),0];assert module.longest_intervals(x)==.05
    assert module.longest_intervals(x,-x)==0
    assert module.longest_intervals(np.full(6,.01))==0
    assert module.longest_intervals(np.array([.02,-.02,.02,-.02]))==0

def test_authoritative_binary_loader_rest_only():
    f=BinaryFixture(Path(__file__).resolve().parents[1]/'var/contact-v8/inputs')
    assert np.array_equal(f.data.mocap_pos[f.probe_id],[0,0,10])
    ratios,forces,loaded,pairs=f.observe(sham=True)
    assert np.all(ratios==0) and not loaded.any()
