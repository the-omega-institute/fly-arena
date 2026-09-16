import numpy as np
from scipy.spatial.distance import cdist,pdist
from flyarena.diagnostics.nonlinear_v5 import waveforms,fit_kernel,predict_kernel,metrics
from flyarena.diagnostics.assay_v5 import labels,causal_features,waveforms as old_waveforms


def test_fresh_panel_bounds_pairs_mirrors_and_no_reused_noncontrol():
    rows=waveforms();raw=np.array([r['raw'] for r in rows]);old=np.array([r['raw'] for r in old_waveforms()])
    assert raw.shape==(24,60,2) and np.isfinite(raw).all() and raw.min()>=0
    for i in range(20):assert not any(np.array_equal(raw[i],r) for r in old[:20])
    for i in range(6):
        np.testing.assert_array_equal(raw[i,30:],raw[i+6,30:]);assert not np.array_equal(raw[i,:30],raw[i+6,:30])
    for a,b in [(12,13),(14,15),(16,17),(18,19)]:np.testing.assert_array_equal(raw[a,:,::-1],raw[b])
    y=labels(raw)
    for a,b in [(12,14),(13,15),(16,18),(17,19)]:
        np.testing.assert_array_equal(raw[a,30],raw[b,30]);assert y[a,30,2]*y[b,30,2]<0
    np.testing.assert_array_equal(raw[12],raw[23])


def test_train_only_bandwidth_formula_constant_drop_silence_and_independent_heads():
    x=np.array([[1.,2.,7.],[2.,1.,7.],[3.,4.,7.],[4.,3.,7.]])
    y=np.array([[1.,0.,-1.],[2.,1.,0.],[3.,2.,1.],[4.,3.,2.]])
    m=fit_kernel(x,y);np.testing.assert_array_equal(m['active'],[True,True,False])
    z=((x-x.mean(0))/np.where(x.std(0)>1e-8,x.std(0),1))[:,:2]/np.sqrt(2)
    d=pdist(z);assert m['sigma']==np.median(d[d>0])
    k=np.exp(-cdist(z,z,'sqeuclidean')/(2*float(m['sigma'])**2))
    np.testing.assert_allclose((k+np.eye(4))@m['dual'],y-y.mean(0),atol=1e-14)
    saved={key:v.copy() for key,v in m.items()}
    p=predict_kernel(m,np.array([[1e8,-1e8,2e8],[2.,2.,7.]]),np.array([False,True]))
    assert np.isfinite(p).all();np.testing.assert_array_equal(p[1],0)
    for key in m:np.testing.assert_array_equal(m[key],saved[key])
    changed=y.copy();changed[:,2]*=100
    other=fit_kernel(x,changed)
    np.testing.assert_allclose(m['dual'][:,:2],other['dual'][:,:2])


def test_dn_history_prediction_future_and_other_sequence_invariance():
    rng=np.random.default_rng(4);rates=rng.normal(50,10,(3,60,4));x=causal_features(rates,'history')
    m=fit_kernel(x[0,9:],rng.normal(size=(51,3)));silence=np.zeros((3,60),bool)
    pred=predict_kernel(m,x,silence)
    changed=rates.copy();changed[1,31:]=1e6;changed[2]=1e8
    other=predict_kernel(m,causal_features(changed,'history'),silence)
    np.testing.assert_array_equal(pred[0],other[0]);np.testing.assert_array_equal(pred[1,:31],other[1,:31])
    np.testing.assert_array_equal(x[:,0,4:],0)
    np.testing.assert_array_equal(x[:,10,4:8],rates[:,5]/100)
    np.testing.assert_array_equal(x[:,10,8:],rates[:,0]/100)


def test_gates_enforce_individual_sign_and_mean_not_peak_and_no_empty_pass():
    rows=waveforms();truth=labels(np.array([r['raw'] for r in rows]));pred=truth.copy();silence=np.zeros((24,60),bool)
    protocol=dict(sequences=rows,response_end_ms=list(range(10,601,10)),matched_current_pairs=[])
    assert metrics(pred,truth,silence,protocol)['gate_result']['passed']
    pred[0,44,0]*=-1 # 15/16=93.75% individual despite pooled127/128=99.2%
    g=metrics(pred,truth,silence,protocol)['gate_result'];assert g['pooled_sign_pass'] and not g['per_sequence_sign_pass'] and not g['passed']
    pred=truth.copy();pred[1,44:,0]=np.tile([.05,-.05],8)
    m=metrics(pred,truth,silence,protocol);assert m['gate_result']['passed'] and m['clamp_sequences'][1]['neutral_peak']>.02
    pred[1,44:,0]=.01;assert not metrics(pred,truth,silence,protocol)['gate_result']['neutral_mean_pass']
    silence[0,44:]=True;assert not metrics(truth,truth,silence,protocol)['gate_result']['no_empty_sequence']
