"""Version dispatch, immutable identity and scientifically bounded motor regression tests."""
import copy
import json
import numpy as np
import pytest
from flyarena.common import DATA, digest
from flyarena.contracts import MatchRequest, TournamentRequest
from flyarena.experiments.motor import MotorTransfer, MOTOR
from flyarena.experiments.probes import profile_manifest, runtime_closure
from flyarena.runner import runtime_manifest
from flyarena.scenarios import scenario, arena_scene
from flyarena.services.ranking import rank, tournament_projection
from test_research_service import lab


def test_missing_bridge_field_is_legacy_and_unknown_rejected():
    request=MatchRequest(fly_ids=['1'*32],mode='forage')
    assert request.bridge_profile=='legacy-v1'
    assert arena_scene('orchard',42)==scenario('orchard',42)
    new=arena_scene('orchard',42,'sensorimotor-research-v2')
    assert new['spawns'][0][2]==pytest.approx(.65)
    assert new['food']==scenario('orchard',42)['food']
    assert new['sha256'] != scenario('orchard',42)['sha256']
    with pytest.raises(ValueError): MatchRequest(fly_ids=['1'*32],mode='forage',bridge_profile='cuda')
    with pytest.raises(ValueError): runtime_manifest(bridge_profile='unknown')


def test_transfer_neural_only_symmetry_bounds_and_stop():
    a,b=MotorTransfer(),MotorTransfer()
    assert np.array_equal(a.advance([0,0]),[0,0])
    for _ in range(100):
        left=a.advance([.4,.8]);right=b.advance([.8,.4])
        np.testing.assert_allclose(left,right[::-1])
        assert 0 <= left.min() <= left.max() <= 1.5
    assert left[1]>left[0]
    for _ in range(200): stopped=a.advance([0,0])
    assert stopped.max()<1e-7
    with pytest.raises(ValueError):a.advance([np.nan,0])
    with pytest.raises(ValueError):a.advance([1,2,3])


@pytest.mark.integration
def test_full_source_version_and_training_identity_preserved():
    manifest=profile_manifest()
    assert manifest['ready'] and manifest['motor_id']==MOTOR['id']
    closure=runtime_closure()
    assert manifest['hashes']['runtime_closure']==digest(closure)
    assert {'experiments/motor.py','experiments/probes.py','runner.py','judge.py','research.py','backend.py'} <= closure['sources'].keys()
    assert closure['dependencies']['flygym']['file_count']>0
    v2=runtime_manifest(bridge_profile='sensorimotor-research-v2')
    assert v2['actual_backend']=='cpu-numba'
    assert digest(v2)!=digest(runtime_manifest())


def test_actual_metadata_discovery_contract_and_unknown_values(lab):
    result=lab.client.get('/api/v1/connectome/annotations?field=class&q=olf&limit=1')
    assert result.status_code==200
    assert result.json()=={'field':'class','items':[{'value':'olfactory','count':1}],
                           'metadata_sha256':lab.compiler.graph.manifest['files']['neurons.json'],'total':1}
    assert lab.client.get('/api/v1/connectome/annotations?field=class&q=ORN').json()['items']==[]
    for query in ['field=roi','field=class&limit=101','field=class&limit=0']:
        assert lab.client.get('/api/v1/connectome/annotations?'+query).status_code==422


def test_arena_admission_dispatch_and_tournament_profile(lab,monkeypatch):
    monkeypatch.setattr('flyarena.api.require_bridge',lambda p:None)
    monkeypatch.setattr('flyarena.api.runtime_manifest',lambda **kw: {'bridge':kw.get('bridge_profile','legacy-v1')})
    ids=[lab.fly['id'],lab.service.references()['wildtype']['id']]
    body={'fly_ids':ids,'bridge_profile':'sensorimotor-research-v2','duration_seconds':1}
    match=lab.client.post('/api/v1/matches',json=body).json()
    assert match['runtime_hash']==digest({'bridge':'sensorimotor-research-v2'})
    tournament=lab.client.post('/api/v1/tournaments',json=body|{'name':'Profile round robin'}).json()
    assert len(tournament['matches'])==2
    assert all(m['request']['bridge_profile']=='sensorimotor-research-v2' and m['runtime_hash']==match['runtime_hash'] for m in tournament['matches'])
    assert lab.client.post('/api/v1/matches',json=body|{'bridge_profile':'not-real'}).status_code==422


