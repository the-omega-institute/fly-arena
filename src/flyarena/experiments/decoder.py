"""Frozen baseline-trained nonlinear DN decoder. Runtime input is DN rate state only."""
from __future__ import annotations
import json
import time
from pathlib import Path
import numpy as np
from ..backend import CPUBrainBackend
from ..common import DATA, digest, file_sha, write_json
from ..connectome import Connectome
from ..neural import Brain, PROFILE
from .sensor import SENSOR, encode_odor

READOUT_ID = "descending-kernel-v2"

def training_identity():
    return {"model": PROFILE, "sensor": SENSOR, "decoder_source": file_sha(Path(__file__)),
            "backend_source": file_sha(Path(__file__).parents[1] / "backend.py"),
            "sensor_source": file_sha(Path(__file__).with_name("sensor.py"))}

def target(raw):
    common = float(np.mean(raw) / (np.mean(raw) + .3))
    turn = .85 * np.tanh(6 * (raw[0] - raw[1]) / (sum(raw) + .05))
    # Measured positive yaw is RIGHT action > LEFT action.
    return common * .85 * np.array([1 - turn, 1 + turn])

class Decoder:
    def __init__(self, path):
        with np.load(path, allow_pickle=False) as a:
            self.neurons = a["neurons"].copy()
            self.centers = a["centers"].copy()
            self.weights = a["weights"].copy()
            self.bandwidth = float(a["bandwidth"])
        self.norm = np.sum(self.centers**2, axis=1)

    def command(self, rates):
        x = np.asarray(rates, dtype=float) / 100
        d2 = np.maximum(0, self.norm + x @ x - 2 * self.centers @ x)
        kernel = np.exp(-d2 / (2 * self.bandwidth**2))
        # Neural silence gives zero motor authority; no sensor/coordinate input here.
        activity = min(1., float(np.linalg.norm(x)) / .02)
        return np.clip(kernel @ self.weights, 0, 1.5) * activity

def prepare(data: Path = DATA):
    folder = data / "connectome/research-v2"
    if folder.exists():
        raise FileExistsError("Versioned readout already exists; use a fresh data root to recalibrate")
    graph = Connectome(data, verify=True)
    backend = CPUBrainBackend(Brain(graph)); dn = graph.groups["descending"]
    started = time.perf_counter()
    xs, ys = [], []
    # Calibration grid and transient ordering are fixed; no task trajectories enter fitting.
    grid = [0., .04, .12, .3, .65, 1.2, 2.4]
    stimuli = [(l, r) for l in grid for r in grid]
    stimuli += [(c*(1+d), c*(1-d)) for c in [.04,.08,.15,.25,.4,.6,.9,1.4,2.2]
                for d in [-.7,-.3,-.12,-.06,0.,.06,.12,.3,.7]]
    for i, raw in enumerate(stimuli):
        backend.reset(1907)
        for t in range(35):
            backend.stimulate(*encode_odor(*raw)); backend.advance(100)
            if t >= 9 and t % 3 == 0:
                xs.append(backend.neural_output(dn) / 100); ys.append(target(raw))
        # Explicit decay training: output should subside after stimulus removal.
        for t in range(20):
            backend.stimulate(0., 0.); backend.advance(100)
            if t >= 9 and t % 3 == 0:
                xs.append(backend.neural_output(dn) / 100); ys.append(np.zeros(2))
        print(f"calibration {i+1}/{len(stimuli)}", flush=True)
    x, y = np.array(xs), np.array(ys)
    norms = np.sum(x*x, axis=1)
    d2 = np.maximum(0, norms[:,None] + norms[None,:] - 2*x@x.T)
    # Calibration-only grouped validation: reserve whole stimulus trajectories.
    # Final directional heldouts and embodied task trials never select parameters.
    groups = np.repeat(np.arange(len(stimuli)), 13)
    if len(groups) != len(x): raise RuntimeError("calibration grouping mismatch")
    held = groups % 7 == 3
    fit = ~held
    candidates = []
    for width in [.5, 1., 1.5, 2.5]:
        k = np.exp(-d2 / (2*width**2))
        for alpha in [.002, .02, .2]:
            w = np.linalg.solve(k[np.ix_(fit,fit)] + alpha*np.eye(fit.sum()), y[fit])
            prediction = k[np.ix_(held,fit)] @ w
            error = float(np.mean(abs(prediction-y[held])))
            candidates.append((error, width, alpha))
    _, bandwidth, alpha = min(candidates)
    kernel = np.exp(-d2 / (2*bandwidth**2))
    weights = np.linalg.solve(kernel + alpha*np.eye(len(x)), y)
    folder.mkdir(parents=True)
    np.savez(folder / "readout.npz", neurons=dn, centers=x, weights=weights, bandwidth=bandwidth)
    decoder = Decoder(folder / "readout.npz")
    validation = []
    heldouts = [(0.,0.),(.08,.08),(.5,.5),(1.7,1.7),(.15,.35),(.35,.15),(.7,.85),(.85,.7),(.1,1.8),(1.8,.1),(.4,.6),(.6,.4),(.38,.42),(.42,.38),(.52,.58),(.58,.52),(.24,.27),(.27,.24)]
    for raw in heldouts:
        backend.reset(8123); observed=[]
        for t in range(40):
            backend.stimulate(*encode_odor(*raw)); backend.advance(100)
            if t >= 20: observed.append(decoder.command(backend.neural_output(dn)))
        command = np.mean(observed, axis=0)
        validation.append({"odor": list(raw), "expected": target(raw).tolist(), "observed": command.tolist(),
                           "direction_correct": bool(raw[0] == raw[1] or (command[1]-command[0])*(raw[0]-raw[1]) > 0),
                           "mae": float(np.mean(abs(command-target(raw))))})
    directional = all(v["direction_correct"] for v in validation)
    blank = max(validation[0]["observed"]) < .02
    speed = np.mean(validation[1]["observed"]) < np.mean(validation[2]["observed"]) < np.mean(validation[3]["observed"])
    gates = {"heldout_direction": directional, "blank_stop": bool(blank), "concentration_speed": bool(speed),
             "neutral_bias": bool(max(abs(v["observed"][0]-v["observed"][1]) for v in validation if v["odor"][0]==v["odor"][1]) < .18),
             "heldout_mae": bool(np.mean([v["mae"] for v in validation]) < .18)}
    metadata = {"id": READOUT_ID, "connectome_sha256": graph.manifest["sha256"],
                "training_identity": training_identity(), "training_stimuli": stimuli,
                "calibration_seed": 1907, "validation_seed": 8123,
                "method": "Gaussian kernel ridge on all annotated DN rates; zero authority at neural silence; two bilateral actions",
                "bandwidth": bandwidth, "ridge_alpha": alpha, "calibration_cv": candidates, "validation": validation, "quality_gates": gates,
                "ready": all(gates.values()), "readout_sha256": file_sha(folder / "readout.npz"),
                "neuron_count": graph.n, "edge_count": graph.e, "dn_count": len(dn),
                "wall_seconds": time.perf_counter()-started,
                "limitation": "Engineered sensorimotor approximation; no biological validation or memory claim."}
    metadata["sha256"] = digest(metadata)
    write_json(folder / "readout.json", metadata)
    print(json.dumps(metadata, indent=2), flush=True)
    if not metadata["ready"]: raise RuntimeError("Calibration did not pass held-out gates")
    return metadata
