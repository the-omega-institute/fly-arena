"""Calibrate a shared, frozen descending-neuron motor readout.

This is an engineering bridge, not a claim about native fly motor decoding.
Training uses only controlled odor stimuli and the baseline graph, never match
positions, food coordinates, player mutations, or evaluation outcomes.
"""
from __future__ import annotations

import time
import numpy as np

from .common import DATA, digest, file_sha, write_json
from .connectome import Connectome
from .neural import Brain, PROFILE


def target(left: float, right: float) -> np.ndarray:
    turn = .65 * (right - left) / (left + right + .15)
    return np.array([.85 + turn, .85 - turn])


def calibrate():
    graph = Connectome()
    brain = Brain(graph)
    dn = graph.groups["descending"]
    xs, ys = [], []
    stimuli = [(l, r) for l in [0., .1, .3, .6, 1.] for r in [0., .1, .3, .6, 1.]]
    start = time.perf_counter()
    for index, (l, r) in enumerate(stimuli):
        brain.reset()
        brain.stimulate(l, r)
        for t in range(40):
            brain.advance(100)
            if t >= 20 and t % 2 == 0:
                xs.append(brain.rates[dn].copy() / 100)
                ys.append(target(l, r))
        print(f"Readout calibration {index+1}/{len(stimuli)}", flush=True)
    x, y = np.array(xs), np.array(ys)
    # Ridge regression, zero intercept: absent neural output means no locomotion.
    alpha = .3
    weights = x.T @ np.linalg.solve(x @ x.T + alpha * np.eye(len(x)), y)
    rng = np.random.default_rng(73041)
    validation = []
    for l, r in rng.uniform(.02, .95, (8, 2)):
        brain.reset()
        brain.stimulate(float(l), float(r))
        readings = []
        for t in range(40):
            brain.advance(100)
            if t >= 20:
                readings.append(brain.rates[dn] / 100 @ weights)
        observed = np.mean(readings, axis=0)
        expected = target(l, r)
        validation.append({"odor": [float(l), float(r)], "expected": expected.tolist(),
                           "observed": observed.tolist(), "mae": float(np.mean(np.abs(observed - expected)))})
    path = DATA / "connectome" / "readout.npz"
    np.savez(path, neurons=dn, weights=weights)
    manifest = {"id": "descending-ridge-v1", "connectome_sha256": graph.manifest["sha256"],
                "neural_profile_sha256": digest(PROFILE), "readout_sha256": file_sha(path),
                "method": "ridge, no intercept, all annotated descending neurons; rates / 100 Hz",
                "training_stimuli": stimuli, "ridge_alpha": alpha,
                "training_mae": float(np.mean(np.abs(x @ weights - y))), "validation": validation,
                "validation_mae": float(np.mean([v["mae"] for v in validation])),
                "wall_seconds": time.perf_counter() - start,
                "limitation": "Engineered shared decoder. No claim of biological motor equivalence or task success."}
    manifest["sha256"] = digest(manifest)
    write_json(DATA / "connectome" / "readout.json", manifest)
    print(manifest, flush=True)


if __name__ == "__main__":
    calibrate()