def test_unqualified_v2_never_falls_back(lab,monkeypatch,tmp_path):
    monkeypatch.setattr('flyarena.bridge.QUALIFICATION',tmp_path/'missing.json')
    response=lab.client.post('/api/v1/matches',json={'fly_ids':[lab.fly['id']],'mode':'forage','bridge_profile':'sensorimotor-research-v2'})
    assert response.status_code==422 and 'Bridge unavailable' in response.json()['detail']
    assert lab.store.matches()==[]


def test_ranking_profile_is_part_of_scope_even_with_same_runtime():
    ids=['1'*32,'2'*32];flies=[{'id':i} for i in ids]
    base={'status':'verified','runtime_hash':'same','created':1,'request':{'fly_ids':ids,'map_id':'orchard','mode':'contest'},'result':{'scores':[1,0],'winner_slot':0}}
    newer=copy.deepcopy(base);newer['created']=2;newer['request']['bridge_profile']='sensorimotor-research-v2'
    assert rank(flies,[base,newer])[0]['matches']==1
    assert tournament_projection([base,newer],ids)['status']=='incomplete'


def test_final_real_service_arena_receipts_and_scene_tampering_when_present():
    from pathlib import Path
    from flyarena.common import ROOT
    from flyarena.experiments.probes import verify_evidence
    from flyarena.judge import verify
    from flyarena.research import PhenotypeReport
    root=ROOT/'var/research-validation/integration-v2-engine/final'
    if not (root/'summary.json').exists():
        pytest.skip('Run scripts/qualify_integration_v2.py for actual full-graph evidence')
    summary=json.loads((root/'summary.json').read_text())
    # Historical observations remain verifiable under their recorded source identity.
    # They are not a qualification for the current v4 policy or a changed motor.
    qualification=json.loads((root/'qualification.json').read_text())
    assert summary['profile_sha256']==qualification['profile_sha256']
    assert summary['passed'] is False and sum(qualification['checks'].values()) == 12
    experiment=json.loads((root/'experiment.json').read_text())
    assert experiment['status']=='complete' and len(experiment['reports'])==3
    for report in experiment['reports']:
        PhenotypeReport.model_validate(report)
    for path in root.glob('*/report.json'):
        report=json.loads(path.read_text());verified=verify_evidence(path.parent,report)
        assert digest(verified['profile']) == summary['profile_sha256']
        if path.parent.name in {'heldout-left', 'bifurcation-left', 'bifurcation-right'}:
            assert verified['metrics']['food_intake'] == 0
        altered=copy.deepcopy(report);altered['scene']['food'][0]['position'][0]+=1
        with pytest.raises(ValueError,match='report disagrees'):verify_evidence(path.parent,altered)
    arena=json.loads((root/'arena.json').read_text())
    assert set(arena)=={'solo','dual'}
    for item in arena.values():
        m=item['match']
        assert verify(Path(item['folder']),expected_request=m['request'],expected_artifacts=m['artifacts'],expected_runtime_hash=m['runtime_hash'])['status']=='verified'


def test_profile_readiness_rejects_stale_motor_qualification(tmp_path,monkeypatch):
    from flyarena.bridge import match_profiles
    from flyarena.common import write_json
    path=tmp_path/'qualification.json'
    q={'profile_sha256':'0'*64,'checks':{'fabricated-label':True},'receipts':{}}
    q['sha256']=digest(q);write_json(path,q)
    monkeypatch.setattr('flyarena.bridge.QUALIFICATION',path)
    profiles=match_profiles()
    assert profiles[0]['ready'] and not profiles[1]['ready']
    assert profiles[1]['reason']


def test_pinned_historical_ring_scene_reconstructs_without_changing_legacy_default():
    from flyarena.scenarios import receipt_scene
    historical=receipt_scene('ring',42,'legacy-v1','a6da0a58972be8789340fe542f77aeefaa56c682d275cc43f7fae720d21957b2')
    assert historical['spawns']==[[-5,0,0],[5,0,np.pi]]
    assert scenario('ring',42)['spawns'][0][1]==.6
    assert receipt_scene('ring',42,'legacy-v1','unknown')==scenario('ring',42)


