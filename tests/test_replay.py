"""Small synthetic receipt contracts, not scientific qualification evidence."""
import copy
import json

import numpy as np
import pytest

from flyarena.common import digest, file_sha, write_json
from flyarena.contracts import MatchRequest
from flyarena.judge import verify
from flyarena.replay import POLICY, REPLAY_RECEIPT, validate_policy
from flyarena.scenarios import RULES, receipt_scene


def resign(folder):
    receipt = json.loads((folder / 'receipt.json').read_text())
    receipt['files'] = {name: file_sha(folder / name) for name in receipt['files']}
    receipt['sha256'] = digest({k: v for k, v in receipt.items() if k != 'sha256'})
    write_json(folder / 'receipt.json', receipt)


@pytest.fixture
def receipt_factory(tmp_path):
    def create(version=REPLAY_RECEIPT, bridge='legacy-v1', historical_ring=False, end=10000):
        folder = tmp_path / 'evidence'
        folder.mkdir()
        ids = ['a' * 32, 'b' * 32] if historical_ring or end < 10000 else ['a' * 32]
        request = MatchRequest(fly_ids=ids, mode='sumo' if len(ids) == 2 else 'forage',
                               map_id='ring' if len(ids) == 2 else 'orchard',
                               duration_seconds=1, bridge_profile=bridge).model_dump()
        source = 'a6da0a58972be8789340fe542f77aeefaa56c682d275cc43f7fae720d21957b2' if historical_ring else 'f' * 64
        runtime = dict(rules=copy.deepcopy(RULES), sources={'scenarios.py': source, 'replay.py': 'e' * 64})
        if bridge == 'sensorimotor-research-v2':
            closure = {'sources': {'replay.py': 'd' * 64}, 'frozen': 'not-current-source'}
            runtime.update(bridge_profile=bridge, actual_backend='cpu-numba', closure=closure,
                           profile={'id': bridge, 'hashes': {'readout_metadata': 'c' * 64,
                                                            'runtime_closure': digest(closure)}})
        scene = receipt_scene(request['map_id'], request['seed'], bridge, source)
        scene['body'] = {'geoms': [dict(id=i, slot=i, mesh='0') for i in range(len(ids))],
                         'meshes': {'0': {'vertices': [0, 0, 0], 'faces': []}}}
        flies = [dict(id=id_, name='schema fixture', color='mint', artifact_id='b' * 64) for id_ in ids]
        scene['flies'] = flies
        receipt = dict(schema=version, request=request, runtime=runtime, flies=flies,
                       silence_output=False, final_tick=end, readout_sha256='c' * 64)
        cadence = 500
        if version == REPLAY_RECEIPT:
            cadence = 100
            for container in (receipt, runtime, scene):
                container['replay_policy'] = dict(POLICY)
        ticks = list(range(0, end + 1, cadence))
        if ticks[-1] != end:
            ticks.append(end)
        food = [f['initial'] for f in scene['food']]
        frames = [dict(tick=tick, time=tick * .0001, poses=[[0, 0, 0, 1, 0, 0, 0] for _ in ids],
                       positions=[[0, 0, 0] for _ in ids], scores=[0] * len(ids),
                       energy=[100] * len(ids), food=food, drives=[[0, 0] for _ in ids]) for tick in ticks]
        events = [] if end == 10000 else [dict(type='exit', tick=end-17, slot=0)]
        result = dict(final_tick=end, scores=[0] * len(ids), food_remaining=food,
                      exit_ticks=([end-17, None] if events else [None] * len(ids)), contact_ticks=0)
        for name, value in [('frames', frames), ('events', events), ('result', result), ('scene', scene)]:
            write_json(folder / (name + '.json'), value)
        np.savez(folder / 'physics.npz', tick=np.array(end), integration=np.zeros(1))
        for i in range(len(ids)):
            np.savez(folder / f'brain-{i}.npz', tick=np.array(end), v=np.zeros(1))
        receipt['files'] = {p.name: file_sha(p) for p in folder.iterdir()}
        write_json(folder / 'receipt.json', receipt)
        resign(folder)
        return folder
    return create


def change(folder, filename, mutate):
    value = json.loads((folder / filename).read_text())
    mutate(value)
    # JSON's permissive encoder deliberately permits NaN adversaries here.
    (folder / filename).write_text(json.dumps(value))
    resign(folder)


