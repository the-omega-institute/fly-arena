"""Reproducible plot for the separately versioned v12 correction analysis."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
import numpy as np

from flyarena.common import file_sha, write_json


PROFILE = "source-native-excursion-v12"
CASES = ("straight-008", "straight-02", "straight-04")
LEGS = ("LF", "LM", "LH", "RF", "RM", "RH")


def produce(analysis_root: Path, output: Path, receipt: Path) -> dict:
    registration_path = analysis_root / "registration.json"
    analysis_path = analysis_root / "analysis.json"
    verification_path = analysis_root / "independent-verification.json"
    registration = json.loads(registration_path.read_text())
    analysis = json.loads(analysis_path.read_text())
    verification = json.loads(verification_path.read_text())
    if analysis["status"] != "complete" or not verification["passed"]:
        raise ValueError("plot requires complete independently verified correction analysis")
    selected = analysis["trials"][f"{PROFILE}--42--straight-02"]
    derived_path = analysis_root / "derived" / selected["derived_npz"]
    if file_sha(derived_path) != selected["derived_npz_sha256"]:
        raise ValueError("selected derived array hash mismatch")
    with np.load(derived_path, allow_pickle=False) as derived:
        ticks = derived["ticks"]
        heights = derived["endpoint_whole_foot_min_height"]
        loads = derived["interval_summed_positive_normal"]

    fig, axes = plt.subplots(2, 2, figsize=(13.2, 8.4), constrained_layout=True)
    colors = {"historical": "#62676f", PROFILE: "#16766d"}
    labels = {"historical": "Historical 0.6", PROFILE: "Fixed candidate 1.0"}
    for profile in ("historical", PROFILE):
        for seed, marker in ((42, "o"), (43, "s")):
            speed = [analysis["trials"][f"{profile}--{seed}--{case}"]["forward_mean_mm_s"] for case in CASES]
            axes[0, 0].plot(
                [0.08, 0.2, 0.4], speed,
                color=colors[profile], marker=marker,
                linestyle="-" if profile == PROFILE else "--",
                alpha=0.9, label=f"{labels[profile]}, seed {seed}",
            )
        turns = []
        turn_x = (-0.8, -0.4, 0.4, 0.8)
        for asymmetry in turn_x:
            case = f"turn-{'negative' if asymmetry < 0 else 'positive'}-{abs(asymmetry):.1f}".replace("0.", "0")
            values = [analysis["trials"][f"{profile}--{seed}--{case}"]["net_active_yaw_rad"] for seed in (42, 43)]
            turns.append(float(np.mean(values)))
        axes[0, 1].plot(
            turn_x, turns,
            color=colors[profile], marker="o",
            linestyle="-" if profile == PROFILE else "--",
            label=labels[profile],
        )

    time_s = ticks * registration["clock"]["dt_s"]
    axes[1, 0].plot(time_s, heights[:, 2], color="#c0524d", linewidth=0.8, label="LH endpoint clearance")
    axes[1, 0].plot(time_s, heights[:, 5], color="#3a6ea5", linewidth=0.8, label="RH endpoint clearance")
    axes[1, 0].axhline(0.02, color="#222222", linewidth=1, linestyle=":", label="0.02 mm gate")
    loaded_scale = max(float(loads[:, [2, 5]].max()), 1.0)
    axes[1, 0].fill_between(
        time_s,
        0,
        np.minimum(loads[:, 2] / loaded_scale * 0.015, 0.015),
        color="#d7982d", alpha=0.28, label="LH owned interval load (scaled)",
    )
    axes[1, 0].set_xlim(0.6, 2.5)

    candidate_trials = [
        analysis["trials"][f"{PROFILE}--{seed}--{case}"]
        for seed in (42, 43)
        for case in ("straight-008", "straight-02", "straight-04", "turn-negative-08", "turn-positive-08")
    ]
    gate_names = ("upright", "stop", "recovery", "support_slip", "straight_yaw", "turn")
    grid = np.full((len(candidate_trials), len(gate_names)), np.nan)
    for row, trial in enumerate(candidate_trials):
        for column, gate in enumerate(gate_names):
            if gate in trial["gates"]:
                grid[row, column] = 1 if trial["gates"][gate] else 0
    cmap = ListedColormap(["#bd4b43", "#2f7d63"])
    cmap.set_bad("#dddddd")
    axes[1, 1].imshow(grid, aspect="auto", cmap=cmap, vmin=0, vmax=1)
    axes[1, 1].set_xticks(range(len(gate_names)), gate_names, rotation=28, ha="right")
    axes[1, 1].set_yticks(
        range(len(candidate_trials)),
        [f"{trial['conditions']['seed']} {trial['conditions']['case'][0]}" for trial in candidate_trials],
        fontsize=8,
    )

    axes[0, 0].set(title="Same-condition retained forward response", xlabel="common command", ylabel="mean forward speed (mm/s)")
    axes[0, 1].set(title="Same-condition retained signed turning", xlabel="command asymmetry", ylabel="net active yaw (rad)")
    axes[1, 0].set(title="Candidate straight 0.2: endpoint pose vs owned load intervals", xlabel="time (s)", ylabel="endpoint clearance (mm)")
    axes[1, 1].set_title("Operational gates, selected candidate conditions")
    for axis in axes.flat[:3]:
        axis.grid(alpha=0.2)
        axis.legend(fontsize=7, ncol=2)
    fig.suptitle(
        "Fly Arena v12 phase-correct retained-data analysis\n"
        "Descriptive and unadmitted: cache=start state, pose=end state, slip=pre-state velocity",
        fontsize=13,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=170, metadata={"Software": "Fly Arena behavior-v12 correction"})
    plt.close(fig)
    result = {
        "schema": "behavior-v12-correction-plot-receipt/v1",
        "analysis_sha256": file_sha(analysis_path),
        "registration_sha256": file_sha(registration_path),
        "independent_verification_sha256": file_sha(verification_path),
        "derived_input": str(derived_path),
        "derived_input_sha256": file_sha(derived_path),
        "producer": str(Path(__file__).resolve()),
        "producer_sha256": file_sha(Path(__file__).resolve()),
        "output": str(output.resolve()),
        "png_sha256": file_sha(output),
        "labels": {
            "pose": "authoritative core endpoint",
            "load": "raw solved normal force owned by interval",
            "slip": "left-endpoint pre-state material velocity",
            "status": "descriptive and unadmitted",
        },
    }
    receipt.parent.mkdir(parents=True, exist_ok=True)
    if receipt.exists():
        raise FileExistsError(receipt)
    write_json(receipt, result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    result = produce(args.analysis_root.resolve(), args.output.resolve(), args.receipt.resolve())
    print(json.dumps({"png_sha256": result["png_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