def test_real_isolated_artifact_root_job_when_present():
    from pathlib import Path
    from flyarena.common import ROOT
    from flyarena.judge import verify
    path=ROOT/'var/research-validation/integration-v2-engine/job-root-check/summary.json'
    if not path.exists():
        pytest.skip('Requires the actual isolated-root HTTP job check')
    evidence=json.loads(path.read_text());match=evidence['match']
    assert match['status']=='verified' and match['request']['bridge_profile']=='legacy-v1'
    assert verify(Path(evidence['folder']),expected_request=match['request'],expected_artifacts=match['artifacts'],expected_runtime_hash=match['runtime_hash'])['status']=='verified'


def test_legacy_idempotency_defaults_and_retries_after_unavailability(lab,monkeypatch):
    old={'fly_ids':[lab.fly['id']],'map_id':'orchard','mode':'forage','seed':42,'duration_seconds':1}
    admitted=lab.store.add_match(lab.user['id'],old,'historical-runtime',key='old-schema')
    def unavailable(*args,**kwargs):
        raise ValueError('runtime deliberately unavailable')
    monkeypatch.setattr('flyarena.api.require_bridge',unavailable)
    response=lab.client.post('/api/v1/matches',json=old,headers={'Idempotency-Key':'old-schema'})
    assert response.status_code==202 and response.json()['id']==admitted['id']
    assert lab.client.post('/api/v1/matches',json=old|{'seed':43},headers={'Idempotency-Key':'old-schema'}).status_code==422
    modern=old|{'bridge_profile':'sensorimotor-research-v2'}
    admitted=lab.store.add_match(lab.user['id'],modern,'old-v2-runtime',key='v2-retry')
    response=lab.client.post('/api/v1/matches',json=modern,headers={'Idempotency-Key':'v2-retry'})
    assert response.status_code==202 and response.json()['id']==admitted['id']
    refs=lab.service.references()
    tour={'name':'Legacy tournament','fly_ids':[lab.fly['id'],refs['wildtype']['id']],
          'map_id':'orchard','mode':'contest','seeds':[42],'duration_seconds':1}
    admitted=lab.store.add_tournament(lab.user['id'],tour,'historical-runtime',key='old-tournament')
    response=lab.client.post('/api/v1/tournaments',json=tour,headers={'Idempotency-Key':'old-tournament'})
    assert response.status_code==202 and response.json()['id']==admitted['id']