@pytest.mark.parametrize('version,bridge', [('run-receipt/v1', 'legacy-v1'),
    ('run-receipt/v2', 'sensorimotor-research-v2'), (REPLAY_RECEIPT, 'legacy-v1'),
    (REPLAY_RECEIPT, 'sensorimotor-research-v2')])
def test_current_and_historical_frozen_receipts(receipt_factory, version, bridge):
    folder = receipt_factory(version, bridge)
    assert verify(folder)['status'] == 'verified'
    # Frozen hashes intentionally differ from today's sources.
    r = json.loads((folder / 'receipt.json').read_text())
    assert verify(folder, expected_request=r['request'], expected_artifacts=['b' * 64],
                  expected_runtime_hash=digest(r['runtime']))['status'] == 'verified'


@pytest.mark.parametrize('version', ['run-receipt/v1', 'run-receipt/v2', REPLAY_RECEIPT])
def test_unique_partial_terminal(receipt_factory, version):
    bridge = 'sensorimotor-research-v2' if version == 'run-receipt/v2' else 'legacy-v1'
    assert verify(receipt_factory(version, bridge, end=600))['final_tick'] == 600


def test_legacy_ring_source_reconstruction(receipt_factory):
    folder = receipt_factory('run-receipt/v1', historical_ring=True)
    assert verify(folder)['status'] == 'verified'
    change(folder, 'scene.json', lambda s: s['spawns'][0].__setitem__(1, .6))
    with pytest.raises(ValueError, match='Scenario digest'):
        verify(folder)


@pytest.mark.parametrize('field,value', [('pose_ticks', 100.), ('pose_ticks', True),
    ('event_ticks', 500.), ('event_ticks', '500'), ('physics_dt', '.0001'),
    ('physics_dt', float('nan')), ('terminal', None), ('id', 'other')])
def test_strict_policy_types(field, value):
    with pytest.raises(ValueError, match='replay policy'):
        validate_policy(dict(POLICY, **{field: value}), RULES)


@pytest.mark.parametrize('location', ['receipt', 'runtime', 'scene'])
@pytest.mark.parametrize('mutation', ['missing', 'partial', 'conflict', 'float', 'extra', 'null'])
def test_required_identical_policy_in_all_locations(receipt_factory, location, mutation):
    folder = receipt_factory()
    def mutate(value):
        container = value['runtime'] if location == 'runtime' else value
        if mutation == 'missing': container.pop('replay_policy')
        elif mutation == 'partial': container['replay_policy'].pop('terminal')
        elif mutation == 'conflict': container['replay_policy']['pose_ticks'] = 500
        elif mutation == 'float': container['replay_policy']['pose_ticks'] = 100.
        elif mutation == 'extra': container['replay_policy']['unknown'] = 1
        elif mutation == 'null': container['replay_policy'] = None
    change(folder, 'scene.json' if location == 'scene' else 'receipt.json', mutate)
    with pytest.raises(ValueError, match='replay policy'):
        verify(folder)


@pytest.mark.parametrize('version', ['run-receipt/v1', 'run-receipt/v2'])
@pytest.mark.parametrize('location', ['receipt', 'runtime', 'scene'])
def test_legacy_rejects_any_policy_metadata(receipt_factory, version, location):
    folder = receipt_factory(version)
    change(folder, 'scene.json' if location == 'scene' else 'receipt.json',
           lambda c: (c['runtime'] if location == 'runtime' else c).__setitem__('replay_policy', None))
    with pytest.raises(ValueError, match='Legacy receipt'):
        verify(folder)


@pytest.mark.parametrize('version', [None, 'run-receipt/v0', 'run-receipt/v4', 3, []])
def test_exact_version_allowlist(receipt_factory, version):
    folder = receipt_factory()
    change(folder, 'receipt.json', lambda r: r.__setitem__('schema', version))
    with pytest.raises(ValueError, match='Unknown receipt version'):
        verify(folder)


@pytest.mark.parametrize('version', ['run-receipt/v1', REPLAY_RECEIPT])
@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'reorder', 'float-tick', 'bool-tick',
    'wrong-time', 'nan-time', 'bool-time', 'empty-poses', 'short-pose', 'extra-pose',
    'bad-quaternion', 'nan-pose', 'string-pose', 'positions', 'scores', 'energy', 'food', 'drives'])
