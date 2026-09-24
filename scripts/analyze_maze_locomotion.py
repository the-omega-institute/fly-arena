#!/usr/bin/env python3
"""Measure inversion and locomotion outcomes from an immutable maze replay.

The command consumes only recorded ``scene.json``, ``frames.json`` and
``events.json``.  It never fills missing poses, infers contacts from distance,
or treats an absent goal contact as a zero-time success.  A directory or a
``.tar.gz`` release asset is accepted; the report says exactly which source
files were available.
"""
from __future__ import annotations

import argparse
import json
import math
import tarfile
import tempfile
from pathlib import Path

import numpy as np


PHYSICS_DT = 0.0001
UPRIGHT_EPSILON = 0.0
COVERAGE_CELL_MM = 1.0


def _json(path: Path):
    return json.loads(path.read_text())


def _source_root(source: Path):
    if source.is_dir():
        return source, None
    if source.is_file() and tarfile.is_tarfile(source):
        temporary = tempfile.TemporaryDirectory(prefix="maze-locomotion-")
        with tarfile.open(source) as archive:
            members = [m for m in archive.getmembers() if m.isfile()]
            archive.extractall(temporary.name, members=members, filter="data")
        root = Path(temporary.name)
        candidates = [root, *sorted(p for p in root.rglob("*") if p.is_dir())]
        for candidate in candidates:
            if all((candidate / name).is_file() for name in ("scene.json", "frames.json", "events.json")):
                return candidate, temporary
        temporary.cleanup()
        raise FileNotFoundError("archive does not contain scene.json, frames.json and events.json")
    raise FileNotFoundError(f"replay source is not a directory or tar archive: {source}")


def _physics_dt(root: Path) -> float:
    for name in ("receipt.json", "scene.json"):
        path = root / name
        if path.is_file():
            value = _json(path)
            for candidate in (
                value.get("runtime", {}).get("rules", {}).get("physics_dt"),
                value.get("physics_dt"),
            ):
                if isinstance(candidate, (int, float)) and math.isfinite(candidate) and candidate > 0:
                    return float(candidate)
    return PHYSICS_DT


def _thorax_index(scene: dict, slot: int) -> int | None:
    for index, item in enumerate(scene.get("body", {}).get("geoms", [])):
        if item.get("slot") == slot and str(item.get("name", "")).endswith("/c_thorax"):
            # ``poses`` follows the rendered-geom list order; the MuJoCo geom
            # id itself is not a pose-list index.
            return index
    return None


def _pose_quaternion(frame: dict, scene: dict, slot: int) -> tuple[float, float, float, float] | None:
    poses = frame.get("poses")
    index = _thorax_index(scene, slot)
    if isinstance(poses, list) and index is not None and index < len(poses):
        pose = poses[index]
        if isinstance(pose, list) and len(pose) >= 7:
            return tuple(float(v) for v in pose[3:7])
    # Small synthetic fixtures may use a per-slot quaternion field.  It is
    # still recorded pose data, never a reconstructed posture.
    quaternions = frame.get("quaternions")
    if isinstance(quaternions, list) and slot < len(quaternions) and len(quaternions[slot]) == 4:
        return tuple(float(v) for v in quaternions[slot])
    return None


def _up_projection(quaternion: tuple[float, float, float, float]) -> float:
    w, x, y, z = quaternion
    norm = math.sqrt(w * w + x * x + y * y + z * z)
    if not math.isfinite(norm) or norm <= 0:
        raise ValueError("recorded thorax quaternion is invalid")
    w, x, y, z = (v / norm for v in quaternion)
    # World-Z projection of the body's local-Z axis for a wxyz quaternion.
    return 1.0 - 2.0 * (x * x + y * y)


def _frame_time(frame: dict, dt: float) -> float:
    if isinstance(frame.get("time"), (int, float)):
        return float(frame["time"])
    if isinstance(frame.get("tick"), (int, float)):
        return float(frame["tick"]) * dt
    raise ValueError("frame has no recorded time or tick")


def _slot_drive(frame: dict, slot: int) -> tuple[float, float] | None:
    drives = frame.get("drives")
    if isinstance(drives, list) and slot < len(drives) and len(drives[slot]) >= 2:
        return float(drives[slot][0]), float(drives[slot][1])
    left, right = frame.get("drive_left"), frame.get("drive_right")
    if left is not None and right is not None:
        return float(left), float(right)
    return None


def _contact_event(event: dict, goal_id: str) -> bool:
    if event.get("type") == "food_contact":
        return goal_id in event.get("food", [])
    if event.get("type") in {"wall_contact", "environment_contact"}:
        if event.get("type") == "wall_contact":
            return True
        objects = event.get("objects", [])
        return any(str(obj).startswith("obstacle-") for obj in objects)
    return False


def _event_time(event: dict, dt: float) -> float | None:
    if isinstance(event.get("time"), (int, float)):
        return float(event["time"])
    if isinstance(event.get("tick"), (int, float)):
        return float(event["tick"]) * dt
    return None


def _intervals(times: list[float], *, sample_dt: float) -> list[dict]:
    if not times:
        return []
    times = sorted(set(times))
    runs: list[list[float]] = [[times[0]]]
    for value in times[1:]:
        if value - runs[-1][-1] <= sample_dt * 1.5 + 1e-12:
            runs[-1].append(value)
        else:
            runs.append([value])
    return [{"start_s": run[0], "end_s": run[-1] + sample_dt,
             "duration_s": (run[-1] - run[0]) + sample_dt} for run in runs]