# Synthetic complete observations for policy tests, NEVER scientific qualification.
# The real receipt/checkpoint verifier runs; only the current source/profile provider
# is replaced with an explicitly synthetic identity. No motor/probe simulation runs.
@pytest.fixture(scope='module')
def qualification_fixture(tmp_path_factory):
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import patch
    from flyarena.body import Bodies
    from flyarena.common import file_sha, write_json
    from flyarena.compiler import BUDGET
    from flyarena.neural import Brain, PROFILE
    from flyarena.experiments import qualification as policy
    from flyarena.experiments.probes import make_scene, measured_metrics
    root = tmp_path_factory.mktemp('synthetic-policy-observations')
    closure = {'fixture': 'synthetic-contract-test-not-real-trial',
               'dependencies': {'flygym': {'version': '2.1.0'}, 'mujoco': {'version': '3.9.0'}}}
    profile = {'id': 'sensorimotor-research-v2', 'ready': True, 'motor_id': 'dn-cpg-fixture-v4',
               'model_id': 'malecns-lif-cpu-v1', 'embodiment_id': 'neurofly-mujoco-v1',
               'actual_backend': 'cpu-numba', 'protocol_id': 'probe-protocol-v3',
               'hashes': {'runtime_closure': digest(closure), 'connectome': policy.GRAPH}}
    phenotype = {'connectome_sha256': policy.GRAPH,
                 'weights_sha256': '707b0ee32b27417bd44587f32686dc0e6d5da73e7a408ac6d5a7ef6ec8a51739',
                 'neuron_parameters': {'tau_scale': 1., 'threshold_shift_mv': 0.},
                 'model': PROFILE, 'budget': BUDGET}
    assert digest(phenotype) == policy.WT_ARTIFACT
    # Use the real emitters for complete, correctly typed full-graph/body layouts.
    # Horizon/drive assignments below are synthetic, just like the observations;
    # these fixtures never claim to have simulated successful held-out trials.
    brain = Brain(SimpleNamespace(n=165122), weights=np.empty(0)).checkpoint()
    body = Bodies(make_scene('gradient-v2', 20042), 1, 20042)
    for _ in range(100):
        body.step(np.array([[.2, .2]]))
    physics = body.checkpoint()
    for name, probe, seed, seconds, options in policy.CASES:
        folder = root / name
        folder.mkdir()
        scene = make_scene(probe, seed)
        controls = name in ('blank', 'output-ablation')
        trajectory, trace = [], []
        for index in range(seconds * 100 + 1):
            t = index * .01
            fraction = 0. if controls else index / (seconds * 100)
            trajectory.append({'time': t, 'x': float(fraction * scene['food'][0]['position'][0]),
                               'y': float(fraction * scene['food'][0]['position'][1]),
                               'yaw': 0. if controls else float(scene['mirror'] * min(t, .5) * .2)})
            row = dict.fromkeys(policy.TRACE_FIELDS, 0.)
            row.update(time=t, z=1., upright_z=1., game_energy=100., wall_contact_ticks=0,
                       food_intake=1. if index == seconds * 100 and not controls else 0.)
            drive = .2 if not controls and not (name == 'delayed-cue' and t >= 1.) else 0.
            row.update(drive_left=drive, drive_right=drive)
            trace.append(row)
        conditions = {'profile': profile, 'runtime': closure, 'scene': scene, 'seed': seed,
                      'duration_seconds': seconds, 'probe_id': probe, 'ablation': options.get('ablation'),
                      'stimulus': options.get('stimulus', 'normal'), 'decoder_version': 'v2'}
        evidence = {'schema_version': 'probe-report/v2', 'fly_id': policy.WT_FLY,
                    'artifact_id': policy.WT_ARTIFACT, 'condition_key': digest(conditions),
                    'probe_id': probe, 'seed': seed, 'duration_seconds': seconds,
                    'trajectory': trajectory, 'neural_trace': trace, 'profile': profile,
                    'scene': scene, 'metrics': measured_metrics(trajectory, trace, scene)}
        write_json(folder/'evidence.json', evidence)
        write_json(folder/'scene.json', scene)
        write_json(folder/'events.json', [])
        brain['tick'] = np.array(seconds * 10000, dtype=np.int64)
        physics['tick'] = brain['tick'].copy()
        physics['integration'][0] = seconds
        physics['drives'][0] = [trace[-1]['drive_left'], trace[-1]['drive_right']]
        np.savez_compressed(folder/'brain.npz', **brain)
        np.savez_compressed(folder/'physics.npz', **physics)
        receipt = {'schema_version': 'probe-receipt/v2', 'conditions': conditions,
                   'subject': {'fly_id': policy.WT_FLY, 'artifact_id': policy.WT_ARTIFACT,
                               'phenotype': phenotype, 'weights_sha256': phenotype['weights_sha256']},
                   'neuron_count': 165122, 'edge_count': 25563197, 'final_tick': seconds*10000,
                   'total_spikes': 0, 'wall_seconds': .01,
                   'files': {f: file_sha(folder/f) for f in ['scene.json', 'evidence.json', 'events.json', 'brain.npz', 'physics.npz']}}
        receipt['sha256'] = digest(receipt)
        write_json(folder/'receipt.json', receipt)
        write_json(folder/'report.json', evidence | {'status': 'complete', 'receipt_sha256': receipt['sha256']})
    with patch.object(policy, 'runtime_closure', lambda: copy.deepcopy(closure)):
        document = policy.build_qualification(root, profile)
    assert len(document['checks']) == 15 and all(document['checks'].values())
    write_json(root/'qualification.json', document)
    return root, profile, closure


@pytest.fixture
def qualified_fixture(qualification_fixture, tmp_path, monkeypatch):
    import shutil
    from flyarena.experiments import qualification as policy
    original, profile, closure = qualification_fixture
    root = tmp_path/'qualification'
    shutil.copytree(original, root)
    monkeypatch.setattr(policy, 'runtime_closure', lambda: copy.deepcopy(closure))
    monkeypatch.setattr('flyarena.bridge.profile_manifest', lambda *args: copy.deepcopy(profile))
    monkeypatch.setattr('flyarena.bridge.QUALIFICATION', root/'qualification.json')
    return root, copy.deepcopy(profile)


def _write_qualification(root, document):
    from flyarena.common import write_json
    document.pop('sha256', None)
    document['sha256'] = digest(document)
    write_json(root/'qualification.json', document)