def test_resigned_malformed_frames_rejected(receipt_factory, version, mutation):
    folder = receipt_factory(version)
    def mutate(frames):
        frame = frames[0]
        if mutation == 'missing': frames.pop(1)
        elif mutation == 'duplicate': frames.append(copy.deepcopy(frames[-1]))
        elif mutation == 'reorder': frames[1], frames[2] = frames[2], frames[1]
        elif mutation == 'float-tick': frame['tick'] = 0.
        elif mutation == 'bool-tick': frame['tick'] = False
        elif mutation == 'wrong-time': frame['time'] = .01
        elif mutation == 'nan-time': frame['time'] = float('nan')
        elif mutation == 'bool-time': frame['time'] = False
        elif mutation == 'empty-poses': frame['poses'] = []
        elif mutation == 'short-pose': frame['poses'][0].pop()
        elif mutation == 'extra-pose': frame['poses'].append(frame['poses'][0])
        elif mutation == 'bad-quaternion': frame['poses'][0][3] = 0
        elif mutation == 'nan-pose': frame['poses'][0][0] = float('nan')
        elif mutation == 'string-pose': frame['poses'][0][0] = '0'
        else: frame[mutation] = []
    change(folder, 'frames.json', mutate)
    with pytest.raises(ValueError):
        verify(folder)


@pytest.mark.parametrize('mutation', ['missing-source', 'bad-source', 'rules', 'float-end', 'bool-end',
    'result-end', 'backend', 'readout', 'closure', 'geometry-slot', 'geometry-duplicate'])
def test_frozen_runtime_endpoint_geometry_and_bridge_checks(receipt_factory, mutation):
    folder = receipt_factory(bridge='sensorimotor-research-v2')
    def mutate(r):
        if mutation == 'missing-source': r['runtime']['closure']['sources'].pop('replay.py')
        elif mutation == 'bad-source': r['runtime']['closure']['sources']['replay.py'] = 'invalid'
        elif mutation == 'rules': r['runtime']['rules']['snapshot_ticks'] = 100
        elif mutation == 'float-end': r['final_tick'] = 10000.
        elif mutation == 'bool-end': r['final_tick'] = True
        elif mutation == 'backend': r['runtime']['actual_backend'] = 'cuda'
        elif mutation == 'readout': r['readout_sha256'] = 'f' * 64
        elif mutation == 'closure': r['runtime']['closure']['changed'] = True
    if mutation.startswith('geometry'):
        change(folder, 'scene.json', lambda s: s['body']['geoms'][0].__setitem__('slot', 1)
               if mutation == 'geometry-slot' else s['body']['geoms'].append(s['body']['geoms'][0]))
    elif mutation == 'result-end':
        change(folder, 'result.json', lambda r: r.__setitem__('final_tick', 10000.))
    else:
        change(folder, 'receipt.json', mutate)
    with pytest.raises(ValueError):
        verify(folder)


@pytest.mark.parametrize('field', ['expected_request', 'expected_artifacts', 'expected_runtime_hash'])
def test_admission_identity_remains_bound(receipt_factory, field):
    folder = receipt_factory()
    request = json.loads((folder / 'receipt.json').read_text())['request']
    value = dict(expected_request=dict(request, seed=43), expected_artifacts=['e' * 64],
                 expected_runtime_hash='a' * 64)[field]
    with pytest.raises(ValueError):
        verify(folder, **{field: value})


def test_metadata_removal_cannot_downgrade_100hz_to_legacy(receipt_factory):
    folder = receipt_factory()
    change(folder, 'scene.json', lambda s: s.pop('replay_policy'))
    def downgrade(r):
        r['schema'] = 'run-receipt/v1'
        r.pop('replay_policy')
        r['runtime'].pop('replay_policy')
    change(folder, 'receipt.json', downgrade)
    with pytest.raises(ValueError, match='missing ticks'):
        verify(folder)


def test_legacy_frame_grid_cannot_masquerade_as_v3(receipt_factory):
    folder = receipt_factory()
    change(folder, 'frames.json', lambda frames: frames.__setitem__(slice(None), frames[::5]))
    with pytest.raises(ValueError, match='missing ticks'):
        verify(folder)
