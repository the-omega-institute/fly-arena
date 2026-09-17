"""Compiler tests use tiny canonical fixtures plus the installed full graph."""
import hashlib
import json
from types import SimpleNamespace
import numpy as np
import pytest
from flyarena.common import file_sha, write_json
from flyarena.compiler import Compiler
from flyarena.contracts import FlySpec
from flyarena.store import Store


def fixture_graph(tmp_path):
    rows = [{'id':'10','class':'olfactory','type':'ORN','side':'L'},
            {'id':'20','class':'ALPN','type':'PN','side':'R'},
            {'id':'30','class':'unknown','type':'mod','side':None},
            {'id':'40','class':'motor','type':'MN','side':'L'}]
    write_json(tmp_path/'neurons.json',rows)
    pre=np.array([0,0,1,2,3]);post=np.array([1,2,3,0,1]);counts=np.array([1,3,2,5,4])
    return SimpleNamespace(path=tmp_path,n=4,e=5,ids=np.array([10,20,30,40]),pre=pre,post=post,counts=counts,
        manifest={'sha256':'a'*64,'files':{'neurons.json':file_sha(tmp_path/'neurons.json')}},
        groups={'olfactory':np.array([0]),'projection':np.array([1]),'local':np.array([2]),'descending':np.array([3])},
        baseline_weights=lambda:np.array([.275,.825,-.55,0,1.1],dtype=np.float32))


def spec(**kwargs):
    return FlySpec(name='fixture',connectome_sha256='a'*64,**kwargs)


def test_selector_roundtrip_overlap_and_effective_budget(tmp_path):
    c=Compiler(fixture_graph(tmp_path))
    change=spec(interventions=[{'selector':{'pre':{'class':'olfactory','side':'L'},'post':{'ids':['20']}},'scale':1.1},
                               {'selector':{'pre':{'ids':['30']}},'scale':1.1}],
                weight_mutations=[{'selector':'olfactory','scale':1.1}],edge_deltas=[{'edge':0,'log_delta':-.02}])
    report=c.compile(change,publish=True,root=tmp_path)
    weights,manifest=c.load_weights(report['artifact_id'],tmp_path)
    expected=c.graph.baseline_weights()*np.exp(np.round([2*np.log(1.1)-.02,np.log(1.1),0,np.log(1.1),0],12))
    np.testing.assert_array_equal(weights,expected.astype(np.float32))
    assert manifest['mutation_format']=='resolved-log-delta/v2'
    assert report['structural_changed_edges']==3 and report['effective_changed_edges']==2
    assert report['synaptic_contacts']==9 and report['effective_synaptic_contacts']==4
    assert report['affected_neurons']==3
    assert report['metadata_sha256']==file_sha(tmp_path/'neurons.json')
    no_zero=spec(interventions=[change.interventions[0]],weight_mutations=change.weight_mutations,edge_deltas=change.edge_deltas)
    assert c.compile(no_zero)['budget_used'] < report['budget_used']
    expected_cost = float(np.sum(c.edge_cost*np.abs(np.round([2*np.log(1.1)-.02,np.log(1.1),0,np.log(1.1),0],12)))/.08*100)
    assert report['weight_points'] == pytest.approx(expected_cost, abs=1e-6)
    # Full final overlap/cancellation, including an edge edit, restores canonical artifact identity.
    cancel=spec(interventions=[{'selector':{'pre':{'ids':['10']}},'scale':1.25}],
                weight_mutations=[{'selector':'olfactory','scale':.8}])
    assert c.compile(cancel)['artifact_id']==c.compile(spec())['artifact_id']
    assert c.compile(cancel)['budget_used']==0


@pytest.mark.parametrize('selector',[{}, {'pre':{}},{'pre':{'ids':[]}},{'pre':{'ids':['010']}},
    {'pre':{'ids':['10','10']}},{'pre':{'roi':'brain'}},{'pre':{'side':'left'}},
    {'pre':{'ids':['999']}},{'pre':{'class':'not-real'}},{'pre':{'type':'not-real'}},
    {'pre':{'class':'olfactory','side':'R'}},{'pre':{'ids':['10']},'post':{'ids':['40']}}])