def _rewrite_trial(root, name, change):
    """Keep hashes internally consistent so rejection exercises semantic policy."""
    from flyarena.common import file_sha, write_json
    folder = root/name
    receipt = json.loads((folder/'receipt.json').read_text())
    evidence = json.loads((folder/'evidence.json').read_text())
    change(receipt, evidence)
    evidence['condition_key'] = digest(receipt['conditions'])
    write_json(folder/'evidence.json', evidence)
    write_json(folder/'scene.json', receipt['conditions']['scene'])
    receipt['files'] = {name: file_sha(folder/name) for name in receipt['files']}
    receipt.pop('sha256')
    receipt['sha256'] = digest(receipt)
    write_json(folder/'receipt.json', receipt)
    write_json(folder/'report.json', evidence | {'status': 'complete', 'receipt_sha256': receipt['sha256']})


def _assert_both_admissions_rejected(lab):
    ids = [lab.fly['id'], lab.service.references()['wildtype']['id']]
    body = {'fly_ids': ids, 'bridge_profile': 'sensorimotor-research-v2', 'duration_seconds': 1}
    for route in ('matches', 'tournaments'):
        response = lab.client.post('/api/v1/'+route, json=body | ({'name': 'Policy fixture'} if route == 'tournaments' else {}))
        assert response.status_code == 422, response.text
        assert 'Bridge unavailable' in response.json()['detail']
    assert lab.store.matches() == []
    season = lab.client.get('/api/v1/season').json()
    assert season['default_bridge_profile'] == 'legacy-v1'
    assert season['match_profiles'][1]['ready'] is False


def test_complete_recomputed_proof_admits_match_and_tournament(qualified_fixture, lab, monkeypatch):
    from flyarena.bridge import match_profiles
    from flyarena.experiments.qualification import verify_qualification
    root, profile = qualified_fixture
    assert all(verify_qualification(root/'qualification.json', profile)['checks'].values())
    assert match_profiles()[1]['ready'] is True
    monkeypatch.setattr('flyarena.api.runtime_manifest', lambda **kw: {'fixture': 'synthetic'})
    ids = [lab.fly['id'], lab.service.references()['wildtype']['id']]
    body = {'fly_ids': ids, 'bridge_profile': 'sensorimotor-research-v2', 'duration_seconds': 1}
    assert lab.client.post('/api/v1/matches', json=body).status_code == 202
    tournament = lab.client.post('/api/v1/tournaments', json=body | {'name': 'Policy fixture'})
    assert tournament.status_code == 202, tournament.text
    assert all(m['request']['bridge_profile'] == 'sensorimotor-research-v2' for m in tournament.json()['matches'])


@pytest.mark.parametrize('exploit', ['empty-receipts-unknown-gate', 'flipped-failed-gates'])
def test_prior_qualification_exploits_never_admit(qualified_fixture, lab, exploit):
    from flyarena.experiments.qualification import build_qualification, verify_qualification
    root, profile = qualified_fixture
    if exploit == 'empty-receipts-unknown-gate':
        document = {'profile_sha256': digest(profile), 'checks': {'fabricated-label': True}, 'receipts': {}}
    else:
        # Verified observations contain the same three zero-intake failures as v3.
        from flyarena.experiments.probes import measured_metrics
        def zero_intake(receipt, evidence):
            for row in evidence['neural_trace']:
                row['food_intake'] = 0.
            evidence['metrics'] = measured_metrics(evidence['trajectory'], evidence['neural_trace'], evidence['scene'])
        for name in ('heldout-left', 'heldout-repeat', 'bifurcation-left', 'bifurcation-right'):
            _rewrite_trial(root, name, zero_intake)
        document = build_qualification(root, profile)
        assert sum(document['checks'].values()) == 12
        _write_qualification(root, document)
        assert sum(verify_qualification(root/'qualification.json', profile)['checks'].values()) == 12
        _assert_both_admissions_rejected(lab)
        document['checks'] = dict.fromkeys(document['checks'], True)
    _write_qualification(root, document)
    with pytest.raises(ValueError):
        verify_qualification(root/'qualification.json', profile)
    _assert_both_admissions_rejected(lab)


