#!/usr/bin/env python3
"""Verify final immutable motor evidence and emit concise scientific results."""
import json
from pathlib import Path
import numpy as np
from flyarena.common import ROOT, digest, file_sha, write_json
from flyarena.experiments.probes import profile_manifest, verify_evidence
from flyarena.experiments.qualification import verify_qualification
from flyarena.judge import verify


def read(path):
    return json.loads(path.read_text())


def main():
    parent = ROOT/'var/research-validation/qualification-v4'
    root = parent/'final'
    profile = profile_manifest()
    q = verify_qualification(root/'qualification.json', profile)
    source = read(root/'source-snapshot.json')
    current = {str(p.relative_to(ROOT)):file_sha(p) for p in sorted((ROOT/'src/flyarena').rglob('*.py'))}
    assert current == source, 'Full scientific source changed after cohort began'
    before = read(parent/'preservation-before.json')
    assert all(file_sha(ROOT/p)==sha for p,sha in before.items()), 'Historical/frozen evidence changed'
    frozen = read(ROOT/'var/research-validation/policy-v3-frozen.json')
    assert all(file_sha(ROOT/p)==sha for p,sha in frozen['hashes'].items()), 'Policy freeze changed'
    rows = {}
    for name in ['heldout-left','heldout-right','bifurcation-left','bifurcation-right']:
        report = read(root/name/'report.json'); verify_evidence(root/name, report)
        xy = np.array([[p['x'],p['y']] for p in report['trajectory']])
        distance = np.linalg.norm(xy-np.array(report['scene']['food'][0]['position'][:2]),axis=1)
        rows[name] = {'seed':report['seed'], 'food_intake':report['metrics']['food_intake'],
            'closest_distance_mm':float(distance.min()), 'final_distance_mm':float(distance[-1]),
            'seconds_thorax_within_1_8mm':float(np.sum(distance[1:]<1.8)*.01),
            'correct_branch':report['metrics']['correct_branch'],
            'minimum_upright':min(p['upright_z'] for p in report['neural_trace'])}
    experiment = read(root/'experiment.json')
    assert experiment['status']=='complete'
    assert len({r['condition_key'] for r in experiment['reports']})==1
    subjects = {}
    for subject, report in zip(experiment['subjects'],experiment['reports']):
        folder = root/'state/research/runs'/experiment['id']/'1'/str(report['seed'])/subject['role']
        verify_evidence(folder,report)
        subjects[subject['role']] = {'fly_id':subject['fly_id'], 'food_intake':report['metrics']['food_intake'],
            'receipt_sha256':report['receipt_sha256']}
    arenas = read(root/'arena.json')
    for entry in arenas.values():
        match = entry['match']
        assert verify(Path(entry['folder']),expected_request=match['request'],expected_artifacts=match['artifacts'],
                      expected_runtime_hash=match['runtime_hash'])['status']=='verified'
    passed = all(q['checks'].values())
    admission = 'HTTP admitted and replay verified' if passed else 'HTTP 422; solo/dual are internal diagnostics only'
    if not passed:
        assert read(root/'admission.json')['rejected_status']==422
        assert all('not API admitted' in v['match']['admission'] for v in arenas.values())
    result = {'passed':passed,'passed_gates':sum(q['checks'].values()),'total_gates':len(q['checks']),
        'failed_gates':[k for k,v in q['checks'].items() if not v], 'physical_trials':rows,
        'experiment_id':experiment['id'],'subjects':subjects,'arena_admission':admission,
        'profile_sha256':digest(profile),'qualification_sha256':q['sha256'],
        'full_source_files_verified':len(source),'historical_and_frozen_files_verified':len(before),
        'policy_freeze_verified':True, 'final_cohort_runs':1,
        'interpretation':'Small engineering cohort only. Intake does not establish retention or biological validity; internal arena diagnostics do not establish public admission.'}
    write_json(root/'acceptance.json', result)
    selection = read(parent/'candidate-selection.json')
    lines = ['# Neural-only v4 motor corrective result', '',
        f"Verdict: **{'implemented' if passed else 'partial'}**. {sum(q['checks'].values())}/{len(q['checks'])} unchanged gates passed.", '',
        'The frozen v2 decoder still supplies exactly two neural outputs. The v4 motor applies smooth high-drive slowing between common decoded magnitudes 0.54 and 0.64, retaining 40% propulsion at the upper threshold. No food, pose, sensory channel or reward enters the motor. Sensor, decoder, body, task geometry, 1.1 mm mouth radius and scientific acceptance thresholds are unchanged.', '',
        f"Selected development candidate: **{selection['selected']}**. {selection['reason']}", '',
        'Development used only seeds 42/43, four ten-second trials for each of two bounded candidates. Both pilot evidence trees and motor sources are preserved. The root policy freeze was verified before the untouched 20042–20045 cohort ran exactly once through scripts/qualify_integration_v2.py. No scientific source changed after that cohort began.', '',
        '| Trial | Seed | Intake | Closest thorax distance (mm) | Final distance (mm) | Time within 1.8 mm (s) |',
        '|---|---:|---:|---:|---:|---:|']
    for name,row in rows.items():
        lines.append(f"| {name} | {row['seed']} | {row['food_intake']:.2f} | {row['closest_distance_mm']:.3f} | {row['final_distance_mm']:.3f} | {row['seconds_thorax_within_1_8mm']:.2f} |")
    lines += ['', 'Failed gates: '+(', '.join(result['failed_gates']) or 'none')+'.', '',
        f"Real in-process HTTP experiment `{experiment['id']}` completed one WT/official/design triplet under a shared condition. Intake: "+', '.join(f"{k} {v['food_intake']:.2f}" for k,v in subjects.items())+'. These differences do not establish design superiority.', '',
        'Arena status: **'+admission+'**. No listener, service, deployment or live authentication activation was used.', '',
        f"Verified {len(source)} final scientific source files, {len(before)} historical/frozen files, the policy freeze and all final probe/experiment/arena receipts. Full graph: 165,122 neurons and 25,563,197 structural edges; actual backend cpu-numba.", '',
        f"Scientific profile SHA-256: `{digest(profile)}`.", '',
        'Evidence: `var/research-validation/qualification-v4/final/acceptance.json`, `qualification.json`, `experiment.json`, `arena.json`, `motor-approach.png`, `heldout-trajectories.png`, `experiment-trajectories.png`; bounded pilot summaries/plots are under sibling `pilot-a` and `pilot-b`.', '',
        'Reliable food approach and retention remain unproven wherever the recorded trajectories or gates fail. CUDA, biological validity, learning and memory remain unqualified. Historical v3 failed evidence and both frozen readouts were preserved.', '']
    (ROOT/'docs/SCIENCE_MOTOR_V4.md').write_text('\n'.join(lines))
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
