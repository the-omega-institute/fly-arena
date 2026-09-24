#!/usr/bin/env python3
"""Run short body-only maze locomotion diagnostic windows.

This probe exercises the existing MuJoCo body and HybridTurningController
without a brain, target steering, route following, pose edits, or upright
resets.  It is a mechanics diagnostic, not a behavior or recovery claim.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from flyarena.body import Bodies
from flyarena.scenarios import arena_scene


def _upright(rotation: np.ndarray) -> float:
    return float(rotation[2, 2])


def run_window(*, wall_present: bool, drive_kind: str, seed: int, seconds: int) -> dict:
    scene = arena_scene("labyrinth", seed)
    if not wall_present:
        scene["obstacles"] = []
    body = Bodies(scene, 1, seed)
    drives = np.array([[.3, .3]] if drive_kind == "symmetric" else [[.25, .55]], dtype=float)
    samples = []
    steps = seconds * 10_000
    for tick in range(steps):
        body.step(drives)
        if body.tick % 100 == 0:
            position, rotation = body.pose(0)
            samples.append({"time": body.tick * .0001, "position": position.round(6).tolist(),
                            "upright_z": _upright(rotation)})
    up = np.asarray([row["upright_z"] for row in samples], dtype=float)
    xy = np.asarray([row["position"][:2] for row in samples], dtype=float)
    return {
        "wall_present": wall_present, "drive_kind": drive_kind, "seed": seed,
        "seconds": seconds, "recorded_samples": len(samples),
        "upright_fraction": float(np.mean(up >= 0)) if len(up) else None,
        "minimum_upright_z": float(np.min(up)) if len(up) else None,
        "first_inversion_time_s": next((row["time"] for row in samples if row["upright_z"] < 0), None),
        "path_length_mm": float(np.linalg.norm(np.diff(xy, axis=0), axis=1).sum()) if len(xy) > 1 else 0.,
        "final_position_mm": samples[-1]["position"] if samples else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=5, choices=range(5, 11))
    parser.add_argument("--seed", type=int, action="append", dest="seeds")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    seeds = args.seeds or [42, 43]
    if any(seed < 0 or seed > 2**31 - 1 for seed in seeds):
        parser.error("seeds must be nonnegative int32 values")
    rows = []
    for seed in seeds:
        for wall_present in (True, False):
            for drive_kind in ("symmetric", "differential"):
                rows.append(run_window(wall_present=wall_present, drive_kind=drive_kind,
                                       seed=seed, seconds=args.seconds))
    report = {"schema_version": "maze-locomotion-body-probe/v1", "model": "existing Bodies + HybridTurningController",
              "scientific_scope": "body-only diagnostic; no brain, target steering, route following or pose reset",
              "windows": rows}
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload)
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