@pytest.mark.parametrize('mutation', [
    'unknown-top', 'missing-top', 'unknown-schema', 'missing-schema', 'unknown-gate', 'missing-gate',
    'integer-gate', 'string-gate', 'null-gate', 'list-gates', 'unknown-trial', 'missing-trial',
    'empty-receipts', 'null-receipts', 'invalid-receipt-hash', 'stale-profile', 'stale-policy',
    'unknown-metric', 'missing-metric', 'boolean-metric', 'false-measurement', 'unknown-measurement',
    'wrong-digest', 'duplicate-json-key', 'nonfinite-json', 'null-document', 'list-document',
])
def test_strict_qualification_document_rejection(qualified_fixture, lab, mutation):
    from flyarena.experiments.qualification import verify_qualification
    root, profile = qualified_fixture
    path = root/'qualification.json'
    q = json.loads(path.read_text())
    if mutation == 'unknown-top': q['unknown'] = True
    elif mutation == 'missing-top': del q['metrics']
    elif mutation == 'unknown-schema': q['schema_version'] = 'motor-qualification/v3'
    elif mutation == 'missing-schema': del q['schema_version']
    elif mutation == 'unknown-gate': q['checks']['unknown'] = True
    elif mutation == 'missing-gate': q['checks'].pop('repeat-identical')
    elif mutation == 'integer-gate': q['checks']['repeat-identical'] = 1
    elif mutation == 'string-gate': q['checks']['repeat-identical'] = 'true'
    elif mutation == 'null-gate': q['checks']['repeat-identical'] = None
    elif mutation == 'list-gates': q['checks'] = [True]*15
    elif mutation == 'unknown-trial': q['receipts']['unknown'] = 'a'*64
    elif mutation == 'missing-trial': q['receipts'].pop('blank')
    elif mutation == 'empty-receipts': q['receipts'] = {}
    elif mutation == 'null-receipts': q['receipts'] = None
    elif mutation == 'invalid-receipt-hash': q['receipts']['blank'] = True
    elif mutation == 'stale-profile': q['profile_sha256'] = '0'*64
    elif mutation == 'stale-policy': q['policy_sha256'] = '0'*64
    elif mutation == 'unknown-metric': q['metrics']['blank']['unknown'] = 0.
    elif mutation == 'missing-metric': q['metrics']['blank'].pop('mean_drive')
    elif mutation == 'boolean-metric': q['metrics']['blank']['mean_drive'] = False
    elif mutation == 'false-measurement': q['measured']['heldout-left']['closest_distance_mm'] = 999.
    elif mutation == 'unknown-measurement': q['measured']['heldout-left']['unknown'] = 0.
    _write_qualification(root, q)
    if mutation == 'wrong-digest':
        q['sha256'] = '0'*64; path.write_text(json.dumps(q))
    elif mutation == 'duplicate-json-key': path.write_text(path.read_text()[:-1]+',"schema_version":"motor-qualification/v4"}')
    elif mutation == 'nonfinite-json': path.write_text(path.read_text().replace('0.0', 'NaN', 1))
    elif mutation == 'null-document': path.write_text('null')
    elif mutation == 'list-document': path.write_text('[]')
    with pytest.raises(ValueError): verify_qualification(path, profile)
    _assert_both_admissions_rejected(lab)


@pytest.mark.parametrize('field,value', [
    ('seed', 10042), ('seed', 20042.), ('seed', True), ('duration_seconds', 3),
    ('duration_seconds', 10.), ('probe_id', 'bifurcation-v2'), ('stimulus', 'blank'),
    ('ablation', 'output'), ('decoder_version', 'v1'), ('unknown', True),
    ('runtime', {}), ('profile', {}), ('scene', {}), ('stimulus', None),
])
def test_strict_receipt_condition_rejection(qualified_fixture, lab, field, value):
    from flyarena.experiments.qualification import build_qualification
    root, profile = qualified_fixture
    def change(receipt, evidence):
        receipt['conditions'][field] = value
        if field in evidence: evidence[field] = value
    _rewrite_trial(root, 'heldout-left', change)
    with pytest.raises(ValueError): build_qualification(root, profile)
    _assert_both_admissions_rejected(lab)


@pytest.mark.parametrize('mutation', ['missing-control', 'wrong-control', 'short-horizon', 'wrong-subject',
    'receipt-schema', 'missing-condition', 'unknown-receipt', 'bool-count', 'small-graph', 'metric-lie',
    'bool-observation', 'unknown-observation', 'missing-observation', 'checkpoint', 'missing-file', 'symlink'])
