"""Static v12 plots from independently reconstructed retained evidence."""
from pathlib import Path
import argparse
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from flyarena.experiments.cadence_v12 import PROFILE
from flyarena.experiments.mechanical_v12 import CORE, DENSE, _slices, _width
from flyarena.experiments.verify_v12 import read_dense


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reg = json.loads((args.root / "registration.json").read_text())
    decision = json.loads((args.root / "development-decision.json").read_text())
    cs, ds = _slices(CORE), _slices(DENSE)
    fig, axes = plt.subplots(2, 3, figsize=(16, 9), constrained_layout=True)
    colors = ["#187a72", "#d27522", "#7b4f9e"]
    for profile, style, label in [("historical", "--", "Historical"), (PROFILE, "-", "Candidate 1.0")]:
        for color, case in zip(colors, ["straight-008", "straight-02", "straight-04"]):
            name = f"{profile}--42--{case}"
            _, core = read_dense(args.root / "development" / name / "core", 40001, _width(CORE))
            pos = core[:, cs["thorax_position"]]
            axes[0, 0].plot(pos[::100, 0], pos[::100, 1], style, color=color,
                            label=f"{label} {case}")
        speeds = [decision["trials"][f"{profile}--42--{case}"]["forward_mean_mm_s"]
                  for case in ["straight-008", "straight-02", "straight-04"]]
        axes[0, 1].plot([0.08, 0.2, 0.4], speeds, style + "o", label=label)
        turns = [decision["trials"][f"{profile}--42--{case}"]["net_active_yaw_rad"]
                 for case in ["turn-negative-08", "turn-negative-04", "turn-positive-04", "turn-positive-08"]]
        axes[0, 2].plot([-0.8, -0.4, 0.4, 0.8], turns, style + "o", label=label)
    name = f"{PROFILE}--42--straight-02"
    ticks, dense = read_dense(args.root / "development" / name / "dense", 40001, _width(DENSE))
    time_s = ticks * reg["dt"]
    heights = dense[:, ds["whole_foot_min_height"]]
    loads = dense[:, ds["summed_positive_normal"]]
    for leg, leg_name in enumerate(["LF", "LM", "LH", "RF", "RM", "RH"]):
        axes[1, 0].plot(time_s[::10], heights[::10, leg], label=leg_name)
        axes[1, 1].plot(time_s[::10], loads[::10, leg], label=leg_name)
    trials = [value for value in decision["trials"].values() if value["conditions"]["profile"] == PROFILE]
    gate_names = ["upright", "stop", "recovery", "support_slip", "straight_yaw", "turn"]
    grid = np.array([[1 if trial["gates"].get(gate) is True else
                      0 if trial["gates"].get(gate) is False else np.nan
                      for gate in gate_names] for trial in trials])
    from matplotlib.colors import ListedColormap
    cmap = ListedColormap(["#b84c43", "#2f7d63"])
    cmap.set_bad("#e5e5e5")
    axes[1, 2].imshow(grid, aspect="auto", cmap=cmap, vmin=0, vmax=1)
    axes[1, 2].set_xticks(range(len(gate_names)), gate_names, rotation=30, ha="right")
    axes[1, 2].set_yticks(range(len(trials)),
        [f"{t['conditions']['seed']} {t['conditions']['case'][0]}" for t in trials], fontsize=7)
    axes[0, 0].set(title="Same-condition actual thorax paths, seed 42", xlabel="world x (mm)", ylabel="world y (mm)")
    axes[0, 0].axis("equal")
    axes[0, 1].set(title="Actual steady forward dose response", xlabel="common input", ylabel="mm/s")
    axes[0, 2].set(title="Actual signed turning", xlabel="command asymmetry", ylabel="net yaw (rad)")
    axes[1, 0].set(title="Candidate whole-foot clearance, straight 0.2", xlabel="time (s)", ylabel="minimum height (mm)")
    axes[1, 0].axhline(0.02, color="#b84c43", linewidth=1)
    axes[1, 1].set(title="Candidate integrated native normal load", xlabel="time (s)", ylabel="native force")
    axes[1, 2].set_title("Candidate development gates")
    for axis in axes.flat[:5]:
        axis.grid(alpha=0.2)
    for axis in [axes[0, 0], axes[0, 1], axes[0, 2], axes[1, 0], axes[1, 1]]:
        axis.legend(fontsize=7, ncol=2)
    fig.suptitle("Fly Arena v12 single-candidate physical experiment\nAll legs, all retained outcomes; failure blocks neural/product admission")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=170)


if __name__ == "__main__":
    main()
