#!/usr/bin/env python3
"""Compare one recorded phase-2 baseline/candidate seed pair.

This is an analysis-only tool. It reads the two arms' recorded
``frames.json``, ``events.json`` and ``receipt.json`` files, verifies the
receipt bindings, and never starts a simulation or reconstructs a pose from
position data. Values derived from poses or from the candidate receipt are
labelled as proxies/modelled quantities in the JSON output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np


ARMS = ("baseline", "candidate")
CORRECTION_FIELDS = ("upright_z", "roll_rate", "pitch_rate", "support_left", "support_right")
DEFAULT_PHYSICS_DT = 0.0001
UPRIGHT_THRESHOLD = 0.0


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode()


def _digest(value) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path):
    return json.loads(path.read_text())


def _finite(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def _run_root(seed_directory: Path, arm: str) -> Path:
    root = seed_directory / arm
    if not root.is_dir():
        raise FileNotFoundError(f"missing {arm} directory under {seed_directory}")
    replay = root / "replay"
    if replay.is_dir():
        root = replay
    required = ("frames.json", "events.json", "receipt.json")
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise FileNotFoundError(f"{arm} is missing {', '.join(missing)}")
    return root


def _verify_receipt(root: Path) -> tuple[dict, dict]:
    receipt = _json(root / "receipt.json")
    if not isinstance(receipt, dict):
        raise ValueError(f"{root}: receipt.json must contain an object")
    files = receipt.get("files")
    if not isinstance(files, dict):
        raise ValueError(f"{root}: receipt has no file bindings")
    hashes = {}
    for name in ("frames.json", "events.json"):
        expected = files.get(name)
        if not isinstance(expected, str):
            raise ValueError(f"{root}: receipt does not bind {name}")
        actual = _file_sha(root / name)
        if actual != expected:
            raise ValueError(f"{root}: receipt hash mismatch: {name}")
        hashes[name] = actual
    if "sha256" in receipt:
        actual_digest = _digest({key: value for key, value in receipt.items() if key != "sha256"})
        if receipt["sha256"] != actual_digest:
            raise ValueError(f"{root}: receipt canonical digest mismatch")
    return receipt, {"status": "verified", "files": hashes,
                     "receipt_sha256": receipt.get("sha256")}


def _physics_dt(receipt: dict) -> float:
    candidates = (
        receipt.get("replay_policy", {}).get("physics_dt"),
        receipt.get("runtime", {}).get("rules", {}).get("physics_dt"),
        receipt.get("runtime", {}).get("closure", {}).get("physics_dt"),
        receipt.get("physics_dt"),
    )
    for value in candidates:
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0:
            return float(value)
    return DEFAULT_PHYSICS_DT


def _frame_times(frames: list[dict], dt: float) -> np.ndarray:
    times = []
    for index, frame in enumerate(frames):
        if isinstance(frame.get("time"), (int, float)) and not isinstance(frame.get("time"), bool):
            times.append(_finite(frame["time"], f"frame {index} time"))
        elif isinstance(frame.get("tick"), (int, float)) and not isinstance(frame.get("tick"), bool):
            times.append(_finite(frame["tick"], f"frame {index} tick") * dt)
        else:
            raise ValueError(f"frame {index} has no recorded time or tick")
    result = np.asarray(times, dtype=float)
    if len(result) < 2 or not np.all(np.diff(result) > 0):
        raise ValueError("frames must contain at least two strictly increasing recorded times")
    return result


def _slot_item(frame: dict, key: str, slot: int):
    values = frame.get(key)
    if not isinstance(values, list) or slot >= len(values):
        return None
    return values[slot]


def _quaternion(frame: dict, slot: int, pose_index: int) -> np.ndarray | None:
    """Read a recorded thorax quaternion without using positions as a pose."""
    candidates = []
    direct = frame.get("thorax_quaternion")
    if isinstance(direct, list):
        candidates.append(direct)
    quaternions = frame.get("quaternions")
    if isinstance(quaternions, list) and slot < len(quaternions):
        candidates.append(quaternions[slot])
    poses = frame.get("poses")
    if isinstance(poses, list):
        if pose_index < len(poses):
            candidates.append(poses[pose_index])
        if slot < len(poses):
            candidates.append(poses[slot])
    for value in candidates:
        if isinstance(value, list) and len(value) == 4:
            quaternion = np.asarray([_finite(item, "recorded quaternion") for item in value], dtype=float)
            norm = float(np.linalg.norm(quaternion))
            if norm <= 0 or not math.isfinite(norm):
                raise ValueError("recorded quaternion has zero or non-finite norm")
            return quaternion / norm
        if isinstance(value, list) and len(value) >= 7:
            quaternion = np.asarray([_finite(item, "recorded pose quaternion") for item in value[3:7]], dtype=float)
            norm = float(np.linalg.norm(quaternion))
            if norm <= 0 or not math.isfinite(norm):
                raise ValueError("recorded pose quaternion has zero or non-finite norm")
            return quaternion / norm
    return None


def _quat_multiply(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    lw, lx, ly, lz = left
    rw, rx, ry, rz = right
    return np.asarray([lw * rw - lx * rx - ly * ry - lz * rz,
                       lw * rx + lx * rw + ly * rz - lz * ry,
                       lw * ry - lx * rz + ly * rw + lz * rx,
                       lw * rz + lx * ry - ly * rx + lz * rw])


def _quat_conjugate(quaternion: np.ndarray) -> np.ndarray:
    return np.asarray([quaternion[0], -quaternion[1], -quaternion[2], -quaternion[3]])


def _upright_z(quaternion: np.ndarray, reference: np.ndarray) -> float:
    relative = _quat_multiply(quaternion, _quat_conjugate(reference))
    relative /= np.linalg.norm(relative)
    return float(1.0 - 2.0 * (relative[1] ** 2 + relative[2] ** 2))


def _pose_rate(previous: np.ndarray | None, current: np.ndarray, dt: float) -> tuple[float, float] | None:
    if previous is None:
        return None
    # q and -q encode the same pose. Pick the short increment before taking
    # its rotation vector; this is a pose-derived rate proxy, not a recorded
    # local MuJoCo angular-rate measurement.
    if float(np.dot(previous, current)) < 0:
        current = -current
    delta = _quat_multiply(current, _quat_conjugate(previous))
    delta /= np.linalg.norm(delta)
    vector_norm = float(np.linalg.norm(delta[1:]))
    angle = 2.0 * math.atan2(vector_norm, max(-1.0, min(1.0, float(delta[0]))))
    rotation_vector = np.zeros(3) if vector_norm <= 1e-12 else delta[1:] * (angle / vector_norm)
    return float(rotation_vector[0] / dt), float(rotation_vector[1] / dt)


def _recorded_support(sense: dict) -> tuple[float, float] | None:
    value = sense.get("contact_support")
    if isinstance(value, dict):
        left = value.get("left", value.get("l"))
        right = value.get("right", value.get("r"))
        if left is not None and right is not None:
            if isinstance(left, list) and isinstance(right, list):
                return len(left) / 3.0, len(right) / 3.0
            return _finite(left, "recorded left support"), _finite(right, "recorded right support")
    if isinstance(value, list):
        names = [str(name).rsplit("/", 1)[-1] for name in value]
        left = sum(name.startswith(("lf", "lm", "lh")) for name in names) / 3.0
        right = sum(name.startswith(("rf", "rm", "rh")) for name in names) / 3.0
        return float(left), float(right)
    return None


def _correction_series(frames: list[dict], times: np.ndarray, slot: int, pose_index: int) -> dict:
    quaternions = [_quaternion(frame, slot, pose_index) for frame in frames]
    if any(quaternion is None for quaternion in quaternions):
        raise ValueError("every frame needs a recorded quaternion for inversion analysis")
    reference = quaternions[0]
    pose_upright = [_upright_z(quaternion, reference) for quaternion in quaternions]
    pose_rates = [None]
    for index in range(1, len(quaternions)):
        pose_rates.append(_pose_rate(quaternions[index - 1], quaternions[index],
                                     float(times[index] - times[index - 1])))

    rows = []
    availability = {field: {"recorded": 0, "pose_proxy": 0, "unavailable": 0} for field in CORRECTION_FIELDS}
    for index, (frame, time) in enumerate(zip(frames, times)):
        sense = _slot_item(frame, "senses", slot)
        sense = sense if isinstance(sense, dict) else {}
        recorded = sense.get("motor_body_state")
        recorded = recorded if isinstance(recorded, dict) else {}
        support = _recorded_support(sense)
        values = {}
        sources = {}
        for field in CORRECTION_FIELDS:
            value = recorded.get(field)
            if value is not None:
                values[field] = _finite(value, f"recorded {field}")
                sources[field] = "recorded_motor_body_state"
            elif field == "upright_z":
                values[field] = pose_upright[index]
                sources[field] = "pose_derived_proxy"
            elif field in {"roll_rate", "pitch_rate"} and pose_rates[index] is not None:
                values[field] = pose_rates[index][0 if field == "roll_rate" else 1]
                sources[field] = "pose_derived_proxy"
            elif field in {"support_left", "support_right"} and support is not None:
                values[field] = support[0 if field == "support_left" else 1]
                sources[field] = "recorded_support_contact"
            else:
                values[field] = None
                sources[field] = "unavailable"
            bucket = sources[field].replace("recorded_motor_body_state", "recorded").replace(
                "recorded_support_contact", "recorded").replace("pose_derived_proxy", "pose_proxy")
            availability[field][bucket] += 1
        rows.append({"time_s": float(time), "pose_upright_z": pose_upright[index], **values, "sources": sources})
    return {"source_policy": "recorded motor_body_state first; pose/support proxies only when explicitly available",
            "fields": list(CORRECTION_FIELDS), "samples": rows, "availability": availability}


def _drive(frame: dict, slot: int) -> tuple[float, float] | None:
    drives = _slot_item(frame, "drives", slot)
    if isinstance(drives, list) and len(drives) >= 2:
        return _finite(drives[0], "recorded left drive"), _finite(drives[1], "recorded right drive")
    if frame.get("drive_left") is not None and frame.get("drive_right") is not None:
        return _finite(frame["drive_left"], "recorded left drive"), _finite(frame["drive_right"], "recorded right drive")
    return None


def _positions(frames: list[dict], slot: int) -> list[np.ndarray | None]:
    result = []
    for frame in frames:
        position = _slot_item(frame, "positions", slot)
        if not isinstance(position, list) or len(position) < 2:
            result.append(None)
        else:
            result.append(np.asarray([_finite(position[0], "recorded x position"),
                                     _finite(position[1], "recorded y position")], dtype=float))
    return result


def _wall_objects(frame: dict, slot: int) -> list[str] | None:
    sense = _slot_item(frame, "senses", slot)
    if not isinstance(sense, dict) or not isinstance(sense.get("contact_environment"), list):
        return None
    return sorted(str(name) for name in sense["contact_environment"] if str(name).startswith("obstacle-"))


def _event_time(event: dict, dt: float) -> float | None:
    if isinstance(event.get("time"), (int, float)) and not isinstance(event.get("time"), bool):
        return _finite(event["time"], "recorded event time")
    if isinstance(event.get("tick"), (int, float)) and not isinstance(event.get("tick"), bool):
        return _finite(event["tick"], "recorded event tick") * dt
    return None


def _wall_onsets(events: list[dict], slot: int, dt: float, first_inversion: float | None) -> list[dict]:
    result = []
    for event in events:
        if event.get("slot") != slot or event.get("type") not in {"wall_contact", "environment_contact"}:
            continue
        if event.get("type") == "environment_contact":
            objects = [str(value) for value in event.get("objects", []) if str(value).startswith("obstacle-")]
            if not objects:
                continue
        else:
            objects = [str(value) for value in event.get("objects", [])]
        time = _event_time(event, dt)
        if time is None or (first_inversion is not None and time >= first_inversion):
            continue
        result.append({"time_s": time, "objects": objects, "event_type": event["type"]})
    return result


def _inversions(times: np.ndarray, upright: list[float]) -> list[dict]:
    result = []
    for index, value in enumerate(upright):
        if value >= UPRIGHT_THRESHOLD or (index and upright[index - 1] < UPRIGHT_THRESHOLD):
            continue
        end_index = index
        while end_index + 1 < len(upright) and upright[end_index + 1] < UPRIGHT_THRESHOLD:
            end_index += 1
        end = float(times[end_index + 1] if end_index + 1 < len(times) else times[-1])
        result.append({"start_s": float(times[index]), "end_s": end, "duration_s": end - float(times[index]),
                       "recovered": end_index + 1 < len(upright)})
    return result


def _drive_stats(drives: list[tuple[float, float] | None], times: np.ndarray,
                 start: float, end: float) -> dict:
    selected = [drive for drive, time in zip(drives, times) if start <= time < end and drive is not None]
    missing = sum(start <= time < end and drive is None for drive, time in zip(drives, times))
    values = np.asarray(selected, dtype=float) if selected else np.empty((0, 2))
    result = {"window_start_s": float(start), "window_end_s": float(end), "samples": len(selected),
              "missing_samples": int(missing)}
    for index, side in enumerate(("left", "right")):
        for name, function in (("mean", np.mean), ("std", np.std), ("min", np.min), ("max", np.max)):
            result[f"{side}_{name}"] = float(function(values[:, index])) if len(values) else None
    difference = values[:, 1] - values[:, 0] if len(values) else np.empty(0)
    result["right_minus_left_mean"] = float(np.mean(difference)) if len(difference) else None
    result["right_greater_fraction"] = float(np.mean(difference > 0)) if len(difference) else None
    return result


def _attenuation(receipt: dict, correction: dict) -> tuple[dict | None, list[dict]]:
    observation_motor = receipt.get("observation_motor")
    config = observation_motor.get("configuration") if isinstance(observation_motor, dict) else None
    if not isinstance(config, dict):
        return None, []
    required = ("upright_threshold", "tilt_gain", "angular_gain", "minimum_propulsion_fraction")
    if any(key not in config for key in required):
        return None, []
    parameters = {key: _finite(config[key], f"candidate motor parameter {key}") for key in required}
    factors = []
    for sample in correction["samples"]:
        upright, pitch = sample["upright_z"], sample["pitch_rate"]
        if upright is None or pitch is None:
            factors.append(None)
            continue
        tilt = min(1.0, max(0.0, parameters["upright_threshold"] - upright))
        factor = min(1.0, max(parameters["minimum_propulsion_fraction"],
                               1.0 - parameters["tilt_gain"] * tilt - .02 * abs(pitch)))
        factors.append(float(factor))
    periods = []
    start = None
    values = []
    for index, (sample, factor) in enumerate(zip(correction["samples"], factors)):
        attenuated = factor is not None and factor < 1.0 - 1e-12
        if attenuated and start is None:
            start = float(sample["time_s"])
            values = []
        if attenuated:
            values.append(factor)
        if (not attenuated or index == len(factors) - 1) and start is not None:
            end_index = index
            # The first non-attenuated sample is the left-hold boundary. If
            # the final sample is attenuated, hold through the next recorded
            # timestamp when one exists, otherwise through the final sample.
            end = float(correction["samples"][end_index]["time_s"])
            if attenuated and end_index + 1 < len(factors):
                end = float(correction["samples"][end_index + 1]["time_s"])
            periods.append({"start_s": start, "end_s": end, "duration_s": end - start,
                            "samples": len(values), "min_factor": min(values), "max_factor": max(values)})
            start = None
            values = []
    return {"source": "modelled from recorded correction inputs and candidate receipt configuration",
            "parameters": parameters,
            "factor_definition": "clip(1 - tilt_gain*clip(threshold-upright_z, 0, 1) - 0.02*abs(pitch_rate), minimum, 1)",
            "sample_factors": [{"time_s": sample["time_s"], "factor": factor}
                               for sample, factor in zip(correction["samples"], factors)]}, periods


def _context(times: np.ndarray, correction: dict, drives: list,
             wall_contacts: list[list[str] | None], inversion: dict | None) -> dict | None:
    if inversion is None:
        return None
    start = max(float(times[0]), inversion["start_s"] - 5.0)
    end = min(float(times[-1]), inversion["start_s"] + 1.0)
    samples = []
    for index, time in enumerate(times):
        if start <= time <= end:
            input_sample = correction["samples"][index]
            samples.append({"time_s": float(time), "offset_s": float(time - inversion["start_s"]),
                            "upright_z": input_sample["upright_z"],
                            "upright_z_source": input_sample["sources"]["upright_z"],
                            "roll_rate": input_sample["roll_rate"], "pitch_rate": input_sample["pitch_rate"],
                            "support_left": input_sample["support_left"],
                            "support_right": input_sample["support_right"],
                            "drives": list(drives[index]) if drives[index] is not None else None,
                            "wall_contact_objects": wall_contacts[index]})
    return {"window_start_s": start, "window_end_s": end,
            "window_definition": "first inversion +/-5 s before and +1 s after; recorded samples only",
            "samples": samples}


def _trajectory_divergence(arm_data: dict, threshold: float) -> dict:
    baseline, candidate = (arm_data[arm] for arm in ARMS)
    right_by_time = {round(float(time), 9): position
                     for time, position in zip(candidate["times"], candidate["positions"])
                     if position is not None}
    baseline_origin = baseline["positions"][0]
    candidate_origin = candidate["positions"][0]
    if baseline_origin is None or candidate_origin is None:
        return {"status": "unavailable", "reason": "one or both arms lack recorded XY positions",
                "threshold_mm": threshold, "first_exceedance_time_s": None}
    rows = []
    for time, position in zip(baseline["times"], baseline["positions"]):
        other = right_by_time.get(round(float(time), 9))
        if position is None or other is None:
            continue
        separation = float(np.linalg.norm((position - baseline_origin) - (other - candidate_origin)))
        rows.append({"time_s": float(time), "trajectory_separation_mm": separation})
    first = next((row["time_s"] for row in rows if row["trajectory_separation_mm"] >= threshold), None)
    return {"status": "measured_on_common_recorded_timestamps", "threshold_mm": threshold,
            "threshold_definition": "relative XY path separation >= threshold; no interpolation",
            "common_samples": len(rows), "first_exceedance_time_s": first,
            "max_separation_mm": max((row["trajectory_separation_mm"] for row in rows), default=None),
            "samples": rows}


def _arm_report(root: Path, slot: int, pose_index: int, drive_window: float) -> tuple[dict, dict]:
    receipt, verification = _verify_receipt(root)
    frames = _json(root / "frames.json")
    events = _json(root / "events.json")
    if not isinstance(frames, list) or not all(isinstance(frame, dict) for frame in frames):
        raise ValueError(f"{root}: frames.json must contain a list of objects")
    if not isinstance(events, list) or not all(isinstance(event, dict) for event in events):
        raise ValueError(f"{root}: events.json must contain a list of objects")
    dt = _physics_dt(receipt)
    times = _frame_times(frames, dt)
    correction = _correction_series(frames, times, slot, pose_index)
    upright = [sample["pose_upright_z"] for sample in correction["samples"]]
    inversions = _inversions(times, upright)
    drives = [_drive(frame, slot) for frame in frames]
    positions = _positions(frames, slot)
    wall_contacts = [_wall_objects(frame, slot) for frame in frames]
    first = inversions[0]["start_s"] if inversions else None
    wall_onsets = _wall_onsets(events, slot, dt, first)
    before_each = [_drive_stats(drives, times, max(float(times[0]), episode["start_s"] - drive_window), episode["start_s"])
                   for episode in inversions]
    attenuation_model, attenuation_periods = _attenuation(receipt, correction)
    return {"source": str(root), "receipt": verification, "recorded_frames": len(frames),
            "observed_seconds": float(times[-1] - times[0]), "times": times, "positions": positions,
            "inversions": inversions, "first_inversion_time_s": first,
            "correction_inputs": correction, "propulsion_attenuation": {
                "status": "available" if attenuation_model is not None else "unavailable",
                "periods": attenuation_periods, "model": attenuation_model},
            "drive_before_each_inversion": before_each,
            "wall_contact_onsets_preceding_first_inversion": wall_onsets,
            "first_inversion_context": _context(times, correction, drives, wall_contacts,
                                                 inversions[0] if inversions else None)}, {
        "receipt": receipt, "times": times, "positions": positions,
    }


def compare(seed_directory: Path, *, slot: int = 0, pose_index: int = 0,
            drive_window: float = 5.0, trajectory_threshold: float = 1.0) -> dict:
    if slot < 0 or pose_index < 0 or not math.isfinite(drive_window) or drive_window <= 0:
        raise ValueError("slot and pose_index must be nonnegative; drive window must be positive")
    if not math.isfinite(trajectory_threshold) or trajectory_threshold <= 0:
        raise ValueError("trajectory threshold must be positive")
    seed_match = re.search(r"seed-(\d+)", seed_directory.name)
    arm_data = {}
    internal = {}
    for arm in ARMS:
        report, values = _arm_report(_run_root(seed_directory, arm), slot, pose_index, drive_window)
        arm_data[arm] = report
        internal[arm] = values
        del report["times"]
        del report["positions"]
    return {"schema_version": "maze-phase2-arm-comparison/v1", "source": str(seed_directory),
            "seed": int(seed_match.group(1)) if seed_match else seed_directory.name, "arms": arm_data,
            "trajectory_divergence": _trajectory_divergence(internal, trajectory_threshold),
            "analysis_policy": {"recording_only": True, "pose_index": pose_index,
                "drive_window_s": drive_window,
                "inversion_definition": "first recorded thorax pose sample with initial-pose-relative upright_z < 0",
                "wall_onset_definition": "recorded wall_contact/environment_contact event before the first inversion; no proximity inference",
                "scientific_scope": "engineering-model replay evidence; no biological righting or causal claim"}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("seed_directory", type=Path, help="one phase-2 seed directory containing baseline/ and candidate/")
    parser.add_argument("--slot", type=int, default=0)
    parser.add_argument("--pose-index", type=int, default=0,
                        help="recorded poses[] index used as the thorax proxy when no direct quaternion field exists")
    parser.add_argument("--drive-window-s", type=float, default=5.0)
    parser.add_argument("--trajectory-threshold-mm", type=float, default=1.0)
    args = parser.parse_args()
    try:
        report = compare(args.seed_directory.resolve(), slot=args.slot, pose_index=args.pose_index,
                         drive_window=args.drive_window_s, trajectory_threshold=args.trajectory_threshold_mm)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