def test_required_trial_evidence_rejection(qualified_fixture, lab, tmp_path, mutation):
    from flyarena.experiments.qualification import build_qualification
    root, profile = qualified_fixture
    name = 'blank' if mutation in ('missing-control', 'wrong-control') else 'heldout-left'
    def change(receipt, evidence):
        if mutation == 'missing-control': del receipt['conditions']['stimulus']
        elif mutation == 'wrong-control': receipt['conditions']['stimulus'] = 'normal'
        elif mutation == 'short-horizon': evidence['trajectory'].pop()
        elif mutation == 'wrong-subject': receipt['subject']['fly_id'] = evidence['fly_id'] = '1'*32
        elif mutation == 'receipt-schema': receipt['schema_version'] = 'probe-receipt/v99'
        elif mutation == 'missing-condition': del receipt['conditions']['ablation']
        elif mutation == 'unknown-receipt': receipt['unknown'] = True
        elif mutation == 'bool-count': receipt['neuron_count'] = True
        elif mutation == 'small-graph': receipt['neuron_count'] = 99999
        elif mutation == 'metric-lie': evidence['metrics']['food_intake'] = 99.
        elif mutation == 'bool-observation': evidence['neural_trace'][-1]['food_intake'] = True
        elif mutation == 'unknown-observation': evidence['trajectory'][0]['unknown'] = 0.
        elif mutation == 'missing-observation': del evidence['neural_trace'][0]['upright_z']
        elif mutation == 'checkpoint': np.savez_compressed(root/name/'physics.npz', tick=1)
    _rewrite_trial(root, name, change)
    if mutation == 'missing-file': (root/name/'brain.npz').unlink()
    elif mutation == 'symlink':
        moved = tmp_path/'redirected.json'
        (root/name/'report.json').rename(moved)
        (root/name/'report.json').symlink_to(moved)
    with pytest.raises(ValueError): build_qualification(root, profile)
    _assert_both_admissions_rejected(lab)


def test_evaluator_and_source_changes_invalidate_proof(qualified_fixture, monkeypatch):
    from flyarena.experiments import qualification as policy
    from flyarena.bridge import match_profiles
    root, profile = qualified_fixture
    original = policy.file_sha
    monkeypatch.setattr(policy, 'file_sha', lambda path: 'f'*64 if path.name == 'qualification.py' else original(path))
    with pytest.raises(ValueError, match='evaluator source'):
        policy.verify_qualification(root/'qualification.json', profile)
    assert match_profiles()[1]['ready'] is False
    monkeypatch.setattr(policy, 'file_sha', original)
    monkeypatch.setattr(policy, 'runtime_closure', lambda: {'changed': 'source'})
    with pytest.raises(ValueError, match='source closure'):
        policy.verify_qualification(root/'qualification.json', profile)
    assert match_profiles()[1]['ready'] is False


CHECKPOINT_FIELDS = {
    'brain.npz': ('v', 'current', 'refractory', 'delay', 'external', 'rates', 'tick', 'total_spikes'),
    'physics.npz': ('integration', 'tick', 'drives', '0_retraction_correction',
                    '0_stumbling_correction', '0_retraction_persistence_counter', '0_phases', '0_magnitudes'),
}


def _assert_checkpoint_rejected(root, profile, lab):
    from flyarena.experiments.probes import verify_evidence
    from flyarena.experiments.qualification import build_qualification, verify_qualification
    _rewrite_trial(root, 'heldout-left', lambda receipt, evidence: None)
    # Rehash the entire chain, including the qualification's receipt reference.
    receipt = json.loads((root/'heldout-left/receipt.json').read_text())
    document = json.loads((root/'qualification.json').read_text())
    document['receipts']['heldout-left'] = receipt['sha256']
    _write_qualification(root, document)
    report = json.loads((root/'heldout-left/report.json').read_text())
    with pytest.raises(ValueError, match='checkpoint'):
        verify_evidence(root/'heldout-left', report)
    with pytest.raises(ValueError, match='checkpoint'):
        build_qualification(root, profile)
    with pytest.raises(ValueError, match='checkpoint'):
        verify_qualification(root/'qualification.json', profile)
    _assert_both_admissions_rejected(lab)


