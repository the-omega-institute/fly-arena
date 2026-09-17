#!/usr/bin/env python3
"""Bounded motor development: only seeds 42/43, unchanged physical probes."""
import argparse
import json
from pathlib import Path
import numpy as np
from flyarena.common import ROOT, digest, file_sha, write_json
from flyarena.compiler import Compiler
from flyarena.connectome import Connectome
from flyarena.contracts import FlySpec
from flyarena.experiments.motor import MOTOR
from flyarena.experiments.probes import run_probe, verify_evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', choices=['a', 'b'], required=True)
    args = parser.parse_args()
    root = ROOT/'var/research-validation/qualification-v4'/('pilot-'+args.candidate)
    root.mkdir(parents=True, exist_ok=False)
    write_json(root/'motor.json', MOTOR)
    (root/'motor-source.py.txt').write_text((ROOT/'src/flyarena/experiments/motor.py').read_text())
    compiler = Compiler(Connectome(verify=True))
    artifact = compiler.compile(FlySpec(name='Motor development baseline',
        connectome_sha256=compiler.graph.manifest['sha256']), publish=True, root=root/'state')
    fly = {'id':'1'*32, 'artifact_id':artifact['artifact_id'], 'name':'Baseline', 'reference_kind':'wildtype'}
    rows = {}
    for probe in ['gradient-v2', 'bifurcation-v2']:
        for seed in [42, 43]:
            name = f'{probe}-{seed}'
            print('PILOT START', args.candidate, name, flush=True)
            report = run_probe(fly, probe, seed, 10, root/name, var=root/'state')
            verify_evidence(root/name, report)
            position = np.array([[p['x'],p['y']] for p in report['trajectory']])
            distance = np.linalg.norm(position-np.array(report['scene']['food'][0]['position'][:2]), axis=1)
            yaw = np.unwrap([p['yaw'] for p in report['trajectory']])
            rows[name] = {'metrics':report['metrics'], 'closest_distance_mm':float(distance.min()),
                'seconds_with_thorax_within_1_8mm':float(np.sum(distance[1:]<1.8)*.01),
                'yaw_at_half_second':float(yaw[50]-yaw[0]),
                'minimum_upright':min(p['upright_z'] for p in report['neural_trace']),
                'receipt_sha256':report['receipt_sha256']}
            write_json(root/'summary.json', {'candidate':args.candidate,'motor':MOTOR,'trials':rows,
                'script_sha256':file_sha(Path(__file__)), 'motor_sha256':digest(MOTOR)})
            print('PILOT DONE', name, json.dumps(rows[name]), flush=True)


if __name__ == '__main__':
    main()
