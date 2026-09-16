"""Post-run reporting correction from frozen arrays; never runs a simulation."""
from pathlib import Path
import argparse
import hashlib
import json

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'var/embodied-v7'
OUTPUT = ROOT / 'var/reporting-correction-v7'
LEGS = ('LF', 'LM', 'LH', 'RF', 'RM', 'RH')
SAMPLE_FIELDS = (
    'ticks', 'rates_hz', 'spike_counts', 'afferent_spikes', 'motor_spikes',
    'all_spikes', 'max_rate_hz', 'pools_hz', 'command_rad', 'knees', 'qpos',
    'velocity', 'force', 'work_native', 'probe_mm', 'contact_ratios',
    'contact_impulse_native', 'current_mv', 'external_mv',
)
BRAIN_FIELDS = ('v', 'external', 'rates', 'current', 'refractory', 'delay',
                'tick', 'total_spikes', 'held_command')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare_arrays(left, right):
    """Keep byte equality distinct from numerical equality (including signed zero)."""
    if left.shape != right.shape or left.dtype != right.dtype:
        raise ValueError('Compared arrays must have matching shape and dtype')
    if not np.isfinite(left).all() or not np.isfinite(right).all():
        raise ValueError('Nonfinite evidence')
    return {
        'shape': list(left.shape), 'dtype': str(left.dtype),
        'bitwise_equal': left.tobytes() == right.tobytes(),
        'differing_values': int(np.count_nonzero(left != right)),
        'max_abs_difference': float(np.max(np.abs(left - right))),
    }


def maximum(paths, field, transform, base):
    """Return the measured maximum and one deterministic witness, including tick."""
    result = None
    for path in sorted(paths):
        with np.load(path, allow_pickle=False) as arrays:
            values = transform(arrays[field])
            if not np.isfinite(values).all():
                raise ValueError(f'Nonfinite {field}: {path}')
            index = np.unravel_index(np.argmax(values), values.shape)
            value = float(values[index])
            if result is None or value > result['value']:
                result = {'value': value, 'record': str(path.relative_to(base)),
                          'tick': int(arrays['ticks'][index[0]]),
                          'array_index_after_selection': [int(i) for i in index]}
    if result is None:
        raise ValueError('Empty measurement scope')
    return result


def paired_report(base, leg, context, afferents):
    stem = f'WT-{leg}-42-{context}-'
    left = base / 'contact' / (stem + 'intact')
    right = base / 'contact' / (stem + 'tactilezero')
    with np.load(left / 'samples.npz') as a, np.load(right / 'samples.npz') as b:
        samples = {k: compare_arrays(a[k], b[k]) for k in SAMPLE_FIELDS}
    checkpoints = {}
    for tick in (2000, 5000, 10000):
        name = f'brain-{tick:04}.npz'
        with np.load(left / name) as a, np.load(right / name) as b:
            fields = {k: compare_arrays(a[k], b[k]) for k in BRAIN_FIELDS}
            # Locate differences without mistaking identical output for identical state.
            for k in ('v', 'external'):
                changed = np.flatnonzero(a[k] != b[k])
                fields[k]['differing_neurons_outside_tactile_afferents'] = int(
                    np.count_nonzero(~np.isin(changed, afferents)))
            checkpoints[str(tick)] = fields
    body = {}
    for tick in (0, 2000, 5000, 10000):
        name = f'body-{tick:04}.npz'
        with np.load(left / name) as a, np.load(right / name) as b:
            body[str(tick)] = {k: compare_arrays(a[k], b[k])
                               for k in ('integration', 'tick', 'command')}
    return {'intact_record': str(left.relative_to(base)),
            'tactilezero_record': str(right.relative_to(base)),
            'sample_fields': samples, 'brain_checkpoints': checkpoints,
            'body_checkpoints': body}


