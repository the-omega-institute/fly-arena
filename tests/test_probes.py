import json
from pathlib import Path
import numpy as np
import pytest
from flyarena.common import DATA, digest, write_json
from flyarena.experiments.sensor import encode_odor
from flyarena.experiments.probes import make_scene, sample_odor, probe_catalog, profile_manifest, measured_metrics, verify_evidence

def test_sensor_retains_superunit_contrast_and_absence():
    np.testing.assert_array_equal(encode_odor(0,0),[0,0])
    a=encode_odor(2,1.2);b=encode_odor(1.2,2)
    assert 1>=a[0]>a[1]>=0
    np.testing.assert_array_equal(a,b[::-1])
    assert encode_odor(.05,.05).mean()<encode_odor(.5,.5).mean()
    with pytest.raises(ValueError):encode_odor(float('nan'),1)

def test_real_disappearance_and_mirrored_off_axis_scene():
    a,b=make_scene('gradient-v2',42),make_scene('gradient-v2',43)
    assert a['food'][0]['position'][0]==b['food'][0]['position'][0]
    assert a['food'][0]['position'][1]==-b['food'][0]['position'][1]
    assert a['food'][0]['position'][1]!=0 and a['spawns'][0][2]==0
    s=make_scene('delayed-cue-v2',42);ant=[np.array([0,.45,0]),np.array([0,-.45,0])]
    for t in [0,.24,1.,2.]:assert not sample_odor(s,ant,t,10).any()
    assert sample_odor(s,ant,.5,10).min()>0
    assert {p['id'] for p in probe_catalog()}=={'gradient-v2','bifurcation-v2','delayed-cue-v2'}
    with pytest.raises(ValueError):make_scene('memory-proven',42)

def test_manifest_unprepared_is_cheap_and_fail_closed(tmp_path):
    result=profile_manifest(tmp_path)
    assert result['ready'] is False and 'reason' in result
    assert not list(tmp_path.iterdir())

def test_prepared_readout_gates_and_neural_only_decoder():
    from flyarena.experiments.decoder import Decoder
    path=DATA/'connectome/research-v2/readout.npz'
    if not path.exists():pytest.skip('explicit full graph calibration not installed')
    assert profile_manifest()['ready']
    decoder=Decoder(path)
    np.testing.assert_array_equal(decoder.command(np.zeros(len(decoder.neurons))),[0,0])
    meta=json.loads(path.with_suffix('.json').read_text())
    assert all(meta['quality_gates'].values())
    assert meta['neuron_count']>100000 and meta['edge_count']>20000000

def test_metrics_yaw_not_displacement_heading_and_censored_latency():
    trajectory=[{'time':0,'x':0,'y':0,'yaw':3.1},{'time':.01,'x':1,'y':0,'yaw':-3.1}]
    trace=[{'time':r['time'],'drive_left':0.,'drive_right':0.,'food_intake':0.,'wall_contact_ticks':0,'game_energy':100.} for r in trajectory]
    m=measured_metrics(trajectory,trace,make_scene('gradient-v2',42))
    assert m['yaw_delta_rad']==pytest.approx(2*np.pi-6.2)
    assert m['food_latency_seconds'] is None and m['path_length_mm']==1

def test_receipt_rejects_file_tampering(tmp_path):
    write_json(tmp_path/'scene.json',{})
    receipt={'files':{n:'0'*64 for n in ['scene.json','evidence.json','events.json','brain.npz','physics.npz']}}
    receipt['sha256']=digest(receipt);write_json(tmp_path/'receipt.json',receipt)
    with pytest.raises(ValueError,match='evidence file mismatch'):verify_evidence(tmp_path)

def test_legacy_dictionary_spec_compiles_without_intervention_dependency(tmp_path):
    from types import SimpleNamespace
    from flyarena.compiler import Compiler
    from flyarena.contracts import FlySpec
    g=SimpleNamespace(n=2,e=2,manifest={'sha256':'a'*64},counts=np.array([1,2]),
                      pre=np.array([0,1]),post=np.array([1,0]),groups={'olfactory':np.array([0])},
                      baseline_weights=lambda:np.array([.275,-.55],dtype=np.float32))
    compiler=Compiler(g)
    raw={'name':'Baseline dictionary','connectome_sha256':'a'*64,'weight_mutations':[],'edge_deltas':[]}
    report=compiler.compile(FlySpec.model_validate(raw),publish=True,root=tmp_path)
    weights,_=compiler.load_weights(report['artifact_id'],tmp_path)
    np.testing.assert_array_equal(weights,g.baseline_weights())

def test_full_graph_evidence_and_platform_report_contract_when_requested():
    import os
    from flyarena.research import PhenotypeReport
    root=os.environ.get('ARENA_SCIENCE_EVIDENCE')
    if root is None:pytest.skip('set ARENA_SCIENCE_EVIDENCE to a completed engineering validation directory')
    root=Path(root);summary=json.loads((root/'summary.json').read_text())
    assert summary['passed'] and all(summary['checks'].values())
    assert {'heldout-left','heldout-right'}.issubset(summary['receipts'])
    for path in root.glob('*/report.json'):
        report=json.loads(path.read_text());verify_evidence(path.parent,report)
        # Historical v2 evidence predates the required report.scene field. Its
        # independently verified scene file supplies the additive display envelope.
        visible = report if 'scene' in report else report | {'scene':json.loads((path.parent/'scene.json').read_text())}
        PhenotypeReport.model_validate(visible)
    path=root/'wt-left/report.json';report=json.loads(path.read_text())
    report['metrics']['path_length_mm']+=1
    with pytest.raises(ValueError,match='report disagrees'):verify_evidence(path.parent,report)
