#!/usr/bin/env python3
"""Measure inversion and locomotion outcomes from an immutable maze replay.

The command consumes only recorded ``scene.json``, ``frames.json`` and
``events.json``.  It never fills missing poses, infers contacts from distance,
or treats an absent goal contact as a zero-time success.  A directory or a
``.tar.gz`` release asset is accepted; the report says exactly which source
files were available. Release gallery filenames are accepted and their receipt
hashes are checked before analysis.
"""
from __future__ import annotations

import argparse
import json
import math
import tarfile
import tempfile
from pathlib import Path

import numpy as np

from flyarena.common import digest, file_sha


PHYSICS_DT = 0.0001
UPRIGHT_EPSILON = 0.0
COVERAGE_CELL_MM = 1.0


def _json(path: Path):
    return json.loads(path.read_text())


def _replay_paths(root: Path) -> dict[str, Path]:
    prefix = ""
    if not (root / "scene.json").is_file():
        scenes = sorted(root.glob("*-scene.json"))
        if len(scenes) != 1:
            raise ValueError("select a directory containing exactly one replay")
        prefix = scenes[0].name.removesuffix("scene.json")
    paths = {name: root / f"{prefix}{name}.json" for name in ("scene", "frames", "events", "receipt", "match")}
    if not all(paths[name].is_file() for name in ("scene", "frames", "events")):
        raise FileNotFoundError("replay is missing scene, frames or events")
    return paths


def verify_replay(paths: dict[str, Path]) -> dict:
    """Reuse the canonical digest/file hash helpers used by bundle verification.

    The gallery excludes full-run checkpoints. Match metadata is checked for
    consistency with the receipt; the receipt does not hash match.json itself.
    """
    if not paths["receipt"].is_file():
        raise ValueError("replay receipt is missing")
    receipt = _json(paths["receipt"])
    hashes = {}
    for name in ("scene", "frames", "events"):
        actual = file_sha(paths[name])
        if receipt.get("files", {}).get(f"{name}.json") != actual:
            raise ValueError(f"receipt hash mismatch: {name}.json")
        hashes[f"{name}.json"] = actual
    receipt_id = digest({key: value for key, value in receipt.items() if key != "sha256"})
    if receipt.get("sha256") != receipt_id:
        raise ValueError("receipt canonical digest mismatch")
    receipt_file = file_sha(paths["receipt"])
    if paths["match"].is_file():
        match = _json(paths["match"])
        source = match.get("source", {})
        participants = receipt.get("flies", [])
        request = receipt.get("request", {})
        if (match.get("status") != "verified" or match.get("request") != request
                or match.get("result", {}).get("receipt_sha256") != receipt_id
                or source.get("receipt_sha256") != receipt_id
                or source.get("receipt_file_sha256") != receipt_file
                or [p["id"] for p in participants] != request.get("fly_ids")
                or [(p["id"], p["artifact_id"]) for p in participants]
                != [(p["id"], p["artifact_id"]) for p in match.get("participants", [])]):
            raise ValueError("match metadata differs from receipt")
    return {"status": "verified", "receipt_sha256": receipt_id, "files": hashes,
            "receipt_file_sha256": receipt_file, "match_metadata_checked": paths["match"].is_file(),
            "scope": "supplied replay files only; match.json is not hashed by the receipt",
            "omitted_receipt_files": sorted(set(receipt["files"]) - set(hashes))}


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
            try:
                _replay_paths(candidate)
            except (ValueError, FileNotFoundError):
                continue
            return candidate, temporary
        temporary.cleanup()
        raise FileNotFoundError("archive does not contain scene.json, frames.json and events.json")
    raise FileNotFoundError(f"replay source is not a directory or tar archive: {source}")