def analyze_replay(root: Path, *, slot: int = 0) -> dict:
    scene, frames, events = _json(root / "scene.json"), _json(root / "frames.json"), _json(root / "events.json")
    if not isinstance(frames, list) or len(frames) < 2:
        raise ValueError("replay needs at least two recorded frames")
    if not isinstance(events, list):
        raise ValueError("events.json must contain a recorded event list")
    dt = _physics_dt(root)
    times = np.asarray([_frame_time(frame, dt) for frame in frames], dtype=float)
    if not np.isfinite(times).all() or np.any(np.diff(times) <= 0):
        raise ValueError("frame times are incomplete or non-increasing")
    up = []
    positions = []
    drives = []
    for frame in frames:
        quaternion = _pose_quaternion(frame, scene, slot)
        if quaternion is None:
            raise ValueError("replay has no recorded thorax pose for the selected slot")
        up.append(_up_projection(quaternion))
        frame_positions = frame.get("positions")
        if not isinstance(frame_positions, list) or slot >= len(frame_positions) or len(frame_positions[slot]) < 2:
            raise ValueError("replay has no recorded thorax positions for the selected slot")
        positions.append([float(v) for v in frame_positions[slot][:2]])
        drives.append(_slot_drive(frame, slot))
    up = np.asarray(up, dtype=float)
    upright = up >= UPRIGHT_EPSILON
    intervals = []
    for i, value in enumerate(upright):
        if not value and (i == 0 or upright[i - 1]):
            start = float(times[i])
            end_i = i
            while end_i + 1 < len(upright) and not upright[end_i + 1]:
                end_i += 1
            recovered = end_i + 1 < len(upright)
            end = float(times[end_i + 1] if recovered else times[-1])
            intervals.append({"start_s": start, "end_s": end,
                              "duration_s": end - start,
                              "recovered": recovered,
                              "recovery_duration_s": end - start if recovered else None})
    duration = float(times[-1] - times[0])
    upright_seconds = float(sum((times[i + 1] - times[i]) for i in range(len(times) - 1) if upright[i]))
    first_inversion = next((float(t) for t, value in zip(times, upright) if not value), None)
    wall_event_times = [t for event in events if _contact_event(event, "__none__")
                        and event.get("type") in {"wall_contact", "environment_contact"}
                        and (t := _event_time(event, dt)) is not None
                        and (event.get("slot") in (None, slot))]
    wall_frame_times = []
    for time, frame in zip(times, frames):
        if isinstance(frame.get("wall_contact_ticks"), (int, float)) and frame["wall_contact_ticks"] > 0:
            wall_frame_times.append(float(time))
        elif isinstance(frame.get("contact_environment"), list) and frame["contact_environment"]:
            wall_frame_times.append(float(time))
    wall_times = sorted(set(wall_event_times + wall_frame_times))
    sample_dt = float(np.median(np.diff(times)))
    goal_id = scene.get("task", {}).get("goal_food", "food-0")
    goal_events = [event for event in events if event.get("type") == "food_contact"
                   and goal_id in event.get("food", []) and event.get("slot", slot) == slot]
    goal_times = [t for event in goal_events if (t := _event_time(event, dt)) is not None]
    pre_mask = times < first_inversion if first_inversion is not None else np.ones(len(times), dtype=bool)
    pre_drives = np.asarray([drive for drive in drives if drive is not None], dtype=float)
    pre_drives = pre_drives[pre_mask[[i for i, drive in enumerate(drives) if drive is not None]]] if len(pre_drives) else pre_drives
    if len(pre_drives):
        drive_stats = {"samples": int(len(pre_drives)),
                       "left_mean": float(pre_drives[:, 0].mean()), "right_mean": float(pre_drives[:, 1].mean()),
                       "left_std": float(pre_drives[:, 0].std()), "right_std": float(pre_drives[:, 1].std())}
    else:
        drive_stats = {"samples": 0, "left_mean": None, "right_mean": None, "left_std": None, "right_std": None}
    xy = np.asarray(positions, dtype=float)
    cells = {tuple(np.floor(point / COVERAGE_CELL_MM).astype(int)) for point in xy}
    goal_position = next((food.get("position") for food in scene.get("food", []) if food.get("id") == goal_id), None)
    result = {
        "schema_version": "maze-locomotion-diagnosis/v1",
        "source": str(root), "slot": slot, "recorded_frames": len(frames),
        "observed_seconds": duration, "upright_fraction": upright_seconds / duration if duration > 0 else None,
        "first_inversion_time_s": first_inversion, "inversion_episodes": intervals,
        "wall_contact_timeline": _intervals(wall_times, sample_dt=sample_dt),
        "left_right_drive_before_inversion": drive_stats,
        "goal_contact": {"food_id": goal_id, "first_contact_time_s": min(goal_times) if goal_times else None,
                         "contact_count": len(goal_times), "reached": bool(goal_times)},
        "coverage": {"cell_size_mm": COVERAGE_CELL_MM, "unique_xy_cells": len(cells),
                     "path_length_mm": float(np.linalg.norm(np.diff(xy, axis=0), axis=1).sum()),
                     "bbox_mm": [float(v) for v in (xy.max(axis=0) - xy.min(axis=0))],
                     "goal_position_recorded": goal_position is not None},
        "thresholds": {"upright_z_projection_gte": UPRIGHT_EPSILON, "wall_contact_source": "recorded events/frames"},
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("replay", type=Path, help="Replay directory or release tar.gz")
    parser.add_argument("--slot", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.slot < 0:
        parser.error("--slot must be nonnegative")
    root, temporary = _source_root(args.replay)
    try:
        report = analyze_replay(root, slot=args.slot)
        payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload)
        else:
            print(payload, end="")
    finally:
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    main()