def test_unknown_empty_or_unsupported_selectors_reject(tmp_path,selector):
    with pytest.raises(ValueError):
        Compiler(fixture_graph(tmp_path)).compile(spec(interventions=[{'selector':selector,'scale':1.1}]))


def test_metadata_tampering_and_bounds(tmp_path):
    g=fixture_graph(tmp_path)
    (tmp_path/'neurons.json').write_text('[]')
    with pytest.raises(ValueError,match='metadata digest'):
        Compiler(g).compile(spec(interventions=[{'selector':{'pre':{'ids':['10']}},'scale':1.1}]))
    c=Compiler(fixture_graph(tmp_path))
    with pytest.raises(ValueError,match='per-edge'):
        c.compile(spec(interventions=[{'selector':{'pre':{'ids':['10']}},'scale':2}],weight_mutations=[{'selector':'olfactory','scale':2}]))
    with pytest.raises(ValueError,match='budget'):
        c.compile(spec(interventions=[{'selector':{'post':{'side':'L'}},'scale':2}],neuron_parameters={'tau_scale':1.2,'threshold_shift_mv':1}))


def test_legacy_artifact_loading_preserved(tmp_path):
    c=Compiler(fixture_graph(tmp_path));report=c.compile(spec(weight_mutations=[{'selector':'olfactory','scale':1.1}]),publish=True,root=tmp_path)
    folder=tmp_path/'artifacts'/report['artifact_id']
    manifest=json.loads((folder/'manifest.json').read_text())
    # Emulate the exact pre-upgrade structured artifact format, not a new compiler roundtrip.
    np.savez(folder/'mutations.npz',node_delta=np.array([np.log(1.1),0,0,0]),edge_idx=np.array([],dtype=np.int64),edge_delta=np.array([]))
    manifest.pop('mutation_format');manifest['mutation_sha256']=file_sha(folder/'mutations.npz')
    write_json(folder/'manifest.json',manifest)
    weights,_=c.load_weights(report['artifact_id'],tmp_path)
    assert hashlib.sha256(weights.tobytes()).hexdigest()==report['weights_sha256']


def test_parent_absolute_lineage_and_graph_profile_match(tmp_path):
    c=Compiler(fixture_graph(tmp_path));s=Store(tmp_path/'db')
    parent_spec=spec(weight_mutations=[{'selector':'olfactory','scale':1.1}])
    parent=s.add_fly('u',parent_spec.model_dump(),c.compile(parent_spec))
    child=spec(parent_id=parent['id'],weight_mutations=parent_spec.weight_mutations)
    assert c.compile(child)['artifact_id']==parent['artifact_id']
    assert s.add_fly('u',child.model_dump(),c.compile(child))['spec']['parent_id']==parent['id']
    with pytest.raises(ValueError,match='same graph'):
        s.add_fly('u',child.model_dump()|{'connectome_sha256':'b'*64},c.compile(child))
    with pytest.raises(ValueError,match='same graph'):
        s.add_fly('u',child.model_dump()|{'model_profile':'unknown'},c.compile(child))


def test_full_graph_exact_id_intervention_roundtrip(tmp_path):
    from flyarena.connectome import Connectome
    g=Connectome();c=Compiler(g)
    neuron=str(g.ids[g.pre[0]])
    design=FlySpec(name='full graph local validation',connectome_sha256=g.manifest['sha256'],
                   interventions=[{'selector':{'pre':{'ids':[neuron]}},'scale':1.01}])
    report=c.compile(design,publish=True,root=tmp_path)
    weights,_=c.load_weights(report['artifact_id'],tmp_path)
    assert report['metadata_sha256']==g.manifest['files']['neurons.json']
    expected=g.baseline_weights().copy();mask=g.pre==g.pre[0]
    expected[mask]=(expected[mask]*np.exp(round(np.log(1.01),12))).astype(np.float32)
    np.testing.assert_array_equal(weights,expected)
