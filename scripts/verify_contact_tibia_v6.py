#!/usr/bin/env python3
"""Independent evidence verifier: does not import the candidate or its decoder."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pyarrow.feather as feather

LEGS = ("LF", "LM", "LH", "RF", "RM", "RH")
RUNS = ("blank", *LEGS, "LF-repeat")


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8*1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def arrays(path):
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def max_streak(mask):
    best = current = 0
    for value in mask:
        current = current + 1 if value else 0
        best = max(best, current)
    return best


def evaluate(commands, raw, repeat_exact):
    """Fixed gates on own-leg blank-subtracted response; no fitting."""
    channels = {}
    for i, leg in enumerate(LEGS):
        delta = np.abs(commands[leg][:, i] - commands["blank"][:, i])
        peak = float(delta[21:41].max())
        streak = max_streak(delta[21:41] > .001)
        final = float(delta[60])
        channels[leg] = {"pulse_peak_increment_rad": peak, "consecutive_samples_gt_0_001": streak,
                         "final_increment_rad": final,
                         "final_to_pulse_peak": final / peak if peak else None,
                         "magnitude_pass": streak >= 5,
                         "decay_pass": peak > 0 and final <= .2*peak,
                         "pass": streak >= 5 and peak > 0 and final <= .2*peak}
    saturation = {run: int(np.count_nonzero(np.abs(raw[run]) >= 1)) for run in RUNS}
    bilateral = any(channels[l]["pass"] for l in LEGS[:3]) and any(channels[l]["pass"] for l in LEGS[3:])
    forelegs = channels["LF"]["pass"] and channels["RF"]["pass"]
    passed = bilateral and forelegs and repeat_exact and not any(saturation.values())
    return {"channels": channels, "saturated_channel_samples": saturation,
            "bilateral_channel_pass": bilateral, "both_forelegs_pass": forelegs,
            "repeat_exact": repeat_exact, "neural_prerequisite_pass": passed,
            "decision": "ELIGIBLE_FOR_SEPARATELY_FROZEN_BODY_STAGE" if passed else "STOP_CANDIDATE",
            "body_qualification": "NOT RUN", "design_panel": "NOT RUN"}


def verify(out: Path, data: Path):
    inventory = json.loads((out / "inventory.json").read_text())
    for name, expected in inventory.items():
        require(not Path(name).is_absolute() and ".." not in Path(name).parts, "Unsafe inventory path")
        require(sha(out / name) == expected, f"Evidence hash mismatch: {name}")
    reg = json.loads((out / "registration.json").read_text())
    for name, expected in reg["frozen_files"].items():
        require(sha(out / name) == expected, f"Registration mismatch: {name}")
    for name, expected in reg["source_files"].items():
        require(sha(out / "source" / name) == expected, f"Source snapshot mismatch: {name}")
    require(sha(out / "source/scripts/verify_contact_tibia_v6.py") == sha(Path(__file__)), "Verifier changed after registration")
    require(sha(data / "connectome/manifest.json") == reg["connectome_manifest_sha256"], "Graph manifest mismatch")
    for name, expected in reg["graph_files"].items():
        require(sha(data / "connectome" / name) == expected, f"Graph hash mismatch: {name}")
    require(sha(data / "raw/body-annotations.feather") == reg["raw_annotations_sha256"], "Annotations hash mismatch")
    protocol = json.loads((out / "protocol.json").read_text())
    require(protocol["runs"] == list(RUNS) and protocol["sample_steps"] == 100 and protocol["samples"] == 60
            and protocol["pulse_start_tick"] == 2000 and protocol["pulse_end_tick"] == 4000
            and protocol["end_tick"] == 6000 and protocol["pulse_force_over_weight"] == 1, "Wrong assay schedule")
    ids = np.load(data / "connectome/ids.npy", mmap_mode="r")
    n = len(ids)
    require(n == reg["neuron_count"], "Neuron count mismatch")
    groups = arrays(out / "groups.npz")
    selected = groups.pop("selected")
    rows = {r["bodyId"]: r for r in feather.read_table(data / "raw/body-annotations.feather").to_pylist() if r["status"] == "Traced"}
    require(set(rows) == set(map(int, ids)), "Retained raw neuron mismatch")
    aligned = [rows[int(i)] for i in ids]
    for leg in LEGS:
        side, part = leg
        nerve = dict(F="ProLN", M="MesoLN", H="MetaLN")[part]
        neuromere = dict(F="T1", M="T2", H="T3")[part]
        expected = [i for i, r in enumerate(aligned) if r["class"] == "mechanosensory_tactile" and r["rootSide"] == side and r["entryNerve"] == nerve]
        require(np.array_equal(groups[f"afferent_{leg}"], expected), f"Wrong afferents: {leg}")
        for a in ("flexor", "extensor"):
            expected = [i for i, r in enumerate(aligned) if r["superclass"] == "vnc_motor" and r["type"] == f"Ti {a} MN"
                        and r["somaSide"] == side and r["somaNeuromere"] == neuromere and r["exitNerve"] == nerve]
            require(np.array_equal(groups[f"{a}_{leg}"], expected) and len(expected) > 0, f"Wrong MNs: {a} {leg}")
    expected_dn = [i for i, r in enumerate(aligned) if r["superclass"] == "descending_neuron"]
    require(np.array_equal(groups["descending"], expected_dn), "Wrong DN observers")
    pre = np.load(data / "connectome/pre.npy", mmap_mode="r")
    post = np.load(data / "connectome/post.npy", mmap_mode="r")
    indptr = np.load(data / "connectome/indptr.npy", mmap_mode="r")
    signs = np.load(data / "connectome/signs.npy", mmap_mode="r")
    weights = np.load(data / "connectome/counts.npy", mmap_mode="r").astype(np.float32)*signs[pre]*np.float32(.275)
    require(hashlib.sha256(weights.tobytes()).hexdigest() == reg["weights_array_sha256"], "Weights differ from canonical baseline")
    aff = np.concatenate([groups[f"afferent_{l}"] for l in LEGS])
    mn = np.concatenate([groups[f"{a}_{l}"] for l in LEGS for a in ("flexor", "extensor")])
    successors = set(map(int, np.concatenate([post[indptr[i]:indptr[i+1]] for i in aff])))
    predecessors = set(map(int, pre[np.isin(post, mn)]))
    expected_mid = sorted(i for i in successors & predecessors if aligned[i]["superclass"] == "vnc_intrinsic")
    require(np.array_equal(groups["intermediary"], expected_mid), "Wrong intermediary observers")
    require(np.array_equal(selected, np.unique(np.concatenate(list(groups.values())))), "Observer union mismatch")
    recorded_rows = json.loads((out / "annotations.json").read_text())
    require(len(recorded_rows) == len(selected), "Observer metadata length mismatch")
    for i, row in zip(selected, recorded_rows):
        require(row["graph_index"] == i and all(rows[int(ids[i])].get(k) == v for k, v in row.items() if k != "graph_index"), "Observer metadata differs from raw")
    slots = {k: np.searchsorted(selected, v) for k, v in groups.items()}
    samples = {run: arrays(out / run / "samples.npz") for run in RUNS}
    rest = arrays(out / "rest.npz")
    expected_fields = {"v", "current", "refractory", "delay", "external", "rates", "tick", "total_spikes", "held_command"}
    require(set(rest) == expected_fields, "Incomplete rest state")
    for k, v in rest.items():
        require(np.all(v == (-52 if k == "v" else 0)), f"Not complete rest: {k}")
    checkpoints = {}
    observations = {}
    for run, s in samples.items():
        require(np.array_equal(s["ticks"], np.arange(61)*100), f"Wrong sampling ticks: {run}")
        require(all(np.isfinite(v).all() for v in s.values()), f"Nonfinite samples: {run}")
        require(s["rates_hz"].shape == s["spike_counts"].shape == (61, len(selected)), "Observer shape mismatch")
        counts = s["spike_counts"]
        require(counts.dtype == np.int32 and np.all((counts >= 0) & (counts <= 5)), "Invalid spike counts")
        require(np.all(s["rates_hz"] >= 0), "Negative rates")
        # Independently bound 50ms exponential rates from every 10ms spike bin.
        gain = (1-np.exp(-.1/50))*10000
        added = s["rates_hz"][1:] - s["rates_hz"][:-1]*np.exp(-10/50)
        require(np.all(added >= counts[1:]*gain*np.exp(-9.9/50)-1e-9)
                and np.all(added <= counts[1:]*gain+1e-9), "Rates inconsistent with spike counts")
        ratios = np.zeros((60, 6))
        if run != "blank":
            ratios[20:40, LEGS.index("LF" if run == "LF-repeat" else run)] = 1
        require(np.array_equal(s["force_over_weight"], ratios), "Wrong fixed force pulse")
        require(np.array_equal(s["group_current_mv"], 48*ratios), "Wrong encoder currents")
        ext = np.zeros((61, len(selected)))
        for i, leg in enumerate(LEGS):
            ext[1:, slots[f"afferent_{leg}"]] = (48*ratios[:, i])[:, None]
        require(np.array_equal(s["external_mv"], ext), "Wrong external current observer trace")
        pools = np.stack([np.stack([s["rates_hz"][:, slots[f"{a}_{leg}"]].mean(axis=1)
                         for a in ("flexor", "extensor")], axis=1) for leg in LEGS], axis=1)
        raw = (pools[:, :, 0]-pools[:, :, 1])/100
        command = .1*np.clip(raw, -1, 1)
        require(np.allclose(pools, s["motor_pools_hz"], rtol=0, atol=1e-12)
                and np.allclose(raw, s["unclipped"], rtol=0, atol=1e-14)
                and np.allclose(command, s["commands_rad"], rtol=0, atol=1e-15), "Neural-only command recomputation failed")
        require(np.array_equal(s["held_before_rad"], s["commands_rad"][:-1]), "Command hold timing mismatch")
        checkpoints[run] = {}
        for tick in (0, 2000, 4000, 6000):
            cp = arrays(out / run / f"checkpoint-{tick:04d}.npz")
            checkpoints[run][tick] = cp
            require(set(cp) == expected_fields and all(np.isfinite(v).all() for v in cp.values()), "Checkpoint fields/finite mismatch")
            for k in ("v", "current", "external", "rates", "refractory"):
                require(cp[k].shape == (n,) and cp[k].dtype == (np.int32 if k == "refractory" else np.float64), "Checkpoint shape/dtype mismatch")
            require(cp["delay"].shape == (19, n) and cp["delay"].dtype == np.float64, "Missing delay ring")
            require(cp["held_command"].shape == (6,) and cp["tick"].shape == cp["total_spikes"].shape == (), "Checkpoint hold/clock shape")
            require(np.all((cp["refractory"] >= 0) & (cp["refractory"] <= 22)) and np.all(cp["rates"] >= 0), "Checkpoint state bounds")
            j = tick//100
            require(int(cp["tick"]) == tick and int(cp["total_spikes"]) == int(s["all_neuron_spikes"][:j+1].sum()), "Checkpoint clock/spike total mismatch")
            for k, record in (("rates", "rates_hz"), ("external", "external_mv"), ("current", "synaptic_current_mv")):
                require(np.array_equal(cp[k][selected], s[record][j]), "Checkpoint/sample mismatch")
            require(np.array_equal(cp["held_command"], s["commands_rad"][j]), "Checkpoint command mismatch")
            unselected = np.ones(n, dtype=bool)
            unselected[selected] = False
            require(np.all(cp["external"][unselected] == 0), "Unregistered external currents")
            if tick == 0:
                require(all(np.array_equal(cp[k], rest[k]) for k in rest), "Different initial causal state")
        observations[run] = {
            "all_neuron_spikes": int(s["all_neuron_spikes"].sum()),
            "max_abs_command_rad": float(np.abs(command).max()),
            "groups": {k: {"spikes": int(counts[:, idx].sum()),
                            "peak_mean_rate_hz": float(s["rates_hz"][:, idx].mean(axis=1).max()) if len(idx) else 0,
                            "final_mean_rate_hz": float(s["rates_hz"][-1, idx].mean()) if len(idx) else 0}
                       for k, idx in slots.items()}}
    require(observations["blank"]["all_neuron_spikes"] == 0, "Blank rest unexpectedly spiking")
    repeat = all(np.array_equal(samples["LF"][k], samples["LF-repeat"][k]) for k in samples["LF"])
    repeat &= all(np.array_equal(checkpoints["LF"][t][k], checkpoints["LF-repeat"][t][k])
                  for t in checkpoints["LF"] for k in expected_fields)
    report = evaluate({r: s["commands_rad"] for r, s in samples.items()},
                      {r: s["unclipped"] for r, s in samples.items()}, bool(repeat))
    report.update(schema="contact-independent-verification/v6", inventory_sha256=sha(out / "inventory.json"),
                  registration_sha256=sha(out / "registration.json"), verifier_sha256=sha(Path(__file__)),
                  evidence_integrity_pass=True, neuron_count=n, edge_count=len(post),
                  selected_neurons=len(selected), observations=observations,
                  verification_scope="Independent source/data hashes, raw selectors, spike/rate bounds, checkpoint/trace correspondence, neural-only commands, fixed gates and exact repeat; no extra neural run or physical trial")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.output, args.data)
    target = args.output / "verification.json"
    with target.open("x") as f:
        json.dump(report, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    print(json.dumps({k: v for k, v in report.items() if k != "observations"}, indent=2))


if __name__ == "__main__":
    main()