def build_report(base=BASE):
    base = Path(base)
    geometry = json.loads((base / 'replay/geometry.json').read_text())
    with np.load(base / 'replay/blank-zero/body.npz') as a:
        neutral = a['qpos'][0]
    other = np.setdiff1d(np.arange(len(neutral)), geometry['qpos_addresses'])
    with np.load(base / 'contact/groups.npz') as groups:
        afferents = np.unique(np.concatenate([groups['afferent_' + l] for l in LEGS]))
        selected = groups['selected']
        positions = np.searchsorted(selected, afferents)
        if not np.array_equal(selected[positions], afferents):
            raise ValueError('Afferents missing from selected columns')
    contact = sorted((base / 'contact').glob('*/samples.npz'))
    coordinate = sorted((base / 'replay').glob('coordinate-*/body.npz'))
    replay = sorted(p for p in (base / 'replay').glob('*/body.npz') if p not in coordinate)
    conditions = {p: json.loads((p.parent / 'condition.json').read_text()) for p in contact}
    seed42 = [p for p in contact if conditions[p]['seed'] == 42
              and conditions[p]['control'] == 'intact' and 'repeat' not in p.parent.name]
    seed43 = [p for p in contact if conditions[p]['seed'] == 43]
    if (len(contact), len(coordinate), len(replay), len(seed42), len(seed43)) != (49, 12, 16, 12, 12):
        raise ValueError('Unexpected frozen v7 panel coverage')
    physical_scopes = {}
    for label, paths in [('coordinate_12', coordinate), ('recorded_neural_replay_16', replay),
                         ('contact_49', contact), ('all_physical_77', coordinate + replay + contact)]:
        physical_scopes[label] = {
            'records': len(paths),
            'max_recorded_actuator_force_native': maximum(paths, 'force', np.abs, base),
            'max_nonTi_constraint_error_rad': maximum(
                paths, 'qpos', lambda q: np.abs(q[:, other] - neutral[other]), base),
        }
    tactile_scopes = {}
    for label, paths in [('seed42_intact_12', seed42), ('seed43_intact_12', seed43), ('all_contact_49', contact)]:
        tactile_scopes[label] = {
            'records': len(paths),
            'max_tactile_external_mv': maximum(paths, 'external_mv', lambda x: x[:, positions], base),
            'max_contact_over_weight': maximum(paths, 'contact_ratios', lambda x: x, base),
        }
    pairs = {f'{leg}-{context}': paired_report(base, leg, context, afferents)
             for leg in LEGS for context in ('off', 'neutral')}
    differences = {}
    for field in ('v', 'external'):
        value, pair, tick = max(
            (fields[field]['max_abs_difference'], pair, tick)
            for pair, record in pairs.items()
            for tick, fields in record['brain_checkpoints'].items())
        differences[field] = {'max_abs_difference_mv': value, 'pair': pair,
                              'tick': int(tick), 'scope': '36 matched saved checkpoint pairs'}
    affspikes = 0
    legs = {}
    for p in contact:
        with np.load(p) as a:
            affspikes += int(a['afferent_spikes'].sum())
            if p in seed42:
                c = conditions[p]; i = LEGS.index(c['leg'])
                legs[f"{c['leg']}-{c['context']}"] = {
                    'scope': 'seed42 intact own leg; 10ms samples',
                    'own_peak_contact_over_weight': float(a['contact_ratios'][:, i].max()),
                    'own_total_afferent_spikes': int(a['afferent_spikes'][:, i].sum()),
                    'own_total_MN_spikes': int(a['motor_spikes'][:, i].sum()),
                    'whole_graph_spikes': int(a['all_spikes'].sum()),
                    'own_contact_impulse_native_sampled': float(a['contact_impulse_native'][-1, i] * geometry['body_weight_native']),
                    'own_final_actuator_work_native': float(a['work_native'][-1, i]),
                }
    inventory = json.loads((base / 'inventory.json').read_text())
    for name, digest in inventory.items():
        if sha(base / name) != digest:
            raise ValueError(f'Frozen inventory mismatch: {name}')
    manifest = json.loads((base / 'delivery-manifest.json').read_text())
    # Reporter/docs are explicitly post-run corrections. Scientific files retain
    # the old digests; old source snapshots and old manifests are never rewritten.
    mutable = {'scripts/summarize_embodied_v7.py', 'docs/CONTACT_EMBODIMENT_V7.md'}
    for name, digest in manifest['source_files'].items():
        if name not in mutable and sha(ROOT / name) != digest:
            raise ValueError(f'Frozen delivery source mismatch: {name}')
    for registration in ('replay/registration.json', 'contact/registration.json'):
        for name, digest in json.loads((base / registration).read_text())['source_hashes'].items():
            if sha(name) != digest:
                raise ValueError(f'Registered scientific source mismatch: {name}')
    report = {
        'schema': 'reporting-correction-v7/1',
        'status': 'post-run derived reporting correction; original measurements retained',
        'scientific_verdict': 'partial',
        'frozen_gates': {name: json.loads((base / name).read_text()) for name in ('replay/gate.json', 'contact/gate.json')},
        'dependent_ABC_and_walking': 'NOT RUN; contact causality failed',
        'browser_visual_QA': 'unavailable under existing authentication; unchanged',
        'counts': {'physical_records': 77, 'contact_scientific_trials': 48, 'contact_integrity_replays': 1},
        'measurement_scope': {
            'force': 'Six recorded named Ti position actuators across each stated record set; not a claim about all 42 model actuators.',
            'constraint': 'All 60 non-Ti qpos relative to frozen neutral; maximum at recorded frames only.',
            'sampling': 'Coordinate/replay .1ms; contact 10ms. Contact frame tick100 stores initial-contact input sampled at tick0.',
            'tactile': f'{len(afferents)} afferent columns of external_mv, located by groups.npz; not inferred from own-contact ratio.',
            'paired': '12 seed42 intact/tactilezero pairs; selected spike/rate samples, output fields and explicitly enumerated checkpoints only. No seed43 clamp pairs or full neural trajectory identity claim.',
            'checkpoints': 'All 165122 neurons at ticks2000/5000/10000; voltage extrema are sampled checkpoint differences, not continuous-time maxima.',
        },
        'physical_scopes': physical_scopes, 'tactile_scopes': tactile_scopes,
        'max_individual_neural_rate_hz_all49': maximum(contact, 'max_rate_hz', lambda x: x, base),
        'selected_afferent_spikes_all49': affspikes,
        'body_weight_native': geometry['body_weight_native'],
        'seed42_intact_own_leg_statistics': legs, 'paired_comparisons': pairs,
        'paired_checkpoint_difference_maxima': differences,
        'provenance': {
            'primary_evidence': str(base.resolve()),
            'original_inventory_sha256': sha(base / 'inventory.json'),
            'original_inventory_verified_files': len(inventory),
            'original_measurements_sha256': sha(base / 'measurements.json'),
            'original_attribution_sha256': sha(base / 'attribution.json'),
            'original_delivery_manifest_sha256': sha(base / 'delivery-manifest.json'),
            'original_reporter_snapshot_sha256': sha(base / 'source/scripts/summarize_embodied_v7.py'),
            'original_delivery_source_hashes': manifest['source_files'],
            'post_run_current_source_hashes': {n: sha(ROOT / n) for n in sorted(mutable | {'tests/test_reporting_correction_v7.py'})},
            'registered_scientific_source_hashes_verified': True,
        },
    }
    return report


def write_report(report, output=OUTPUT, base=BASE):
    output = Path(output).resolve()
    if output == Path(base).resolve() or Path(base).resolve() in output.parents:
        raise ValueError('Corrected output must be outside frozen primary evidence')
    output.mkdir(parents=True, exist_ok=True)
    target = output / 'measurements.json'
    with target.open('x') as stream:
        stream.write(json.dumps(report, indent=2, allow_nan=False) + '\n')
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    path = write_report(build_report(), args.output)
    print(json.dumps({'corrected_report': str(path), 'sha256': sha(path)}))


if __name__ == '__main__':
    main()