@pytest.mark.parametrize('filename,field', [(f, k) for f, keys in CHECKPOINT_FIELDS.items() for k in keys])
@pytest.mark.parametrize('mutation', ['missing', 'shape', 'dtype', 'nonfinite'])
def test_rehashed_checkpoint_fields_rejected_by_research_and_admission(qualified_fixture, lab, filename, field, mutation):
    root, profile = qualified_fixture
    path = root/'heldout-left'/filename
    with np.load(path, allow_pickle=False) as archive:
        state = dict(archive)
    value = state[field]
    if mutation == 'missing': del state[field]
    elif mutation == 'shape': state[field] = value.reshape(value.shape + (1,))
    elif mutation == 'dtype': state[field] = value.astype(np.float32 if value.dtype.kind == 'f' else np.float64)
    elif mutation == 'nonfinite':
        state[field] = value.astype(np.float64)
        state[field].flat[0] = np.nan
    np.savez_compressed(path, **state)
    _assert_checkpoint_rejected(root, profile, lab)


@pytest.mark.parametrize('filename,field,value', [
    ('brain.npz', 'tick', np.array(100000.5)),
    ('physics.npz', 'tick', np.array(100000.5)),
    ('brain.npz', 'total_spikes', np.array(True)),
    ('brain.npz', 'total_spikes', np.array(-1, dtype=np.int64)),
    ('brain.npz', 'tick', np.array('100000')),
    ('brain.npz', 'external', np.zeros(165122, dtype=object)),
    ('brain.npz', 'unknown', np.array(0.)),
    ('physics.npz', '1_phases', np.zeros(6)),
    ('physics.npz', 'integration', np.zeros(752)),
    ('physics.npz', 'drives', np.array([[.3, .2]])),
    ('physics.npz', 'drives', np.array([[1.6, .2]])),
    ('physics.npz', '0_phases', np.full(6, np.inf)),
    ('physics.npz', '0_retraction_persistence_counter', np.full(6, -1, dtype=np.int64)),
    ('brain.npz', 'refractory', np.full(165122, 23, dtype=np.int32)),
    ('brain.npz', 'rates', np.full(165122, -1.)),
])
def test_rehashed_malformed_checkpoint_values_rejected(qualified_fixture, lab, filename, field, value):
    root, profile = qualified_fixture
    path = root/'heldout-left'/filename
    with np.load(path, allow_pickle=False) as archive:
        state = dict(archive)
    state[field] = value
    np.savez_compressed(path, **state)
    _assert_checkpoint_rejected(root, profile, lab)


def test_original_stripped_and_rehashed_checkpoint_exploit(qualified_fixture, lab):
    root, profile = qualified_fixture
    path = root/'heldout-left'
    with np.load(path/'brain.npz', allow_pickle=False) as archive:
        brain = {k: archive[k] for k in ('tick', 'total_spikes', 'v')}
    np.savez_compressed(path/'brain.npz', **brain)
    np.savez_compressed(path/'physics.npz', tick=brain['tick'])
    _assert_checkpoint_rejected(root, profile, lab)


@pytest.mark.parametrize('target,field,value', [
    ('profile', 'model_id', 'malecns-lif-cpu-v99'),
    ('profile', 'embodiment_id', 'neurofly-mujoco-v99'),
    ('profile', 'model_id', None),
    ('flygym', 'version', '99.0'),
    ('mujoco', 'version', '99.0'),
    ('receipt', 'schema_version', 'probe-receipt/v99'),
    ('receipt', 'final_tick', 100000.5),
    ('receipt', 'neuron_count', 165122.),
    ('receipt', 'total_spikes', False),
])
def test_checkpoint_dispatch_and_receipt_integers_are_strict(qualified_fixture, lab, target, field, value):
    from flyarena.experiments.probes import verify_evidence
    root, profile = qualified_fixture
    def change(receipt, evidence):
        if target == 'receipt': receipt[field] = value
        elif target == 'profile':
            receipt['conditions']['profile'][field] = value
            evidence['profile'][field] = value
        else: receipt['conditions']['runtime']['dependencies'][target][field] = value
    _rewrite_trial(root, 'heldout-left', change)
    with pytest.raises(ValueError, match='checkpoint'):
        verify_evidence(root/'heldout-left')
    _assert_both_admissions_rejected(lab)
