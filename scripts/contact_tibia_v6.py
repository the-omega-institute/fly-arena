#!/usr/bin/env python3
"""Run the one fixed full-connectome contact candidate (8 x 0.6 s)."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import sys
import time

import numpy as np

from flyarena.backend import CPUBrainBackend
from flyarena.common import file_sha, write_json
from flyarena.connectome import Connectome
from flyarena.neural import Brain, PROFILE as LIF
from flyarena.experiments.contact_v6 import (
    LEGS, PROTOCOL, ContactTibiaBridge, bind_annotations,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = ["src/flyarena/experiments/contact_v6.py", "scripts/contact_tibia_v6.py",
                "scripts/verify_contact_tibia_v6.py", "src/flyarena/backend.py",
                "src/flyarena/neural.py", "src/flyarena/connectome.py",
                "src/flyarena/common.py", "src/flyarena/experiments/checkpoints.py"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    import flyarena.neural
    if Path(flyarena.neural.__file__).resolve() != ROOT / "src/flyarena/neural.py":
        raise RuntimeError("PYTHONPATH must resolve isolated source")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)  # Evidence never overwritten.
    start = time.monotonic()
    graph = Connectome(args.data, verify=True)
    groups, rows = bind_annotations(graph, args.data / "raw/body-annotations.feather")
    bridge = ContactTibiaBridge(CPUBrainBackend(Brain(graph)), groups)
    initial = bridge.checkpoint()
    selected = np.unique(np.concatenate(list(groups.values())))
    np.savez_compressed(out / "groups.npz", **groups, selected=selected)
    write_json(out / "annotations.json", rows)
    np.savez_compressed(out / "rest.npz", **initial)
    write_json(out / "protocol.json", PROTOCOL)
    for name in SOURCE_FILES:
        target = out / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    # Copy the inspected FlyGym API and native-unit declaration, no model stepping.
    import importlib.util
    flygym_root = Path(importlib.util.find_spec("flygym").origin).parent
    api_sources = ["simulation.py", "assets/model/neuromechfly/mujoco_globals.yaml"]
    for name in api_sources:
        target = out / "source/flygym" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(flygym_root / name, target)
    write_json(out / "registration.json", {
        "schema": "contact-registration/v6", "baseline_commit": "61a89f6cb94e4a6ff206f3fe1e3a147c535a44b2",
        "argv": sys.argv, "python": sys.executable, "python_version": sys.version,
        "platform": platform.platform(), "isolated_neural_source": flyarena.neural.__file__,
        "data": str(args.data.resolve()), "lif": LIF,
        "dependencies": {n: importlib.metadata.version(n) for n in ("numpy", "numba", "pyarrow", "flygym", "mujoco")},
        "neuron_count": graph.n, "edge_count": graph.e,
        "connectome_manifest_sha256": file_sha(graph.path / "manifest.json"),
        "graph_files": graph.manifest["files"],
        "raw_annotations_sha256": file_sha(args.data / "raw/body-annotations.feather"),
        "weights_array_sha256": __import__("hashlib").sha256(bridge.backend.brain.weights.tobytes()).hexdigest(),
        "source_files": {n: file_sha(ROOT / n) for n in SOURCE_FILES},
        "frozen_files": {str(p.relative_to(out)): file_sha(p) for p in sorted(out.rglob("*")) if p.is_file()},
        "group_counts": {k: len(v) for k, v in groups.items()},
        "intermediary_rule": "all vnc_intrinsic afferent successors intersect Ti MN predecessors; structural two-hop, not functional validation",
    })
    print(json.dumps({"registered": str(out), "neurons": graph.n, "edges": graph.e,
                      "group_counts": {k: len(v) for k, v in groups.items()}}), flush=True)
    times = {}
    for run in PROTOCOL["runs"]:
        run_start = time.monotonic()
        folder = out / run
        folder.mkdir()
        bridge.restore(initial)
        np.savez_compressed(folder / "checkpoint-0000.npz", **bridge.checkpoint())
        brain = bridge.backend.brain
        records = {"rates_hz": [brain.rates[selected].copy()],
                   "spike_counts": [np.zeros(len(selected), dtype=np.int32)],
                   "external_mv": [brain.external[selected].copy()],
                   "synaptic_current_mv": [brain.current[selected].copy()],
                   "motor_pools_hz": [np.zeros((6, 2))], "unclipped": [np.zeros(6)],
                   "commands_rad": [np.zeros(6)], "all_neuron_spikes": [0]}
        inputs, currents, held_before = [], [], []
        leg = "LF" if run == "LF-repeat" else run
        for sample in range(60):
            ratios = np.zeros(6)
            if leg != "blank" and 20 <= sample < 40:
                ratios[LEGS.index(leg)] = 1.0
            inputs.append(ratios)
            held_before.append(bridge.held_command.copy())
            currents.append(bridge.stimulate(ratios))
            counts = bridge.backend.advance(100)
            pools, raw, command = bridge.readout()
            for key, value in {
                "rates_hz": brain.rates[selected].copy(), "spike_counts": counts[selected],
                "external_mv": brain.external[selected].copy(),
                "synaptic_current_mv": brain.current[selected].copy(),
                "motor_pools_hz": pools, "unclipped": raw, "commands_rad": command,
                "all_neuron_spikes": int(counts.sum()),
            }.items():
                records[key].append(value)
            if brain.tick in (2000, 4000, 6000):
                np.savez_compressed(folder / f"checkpoint-{brain.tick:04d}.npz", **bridge.checkpoint())
        np.savez_compressed(folder / "samples.npz", **{k: np.asarray(v) for k, v in records.items()},
                            ticks=np.arange(61)*100, force_over_weight=np.asarray(inputs),
                            group_current_mv=np.asarray(currents), held_before_rad=np.asarray(held_before))
        times[run] = time.monotonic() - run_start
        print(json.dumps({"run": run, "wall_seconds": times[run], "total_spikes": brain.total_spikes,
                          "max_command_rad": float(np.max(np.abs(records["commands_rad"])))}), flush=True)
    write_json(out / "execution.json", {"runs_wall_seconds": times, "total_wall_seconds": time.monotonic()-start,
        "neural_runs_completed": 8, "body_qualification": "NOT RUN: awaiting independent neural gate",
        "design_panel": "NOT RUN", "no_retuning": True})
    write_json(out / "inventory.json", {str(p.relative_to(out)): file_sha(p)
               for p in sorted(out.rglob("*")) if p.is_file()})
    print(f"Completed fixed assay. Verify recorded evidence: {out}", flush=True)


if __name__ == "__main__":
    main()
