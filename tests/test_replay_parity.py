"""Opt-in old/new real-physics evidence. No network, stores, or qualification writes.

Set FLY_REPLAY_ORIGINAL_ROOT to a read-only pre-replay source/assets checkout and
FLY_REPLAY_OUTPUT to an empty scratch directory. The full case retains every
neuron/edge; the short edge cases deliberately use a four-neuron fixture.
"""
import copy
import importlib.util
import json
import os
from pathlib import Path
import time

import mujoco
import numpy as np
import pytest

from flyarena import runner
from flyarena.body import Bodies
from flyarena.common import digest, file_sha, write_json
from flyarena.compiler import Compiler
from flyarena.connectome import Connectome
from flyarena.contracts import FlySpec, MatchRequest
from flyarena.judge import verify
from flyarena.neural import PROFILE
from flyarena.scenarios import arena_scene


def load_original(root):
    path = root / 'src/flyarena/runner.py'
    spec = importlib.util.spec_from_file_location('flyarena._replay_original_runner', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = root  # Freeze the old manifest to its actual read-only source.
    return module


def tiny_assets(root):
    """Real LIF dynamics and decoder on a deliberately non-biological small graph."""
    data, var = root / 'data', root / 'var'
    folder = data / 'connectome'
    folder.mkdir(parents=True)
    arrays = dict(ids=np.arange(4), pre=np.arange(4, dtype=np.int32),
                  post=np.array([1, 2, 3, 0], dtype=np.int32),
                  counts=np.ones(4, dtype=np.int32), indptr=np.arange(5, dtype=np.int64),
                  signs=np.ones(4, dtype=np.int8), side=np.array([1, -1, 1, -1], dtype=np.int8))
    for key, value in arrays.items():
        np.save(folder / (key + '.npy'), value)
    groups = {key: np.arange(4, dtype=np.int32) for key in
              ['olfactory', 'projection', 'local', 'memory', 'readout', 'descending', 'visual', 'motor']}
    groups.update(olfactory_left=np.array([0, 2]), olfactory_right=np.array([1, 3]))
    np.savez(folder / 'groups.npz', **groups)
    manifest = {'files': {p.name: file_sha(p) for p in folder.iterdir()}}
    manifest['sha256'] = digest(manifest)
    write_json(folder / 'manifest.json', manifest)
    np.savez(folder / 'readout.npz', neurons=np.arange(4), weights=np.full((4, 2), .2))
    readout = dict(connectome_sha256=manifest['sha256'], neural_profile_sha256=digest(PROFILE),
                   readout_sha256=file_sha(folder / 'readout.npz'))
    readout['sha256'] = digest(readout)
    write_json(folder / 'readout.json', readout)
    artifact = Compiler(Connectome(data)).compile(
        FlySpec(name='bounded fixture', connectome_sha256=manifest['sha256']), publish=True, root=var)
    return data, var, artifact['artifact_id']


def observed_bodies(observations):
    class ObservedBodies(Bodies):
        def snapshot(self):
            # Independent read of actual compiled geom poses; no forward/step call.
            before = self.checkpoint()
            poses = []
            for geom in self.replay_geoms:
                quat = np.empty(4)
                mujoco.mju_mat2Quat(quat, self.data.geom_xmat[geom])
                poses.append([*self.data.geom_xpos[geom].round(5).tolist(), *quat.round(6).tolist()])
            frame = super().snapshot()
            assert frame['poses'] == poses
            after = self.checkpoint()
            for key in before:
                np.testing.assert_array_equal(before[key], after[key], err_msg=key)
            observations[self.tick] = copy.deepcopy(frame)
            return frame
    return ObservedBodies


def compare_pair(old, new, request, flies, output, data, var, *, scientific_limit, admit=True):
    receipts, progress, snapshots, elapsed = {}, {}, {}, {}
    for name, module in [('old', old), ('new', new)]:
        progress[name], snapshots[name] = [], {}
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(module, 'Bodies', observed_bodies(snapshots[name]))
            started = time.perf_counter()
            receipts[name] = module.simulate(request, flies, output / name, progress[name].append,
                                            data=data, var=var)
            elapsed[name] = time.perf_counter() - started
    a, b = output / 'old', output / 'new'
    read = lambda path: json.loads(path.read_text())
    oldframes, newframes = read(a / 'frames.json'), read(b / 'frames.json')
    by_tick = {f['tick']: f for f in newframes}
    assert len(by_tick) == len(newframes)
    assert all(frame == by_tick[frame['tick']] for frame in oldframes)
    assert progress['old'] == progress['new']
    assert read(a / 'events.json') == read(b / 'events.json')
    assert read(a / 'result.json') == read(b / 'result.json')
    assert receipts['old']['total_spikes'] == receipts['new']['total_spikes']
    checkpoint_keys = {}
    for filename in ['physics.npz'] + [f'brain-{i}.npz' for i in range(len(flies))]:
        with np.load(a / filename) as left, np.load(b / filename) as right:
            assert left.files == right.files
            checkpoint_keys[filename] = left.files
            for key in left.files:
                np.testing.assert_array_equal(left[key], right[key], err_msg=filename + ':' + key)
    for frame in newframes:
        assert {key: frame[key] for key in snapshots['new'][frame['tick']]} == snapshots['new'][frame['tick']]
    oldscene, newscene = read(a / 'scene.json'), read(b / 'scene.json')
    newscene.pop('replay_policy')
    assert oldscene == newscene
    if admit:
        for name in ['old', 'new']:
            verify(output / name, expected_request=request.model_dump(),
                   expected_artifacts=[f['artifact_id'] for f in flies],
                   expected_runtime_hash=digest(receipts[name]['runtime']))
    oldticks = {f['tick'] for f in oldframes}
    result = dict(scientific_limit=scientific_limit, old_runner_sha256=file_sha(Path(old.__file__)),
                  final_tick=receipts['new']['final_tick'], neuron_count=receipts['new']['neuron_count'],
                  edge_count=receipts['new']['edge_count'], common_frames_exact=len(oldframes),
                  extra_actual_snapshots=len(by_tick.keys() - oldticks), all_checkpoint_arrays_exact=checkpoint_keys,
                  ordered_events_exact=True, result_exact=True, progress_exact=progress['new'],
                  snapshots_observational=True, total_spikes=receipts['new']['total_spikes'],
                  events=read(b / 'events.json'), result=read(b / 'result.json'),
                  admission_verified=admit, timing_includes_observer_overhead=True,
                  frame_counts={name: len(read(output / name / 'frames.json')) for name in receipts},
                  measured={name: dict(wall_seconds=elapsed[name], receipt_timing=r['timing'],
                                      frames_bytes=(output / name / 'frames.json').stat().st_size,
                                      scene_bytes=(output / name / 'scene.json').stat().st_size,
                                      evidence_bytes=sum(p.stat().st_size for p in (output / name).iterdir()),
                                      file_sha256={p.name: file_sha(p) for p in (output / name).iterdir()})
                            for name, r in receipts.items()})
    write_json(output / 'comparison.json', result)
    return result


@pytest.fixture(scope='module')
def original():
    value = os.environ.get('FLY_REPLAY_ORIGINAL_ROOT')
    if not value:
        pytest.skip('Opt-in read-only original source and assets required for actual parity')
    return Path(value)


def test_full_retained_graph_pair(original):
    output = Path(os.environ['FLY_REPLAY_OUTPUT']) / 'fullgraph-1s'
    # Read existing artifacts only; no compilation or store creation in original var.
    artifact = next(p.parent.name for p in sorted((original / 'var/artifacts').glob('*/manifest.json'))
                    if json.loads(p.read_text())['report']['budget_used'] == 0)
    fly = dict(id='a' * 32, name='Read-only baseline', color='mint', artifact_id=artifact)
    # These scientific/physical dependencies must be unchanged for the matched reference.
    for name in ['body.py', 'neural.py', 'compiler.py', 'connectome.py', 'contracts.py', 'scenarios.py']:
        assert file_sha(original / 'src/flyarena' / name) == file_sha(Path(runner.__file__).parent / name)
    result = compare_pair(load_original(original), runner,
                          MatchRequest(fly_ids=[fly['id']], mode='forage', duration_seconds=1),
                          [fly], output, original / 'data', original / 'var',
                          scientific_limit='Actual 1s legacy-bridge solo retained-graph case; not phenotype or behavior qualification.')
    assert result['final_tick'] == 10000
    assert result['frame_counts'] == {'old': 21, 'new': 101}
    assert result['extra_actual_snapshots'] == 80


@pytest.mark.parametrize('case', ['intake-contact-partial', 'sumo-partial'])
def test_bounded_physical_edge_cases(original, case):
    output = Path(os.environ['FLY_REPLAY_OUTPUT']) / case
    data, var, artifact = tiny_assets(output / 'fixture')
    old = load_original(original)
    flies = [dict(id=c * 32, name='fixture ' + c, color='mint', artifact_id=artifact) for c in 'ab']
    request = MatchRequest(fly_ids=[f['id'] for f in flies], map_id='ring',
                           mode='sumo' if case == 'sumo-partial' else 'contest', duration_seconds=1)
    def fixture_scene(*args):
        scene = arena_scene(*args)
        scene['spawns'] = [[-1, 0, 0], [1, 0, float(np.pi)]]
        scene['food'][0]['position'] = [0, 0, .15]
        if case == 'sumo-partial':
            scene['ring_radius'] = .1
        return scene
    def bounded_range():
        capped = False
        def call(n):
            nonlocal capped
            if n == 100 and not capped:
                capped = True
                return range(6)
            return range(n)
        return call
    with pytest.MonkeyPatch.context() as patch:
        for module in [old, runner]:
            patch.setattr(module, 'arena_scene', fixture_scene)
            if case == 'intake-contact-partial':
                # Bound only the OUTER experiment duration to 600 ticks. Internal
                # neural/controller/physics/event steps and RNG are unmodified.
                patch.setattr(module, 'range', bounded_range(), raising=False)
        result = compare_pair(old, runner, request, flies, output, data, var, admit=False,
                              scientific_limit='Four-neuron LIF fixture, real dual MuJoCo; altered scene and bounded endpoint, not admissible research evidence.')
    assert result['result']['contact_ticks'] > 0
    assert any(e['type'] == 'contact' for e in result['events'])
    if case == 'intake-contact-partial':
        assert result['final_tick'] == 600
        assert sum(result['result']['scores']) > 0
        assert any(e['type'] == 'intake' and e['tick'] == 600 for e in result['events'])
        assert result['progress_exact'] == [.05]
    else:
        assert result['final_tick'] == 100
        assert result['result']['exit_ticks'] == [1, 1]
        assert result['frame_counts'] == {'old': 2, 'new': 2}