def _physics_dt(paths: dict[str, Path]) -> float:
    for name in ("receipt", "scene"):
        path = paths[name]
        if path.is_file():
            value = _json(path)
            for candidate in (
                value.get("replay_policy", {}).get("physics_dt"),
                value.get("runtime", {}).get("rules", {}).get("physics_dt"),
                value.get("runtime", {}).get("closure", {}).get("physics_dt"),
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


def _up_projection(quaternion: tuple[float, float, float, float], reference=None) -> float:
    w, x, y, z = quaternion
    norm = math.sqrt(w * w + x * x + y * y + z * z)
    if not math.isfinite(norm) or norm <= 0:
        raise ValueError("recorded thorax quaternion is invalid")
    w, x, y, z = (v / norm for v in quaternion)
    if reference is not None:
        reference = np.asarray(reference, dtype=float)
        reference_norm = float(np.linalg.norm(reference))
        if not math.isfinite(reference_norm) or reference_norm <= 0:
            raise ValueError("initial thorax quaternion is invalid")
        a, b, c, d = reference / reference_norm
        # q(t) * inverse(q(0)), as in flyarena.behavior.behavior_metrics.
        # Rendered mesh axes are not the anatomical body's axes.
        x, y = -w*b + x*a - y*d + z*c, -w*c + x*d + y*a - z*b
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


def _sample_intervals(times: np.ndarray, states: list[bool]) -> list[dict]:
    """Left-hold estimate between observed frames, clipped to the last frame.

    Onset-only events never enter this duration calculation. Unknown samples
    interrupt a run; nothing is projected beyond the recording horizon.
    """
    runs = []
    for i, state in enumerate(states[:-1]):
        if not state:
            continue
        start, end = float(times[i]), float(times[i + 1])
        if runs and runs[-1]["end_s"] == start:
            runs[-1]["end_s"] = end
            runs[-1]["duration_s"] = end - runs[-1]["start_s"]
        else:
            runs.append({"start_s": start, "end_s": end, "duration_s": end - start})
    return runs


def _wall_objects(frame: dict, slot: int) -> list[str] | None:
    senses = frame.get("senses", [])
    if slot < len(senses) and isinstance(senses[slot].get("contact_environment"), list):
        return [name for name in senses[slot]["contact_environment"] if str(name).startswith("obstacle-")]
    return None


def _drive_statistics(drives: list, mask: np.ndarray) -> dict:
    selected = np.asarray([drive for drive, include in zip(drives, mask) if include and drive is not None])
    if len(selected) and not np.isfinite(selected).all():
        raise ValueError("recorded drives must be finite")
    result = {"samples": len(selected),
              "missing_samples": int(sum(include and drive is None for drive, include in zip(drives, mask)))}
    for index, side in enumerate(("left", "right")):
        for name, fn in (("mean", np.mean), ("std", np.std), ("min", np.min), ("max", np.max)):
            result[f"{side}_{name}"] = float(fn(selected[:, index])) if len(selected) else None
    difference = selected[:, 1] - selected[:, 0] if len(selected) else []
    result.update({"right_minus_left_mean": float(np.mean(difference)) if len(selected) else None,
                   "right_greater_fraction": float(np.mean(difference > 0)) if len(selected) else None})
    return result


def analyze_replay(root: Path, *, slot: int = 0) -> dict:
    paths = _replay_paths(root)
    verification = verify_replay(paths)
    scene, frames, events = (_json(paths[name]) for name in ("scene", "frames", "events"))
    if not isinstance(frames, list) or len(frames) < 2:
        raise ValueError("replay needs at least two recorded frames")
    if not isinstance(events, list):
        raise ValueError("events.json must contain a recorded event list")
    dt = _physics_dt(paths)
    times = np.asarray([_frame_time(frame, dt) for frame in frames], dtype=float)
    if not np.isfinite(times).all() or np.any(np.diff(times) <= 0):
        raise ValueError("frame times are incomplete or non-increasing")
    reference = _pose_quaternion(frames[0], scene, slot)
    up = []
    positions = []
    drives = []
    for frame in frames:
        quaternion = _pose_quaternion(frame, scene, slot)
        if quaternion is None:
            raise ValueError("replay has no recorded thorax pose for the selected slot")
        up.append(_up_projection(quaternion, reference))
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
    wall_events = [{"time_s": t, "objects": event.get("objects", [])} for event in events
                   if _contact_event(event, "__none__")
                   and event.get("type") in {"wall_contact", "environment_contact"}
                   and (t := _event_time(event, dt)) is not None
                   and event.get("slot") == slot]
    wall_objects = [_wall_objects(frame, slot) for frame in frames]
    wall_timeline = _sample_intervals(times, [bool(objects) for objects in wall_objects])
    window_mask = (times >= 45.) & (times < 65.)
    window_indices = np.flatnonzero(window_mask)
    window_objects = sorted({obj for i in window_indices for obj in (wall_objects[i] or [])})
    window = {"start_s": 45., "end_s": 65., "frames": len(window_indices),
              "contact_samples": sum(bool(wall_objects[i]) for i in window_indices),
              "missing_contact_samples": sum(wall_objects[i] is None for i in window_indices),
              "objects": {obj: sum(obj in (wall_objects[i] or []) for i in window_indices) for obj in window_objects},
              "onsets": [event for event in wall_events if 45. <= event["time_s"] < 65.],
              "sampled_intervals": [{"start_s": max(45., row["start_s"]), "end_s": min(65., row["end_s"]),
                                     "duration_s": min(65., row["end_s"]) - max(45., row["start_s"])}
                                    for row in wall_timeline if row["end_s"] > 45. and row["start_s"] < 65.]}
    goal_id = scene.get("task", {}).get("goal_food", "food-0")
    goal_events = [event for event in events if event.get("type") == "food_contact"
                   and goal_id in event.get("food", []) and event.get("slot", slot) == slot]
    goal_times = [t for event in goal_events if (t := _event_time(event, dt)) is not None]
    pre_mask = times < first_inversion if first_inversion is not None else np.ones(len(times), dtype=bool)
    drive_stats = _drive_statistics(drives, pre_mask)
    final_pre_mask = pre_mask & (times >= first_inversion - 5.) if first_inversion is not None else np.zeros(len(times), dtype=bool)
    xy = np.asarray(positions, dtype=float)
    if not np.isfinite(xy).all():
        raise ValueError("recorded thorax positions must be finite")
    cells = {tuple(np.floor(point / COVERAGE_CELL_MM).astype(int)) for point in xy}
    goal_position = next((food.get("position") for food in scene.get("food", []) if food.get("id") == goal_id), None)
    result = {
        "schema_version": "maze-locomotion-diagnosis/v2",
        "verification": verification,
        "source": str(root), "slot": slot, "recorded_frames": len(frames),
        "observed_seconds": duration, "upright_fraction": upright_seconds / duration if duration > 0 else None,
        "first_inversion_time_s": first_inversion, "inversion_episodes": intervals,
        "upright_sample_fraction": float(np.mean(upright)),
        "upright_seconds": upright_seconds,
        "wall_contact_timeline": wall_timeline,
        "wall_contact_onsets": wall_events,
        "wall_contact_sampled_seconds": (sum(row["duration_s"] for row in wall_timeline)
                                         if any(objects is not None for objects in wall_objects[:-1]) else None),
        "wall_contact_missing_samples": sum(objects is None for objects in wall_objects),
        "wall_contact_window_45_65_s": window,
        "left_right_drive_before_inversion": drive_stats,
        "left_right_drive_final_5s_before_inversion": _drive_statistics(drives, final_pre_mask),
        "goal_contact": {"food_id": goal_id, "first_contact_time_s": min(goal_times) if goal_times else None,
                         "contact_count": len(goal_times), "reached": bool(goal_times)},
        "coverage": {"cell_size_mm": COVERAGE_CELL_MM, "unique_xy_cells": len(cells),
                     "path_length_mm": float(np.linalg.norm(np.diff(xy, axis=0), axis=1).sum()),
                     "bbox_mm": [float(v) for v in (xy.max(axis=0) - xy.min(axis=0))],
                     "goal_position_recorded": goal_position is not None},
        "thresholds": {"upright_z_projection_gte": UPRIGHT_EPSILON,
                       "orientation_reference": "initial recorded thorax pose; q(t) * inverse(q(0))",
                       "wall_contact_source": "per-slot senses.contact_environment; events are onsets only",
                       "duration_estimator": "left-hold to next frame, clipped at final frame; unknown contacts excluded"},
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
