import importlib.util
import json
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest


_MODULE = importlib.util.spec_from_file_location(
    "compare_phase2_arms", Path(__file__).parents[1] / "scripts" / "compare_phase2_arms.py")
_COMPARE = importlib.util.module_from_spec(_MODULE)
assert _MODULE.loader is not None
_MODULE.loader.exec_module(_COMPARE)


def _digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                        allow_nan=False).encode()
    return sha256(encoded).hexdigest()


def _write_json(path, value):
    path.write_text(json.dumps(value, separators=(",", ":"), allow_nan=False))


def _fixture(tmp_path):
    seed = tmp_path / "seed-42"
    times = list(range(7))
    baseline_quaternions = [[1, 0, 0, 0], [1, 0, 0, 0], [1, 0, 0, 0],
                            [0, 1, 0, 0], [0, 1, 0, 0], [1, 0, 0, 0], [1, 0, 0, 0]]
    candidate_quaternions = [[1, 0, 0, 0], [1, 0, 0, 0], [0, 1, 0, 0],
                             [0, 1, 0, 0], [1, 0, 0, 0], [1, 0, 0, 0], [1, 0, 0, 0]]

    def frames(quaternions, offset, body_state=None, missing_sense=False):
        rows = []
        for index, (time, quaternion) in enumerate(zip(times, quaternions)):
            sense = {} if missing_sense else {"contact_environment": ["obstacle-0"] if time == 1 else []}
            if body_state is not None:
                sense["motor_body_state"] = body_state[index]
            rows.append({"time": float(time), "quaternions": [quaternion],
                         "positions": [[float(time + offset), float(time * (0.3 if offset else 0.0)), 1.0]],
                         "drives": [[0.1 + time / 10, 0.4 - time / 20]], "senses": [sense]})
        return rows

    candidate_state = [
        {"upright_z": 1.0, "roll_rate": 0.0, "pitch_rate": 0.0, "support_left": .33, "support_right": .33},
        {"upright_z": .8, "roll_rate": .1, "pitch_rate": .2, "support_left": .33, "support_right": .67},
        {"upright_z": .1, "roll_rate": .2, "pitch_rate": .5, "support_left": 0.0, "support_right": .33},
        {"upright_z": -.5, "roll_rate": .3, "pitch_rate": .5, "support_left": 0.0, "support_right": 0.0},
        {"upright_z": 1.0, "roll_rate": 0.0, "pitch_rate": .1, "support_left": .33, "support_right": .33},
        {"upright_z": 1.0, "roll_rate": 0.0, "pitch_rate": 0.0, "support_left": .33, "support_right": .33},
        {"upright_z": 1.0, "roll_rate": 0.0, "pitch_rate": 0.0, "support_left": .33, "support_right": .33},
    ]
    events = [{"type": "environment_contact", "time": 1.0, "slot": 0, "objects": ["obstacle-0"]},
              {"type": "environment_contact", "time": 4.0, "slot": 0, "objects": ["obstacle-1"]}]
    config = {"upright_threshold": .35, "tilt_gain": .35, "angular_gain": .08,
              "minimum_propulsion_fraction": .2}
    for arm, quaternion_data, offset, state in (
            ("baseline", baseline_quaternions, 0.0, None), ("candidate", candidate_quaternions, .1, candidate_state)):
        root = seed / arm
        root.mkdir(parents=True)
        frame_data = frames(quaternion_data, offset, state, missing_sense=arm == "baseline")
        _write_json(root / "frames.json", frame_data)
        _write_json(root / "events.json", events)
        receipt = {"runtime": {"rules": {"physics_dt": .0001}},
                   "files": {"frames.json": _COMPARE._file_sha(root / "frames.json"),
                             "events.json": _COMPARE._file_sha(root / "events.json")}}
        if arm == "candidate":
            receipt["observation_motor"] = {"configuration": config}
        receipt["sha256"] = _digest(receipt)
        _write_json(root / "receipt.json", receipt)
    return seed


def test_compare_reports_recorded_candidate_inputs_and_proxy_baseline(tmp_path):
    report = _COMPARE.compare(_fixture(tmp_path))
    candidate = report["arms"]["candidate"]
    baseline = report["arms"]["baseline"]
    assert candidate["correction_inputs"]["samples"][1]["sources"]["roll_rate"] == "recorded_motor_body_state"
    assert baseline["correction_inputs"]["samples"][1]["sources"]["upright_z"] == "pose_derived_proxy"
    assert baseline["correction_inputs"]["samples"][1]["sources"]["support_left"] == "unavailable"
    assert candidate["correction_inputs"]["availability"]["upright_z"]["recorded"] == 7


def test_compare_reports_attenuation_wall_onsets_context_and_divergence(tmp_path):
    report = _COMPARE.compare(_fixture(tmp_path), trajectory_threshold=.2)
    candidate = report["arms"]["candidate"]
    assert candidate["propulsion_attenuation"]["status"] == "available"
    periods = candidate["propulsion_attenuation"]["periods"]
    assert periods[0]["start_s"] == pytest.approx(1.0)
    assert periods[0]["end_s"] == pytest.approx(5.0)
    onsets = candidate["wall_contact_onsets_preceding_first_inversion"]
    assert len(onsets) == 1
    assert onsets[0]["time_s"] == pytest.approx(1.0)
    assert onsets[0]["objects"] == ["obstacle-0"]
    assert onsets[0]["event_type"] == "environment_contact"
    assert candidate["first_inversion_context"]["window_start_s"] == pytest.approx(0.0)
    assert candidate["first_inversion_context"]["window_end_s"] == pytest.approx(3.0)
    assert report["trajectory_divergence"]["first_exceedance_time_s"] == pytest.approx(1.0)


def test_compare_reports_each_inversion_drive_window(tmp_path):
    report = _COMPARE.compare(_fixture(tmp_path), drive_window=2.0)
    baseline = report["arms"]["baseline"]
    candidate = report["arms"]["candidate"]
    assert len(baseline["inversions"]) == 1
    assert len(candidate["inversions"]) == 1
    assert baseline["drive_before_each_inversion"][0]["window_start_s"] == pytest.approx(1.0)
    assert candidate["drive_before_each_inversion"][0]["window_end_s"] == pytest.approx(2.0)
    assert candidate["first_inversion_context"]["samples"][-1]["offset_s"] == pytest.approx(1.0)


def test_compare_rejects_tampered_recorded_frame(tmp_path):
    seed = _fixture(tmp_path)
    path = seed / "candidate" / "frames.json"
    frames = json.loads(path.read_text())
    frames[0]["positions"][0][0] = 99
    path.write_text(json.dumps(frames))
    with pytest.raises(ValueError, match="hash mismatch"):
        _COMPARE.compare(seed)


def test_cli_prints_a_json_report(tmp_path):
    seed = _fixture(tmp_path)
    result = subprocess.run([sys.executable, str(Path(_COMPARE.__file__)), str(seed)],
                            capture_output=True, text=True, check=True)
    report = json.loads(result.stdout)
    assert report["schema_version"] == "maze-phase2-arm-comparison/v1"
    assert report["seed"] == 42
