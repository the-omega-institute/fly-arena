from types import SimpleNamespace
import numpy as np
import pytest
from flyarena.rate import RateBrain,connection_matrix
from flyarena.rate_training import loss_and_gradient,fit
from flyarena.contracts import FlySpec,MatchRequest
from flyarena.compiler import Compiler
from test_core import graph


def teaching_graph():
    g=graph();g.baseline_weights=lambda:np.array([20.,20.,0.],dtype=np.float32)
    g.groups.update({c:np.array([2]) for c in ['local','memory','readout','descending','visual','motor']})
    g.groups['projection']=np.array([1]);g.groups['olfactory_right']=np.array([],dtype=int)
    return g


def test_rate_clock_restore_bounds_and_no_invented_spikes():
    g=teaching_graph();a,b=RateBrain(g),RateBrain(g)
    a.stimulate(.8,.2);b.stimulate(.8,.2);a.advance(1000)
    for n in [1,7,12,81,99,800]:b.advance(n)
    for k in a.checkpoint():np.testing.assert_array_equal(a.checkpoint()[k],b.checkpoint()[k])
    assert a.total_spikes is None and 0<a.rates[2]<=250
    state=a.checkpoint();a.advance(100);expected=a.rates.copy();a.restore(state);a.advance(100)
    np.testing.assert_array_equal(a.rates,expected)
    with pytest.raises(ValueError):a.restore(state|{'rates':np.full(3,np.nan)})
    a.reset();assert a.tick==0 and not a.rates.any()


def test_full_sparse_backprop_matches_finite_differences_and_adam_learns():
    g=teaching_graph();matrix=connection_matrix(g,g.baseline_weights());membership=np.eye(3)[:,:2]
    theta=np.array([.02,-.03]);stimulus=np.array([40.,0.,0.]);neurons=np.array([2]);decoder=np.array([[.2,.4]]);target=np.array([.4,.6])
    args=(stimulus,neurons,decoder,target)
    loss,gradient=loss_and_gradient(matrix,membership,theta,*args,steps=80)
    numeric=[]
    for i in range(2):
        shift=np.eye(2)[i]*1e-5
        numeric.append((loss_and_gradient(matrix,membership,theta+shift,*args,steps=80)[0]-loss_and_gradient(matrix,membership,theta-shift,*args,steps=80)[0])/2e-5)
    np.testing.assert_allclose(gradient,numeric,rtol=1e-5,atol=1e-8)
    delta,record=fit(g,g.baseline_weights(),neurons,decoder,['olfactory','projection'],updates=3,steps=80)
    assert np.linalg.norm(delta)>0 and record['history'][-1]['response_mse']<record['history'][0]['response_mse']


def test_model_artifacts_distinct_and_legacy_unchanged(tmp_path):
    c=Compiler(graph());lif=FlySpec(name='lif',connectome_sha256='a'*64)
    rate=lif.model_copy(update={'model_profile':'malecns-rate-cpu-v1'})
    old=c.compile(lif,publish=True,root=tmp_path);new=c.compile(rate,publish=True,root=tmp_path)
    assert old['artifact_id']!=new['artifact_id'] and old['weights_sha256']==new['weights_sha256']
    weights,manifest=c.load_weights(new['artifact_id'],tmp_path)
    assert manifest['phenotype']['model']['id']==rate.model_profile


def test_real_body_mixed_models_and_replay(tmp_path):
    from test_replay_parity import tiny_assets
    from flyarena.connectome import Connectome
    from flyarena.runner import simulate
    from flyarena.judge import verify
    from flyarena.common import digest
    data,var,old=tiny_assets(tmp_path/'assets');g=Connectome(data)
    report=Compiler(g).compile(FlySpec(name='rate',connectome_sha256=g.manifest['sha256'],model_profile='malecns-rate-cpu-v1'),publish=True,root=var)
    flies=[dict(id='a'*32,name='lif',color='mint',artifact_id=old),dict(id='b'*32,name='rate',color='blue',artifact_id=report['artifact_id'])]
    request=MatchRequest(fly_ids=[f['id'] for f in flies],duration_seconds=1)
    output=tmp_path/'run';receipt=simulate(request,flies,output,data=data,var=var)
    assert receipt['total_spikes'][0]>0 and receipt['total_spikes'][1] is None
    assert [p['id'] for p in receipt['model_profiles']]==['malecns-lif-cpu-v1','malecns-rate-cpu-v1']
    assert verify(output,expected_request=request.model_dump(),expected_artifacts=[old,report['artifact_id']],expected_runtime_hash=digest(receipt['runtime']))['status']=='verified'


def test_lineage_model_switch_and_research_bridge_admission(tmp_path):
    from flyarena.store import Store
    from flyarena.services.training import TrainingService
    store=Store(tmp_path);c=Compiler(graph())
    lif=FlySpec(name='lif',connectome_sha256='a'*64);parent=store.add_fly('u',lif.model_dump(),c.compile(lif))
    spec=lif.model_copy(update={'model_profile':'malecns-rate-cpu-v1','parent_id':parent['id']})
    child=store.add_fly('u',spec.model_dump(),c.compile(spec));assert child['spec']['parent_id']==parent['id']
    request=MatchRequest(fly_ids=[child['id']],mode='forage',duration_seconds=1)
    assert store.add_match('u',request.model_dump(),'runtime')['status']=='queued'
    with pytest.raises(ValueError,match='legacy arena bridge'):
        store.add_match('u',request.model_copy(update={'bridge_profile':'sensorimotor-research-v2'}).model_dump(),'runtime')
    with pytest.raises(ValueError,match='legacy arena bridge'):
        TrainingService(store,lambda:c).create('u',{'founder_id':child['id'],'bridge_profile':'sensorimotor-research-v2'},'runtime')
