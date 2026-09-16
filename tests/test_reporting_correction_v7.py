"""Read-only regressions for the reporting scope and frozen evidence boundaries."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('reporting_v7', ROOT / 'scripts/summarize_embodied_v7.py')
reporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reporter)


@pytest.fixture(scope='module')
def report():
    return reporter.build_report()


def test_outputs_do_not_imply_neural_identity(report):
    pairs = report['paired_comparisons']
    assert len(pairs) == 12
    for pair in pairs.values():
        assert all(s['bitwise_equal'] for k, s in pair['sample_fields'].items() if k != 'external_mv')
        assert not pair['sample_fields']['external_mv']['bitwise_equal']
        for fields in pair['brain_checkpoints'].values():
            assert all(fields[k]['bitwise_equal'] for k in reporter.BRAIN_FIELDS if k not in ('v', 'external'))
            assert fields['v']['differing_neurons_outside_tactile_afferents'] == 0
            assert fields['external']['differing_neurons_outside_tactile_afferents'] == 0
        assert all(s['bitwise_equal'] for fields in pair['body_checkpoints'].values() for s in fields.values())
    # Independent direct subtraction of the checkpoint that exposes the old overclaim.
    base = ROOT / 'var/embodied-v7/contact'
    with np.load(base / 'WT-LM-42-neutral-intact/brain-5000.npz') as a, np.load(base / 'WT-LM-42-neutral-tactilezero/brain-5000.npz') as b:
        delta = np.abs(a['v'] - b['v'])
        assert np.count_nonzero(delta) == 378
        assert float(delta.max()) == 0.09369196868231455
        assert report['paired_checkpoint_difference_maxima']['v']['max_abs_difference_mv'] == float(delta.max())


def test_maxima_include_seed43_and_coordinate_records(report):
    base = ROOT / 'var/embodied-v7'
    # Recompute across independently enumerated record paths, without reporter helpers.
    with np.load(base / 'contact/groups.npz') as g:
        ids = set(np.concatenate([g[k] for k in g.files if k.startswith('afferent_')]).tolist())
        columns = [i for i, n in enumerate(g['selected']) if n in ids]
    peaks = {42: [], 43: []}
    force = []
    constraint = []
    geometry = json.loads((base / 'replay/geometry.json').read_text())
    with np.load(base / 'replay/blank-zero/body.npz') as a:
        neutral = a['qpos'][0]
    locked = [i for i in range(66) if i not in geometry['qpos_addresses']]
    paths = sorted((base / 'contact').glob('WT-*/samples.npz'))
    assert len(paths) == 49
    for p in paths:
        c = json.loads((p.parent / 'condition.json').read_text())
        with np.load(p) as a:
            peaks[c['seed']].append(float(a['external_mv'][:, columns].max()))
    physical = paths + list((base / 'replay').glob('*/body.npz'))
    assert len(physical) == 77
    for p in physical:
        with np.load(p) as a:
            force.append(float(np.max(np.abs(a['force']))))
            constraint.append(float(np.max(np.abs(a['qpos'][:, locked] - neutral[locked]))))
    tactile = report['tactile_scopes']
    assert tactile['seed42_intact_12']['max_tactile_external_mv']['value'] == max(peaks[42]) == 0.3725257161390243
    assert tactile['all_contact_49']['max_tactile_external_mv']['value'] == max(peaks[43]) == 2.7779656148103524
    assert tactile['seed43_intact_12']['max_tactile_external_mv']['tick'] == 100
    all_physical = report['physical_scopes']['all_physical_77']
    assert all_physical['max_recorded_actuator_force_native']['value'] == max(force) == 2.2871832808675805
    assert all_physical['max_nonTi_constraint_error_rad']['value'] == max(constraint) == 0.0021372277939230994
    assert report['physical_scopes']['contact_49']['max_recorded_actuator_force_native']['value'] == 0.22499999999999432
    assert report['physical_scopes']['contact_49']['max_nonTi_constraint_error_rad']['value'] == 1.7037258790486565e-05
    assert report['selected_afferent_spikes_all49'] == 0
    assert report['frozen_gates']['replay/gate.json']['transduction_pass'] is True
    assert report['frozen_gates']['contact/gate.json']['physical_causal_pass'] is False


def test_report_cannot_overwrite_primary_or_previous_report(tmp_path):
    base = tmp_path / 'primary'
    base.mkdir()
    sentinel = base / 'measurements.json'
    sentinel.write_text('frozen')
    for output in (base, base / 'nested'):
        with pytest.raises(ValueError, match='outside frozen'):
            reporter.write_report({}, output, base)
    alias = tmp_path / 'alias'
    alias.symlink_to(base, target_is_directory=True)
    with pytest.raises(ValueError, match='outside frozen'):
        reporter.write_report({}, alias, base)
    assert sentinel.read_text() == 'frozen'
    output = tmp_path / 'derived'
    reporter.write_report({'corrected': True}, output, base)
    with pytest.raises(FileExistsError):
        reporter.write_report({}, output, base)
    assert json.loads((output / 'measurements.json').read_text()) == {'corrected': True}


def test_bitwise_claim_distinguishes_signed_zero_and_rejects_nonfinite():
    result = reporter.compare_arrays(np.array([0.0]), np.array([-0.0]))
    assert result['differing_values'] == 0
    assert result['bitwise_equal'] is False
    with pytest.raises(ValueError, match='Nonfinite'):
        reporter.compare_arrays(np.array([np.nan]), np.array([np.nan]))
