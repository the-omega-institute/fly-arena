"""Focused diagnostic integrity tests; no full graph integration outside the assay."""
import numpy as np
import pytest
from flyarena.diagnostics.assay_v5 import waveforms,raw_pair,labels,causal_features,fit_probe,predict_probe
from flyarena.diagnostics.contact import contact_geometry,sample_contact


def test_waveform_bounds_terminal_matching_and_mirrors():
    rows=waveforms(); raw=np.array([r['raw'] for r in rows])
    assert raw.shape==(24,60,2) and np.isfinite(raw).all() and raw.min()>=0
    y=labels(raw)
    for i in range(6):
        np.testing.assert_array_equal(raw[i,30:],raw[i+6,30:])
        assert not np.array_equal(raw[i,:30],raw[i+6,:30])
        np.testing.assert_allclose(y[i,30:,0],rows[i]['terminal_contrast'],atol=1e-15)
        np.testing.assert_allclose(y[i,30:,1],rows[i]['terminal_common'],atol=1e-15)
    for a,b in [(12,13),(14,15),(16,17),(18,19)]:
        np.testing.assert_array_equal(raw[a,:,::-1],raw[b])
    for a,b in [(12,14),(13,15),(16,18),(17,19)]:
        np.testing.assert_allclose(raw[a,30],raw[b,30],atol=1e-15)
        assert y[a,30,2]>0>y[b,30,2]
    np.testing.assert_array_equal(raw[12],raw[23])


def test_features_and_labels_causal_future_invariance_and_no_sequence_leak():
    rng=np.random.default_rng(7); x=rng.normal(size=(3,60,4))
    original=causal_features(x,'history'); changed=x.copy();changed[:,31:]=1e6
    np.testing.assert_array_equal(original[:,:31],causal_features(changed,'history')[:,:31])
    changed=x.copy();changed[0]=1e6
    np.testing.assert_array_equal(original[1:],causal_features(changed,'history')[1:])
    np.testing.assert_array_equal(original[:,0,4:],0)
    np.testing.assert_array_equal(original[:,10,4:8],x[:,5]/100)
    np.testing.assert_array_equal(original[:,10,8:],x[:,0]/100)
    raw=np.array([r['raw'] for r in waveforms()]); y=labels(raw);raw[:,31:]=4
    np.testing.assert_array_equal(y[:,:31],labels(raw)[:,:31])


def test_training_scaling_constant_drop_and_silence():
    x=np.array([[1.,2.,7.],[2.,1.,7.],[3.,4.,7.],[4.,3.,7.]])
    y=np.array([[1.,0.,-1.],[2.,1.,0.],[3.,2.,1.],[4.,3.,2.]])
    model=fit_probe(x,y)
    np.testing.assert_array_equal(model['active'],[True,True,False])
    np.testing.assert_allclose(model['mean'],x.mean(axis=0))
    saved={k:v.copy() for k,v in model.items()}
    test=np.array([[1e8,-1e8,2e8],[2.,2.,7.]])
    prediction=predict_probe(model,test,np.array([False,True]))
    assert np.isfinite(prediction).all()
    np.testing.assert_array_equal(prediction[1],0)
    for k in saved:np.testing.assert_array_equal(model[k],saved[k])


def test_contact_exact_boundaries_and_resource_independence():
    at=contact_geometry([0,0,2.5],[[0,0],[1.1,0],[1.100001,0]],[10,10,10])
    assert at['horizontal_eligible'].tolist()==[True,True,False]
    assert not at['feeding_eligible'].any()
    low=contact_geometry([0,0,2.5-1e-9],[[0,0],[1.1,0]],[0,10])
    assert low['geometry_eligible'].tolist()==[True,True]
    assert low['feeding_eligible'].tolist()==[False,True]
    with pytest.raises(ValueError):contact_geometry([0,0,0],[[0,0]],[])


def test_live_pose_reads_rotated_head_and_copies():
    from types import SimpleNamespace
    class Body:
        head_ids=[0];tick=100
        data=SimpleNamespace(site_xpos=np.array([[2.,3.,4.]]),
            site_xmat=np.array([[0.,-1.,0.,1.,0.,0.,0.,0.,1.]]))
        def mouth(self,slot):return self.data.site_xpos[0]+self.data.site_xmat[0].reshape(3,3)@np.array([.35,0,-.2])
        def antennae(self,slot):return (np.array([1.,2.,3.]),np.array([4.,5.,6.]))
        def pose(self,slot):return np.zeros(3),np.eye(3)
    body=Body();s=sample_contact(body,0,[[2,3]],[10],actual_intake_delta=.08,actual_intake_total=.16)
    np.testing.assert_allclose(s['mouth_position_mm'],[2.,3.35,3.8])
    assert s['actual_intake_delta']==.08 and s['actual_intake_total']==.16
    body.data.site_xpos[0]=0
    np.testing.assert_array_equal(s['head_position_mm'],[2.,3.,4.])
