import json
import importlib.util
from pathlib import Path

import pytest

_MODULE = importlib.util.spec_from_file_location(
    "analyze_maze_locomotion", Path(__file__).parents[1] / "scripts" / "analyze_maze_locomotion.py")
_ANALYSIS = importlib.util.module_from_spec(_MODULE)
assert _MODULE.loader is not None
_MODULE.loader.exec_module(_ANALYSIS)
analyze_replay = _ANALYSIS.analyze_replay


def _fixture(tmp_path):
    scene = {
        "task": {"goal_food": "food-0"},
        "food": [{"id": "food-0", "position": [4, 0, .15]}],
        "body": {"geoms": [{"id": 11, "slot": 0, "name": "fly-0/c_thorax"}]},
    }
    times = [0., 1., 2., 3., 4.]
    quaternions = [[1, 0, 0, 0], [1, 0, 0, 0], [0, 1, 0, 0], [0, 1, 0, 0], [1, 0, 0, 0]]
    frames = [{"time": time, "poses": [[0, 0, 1, *quat]], "positions": [[time, 0, 1]],
               "drives": [[.2 + time / 10, .4]]} for time, quat in zip(times, quaternions)]
    events = [{"type": "wall_contact", "tick": 10_000, "slot": 0},
              {"type": "food_contact", "tick": 30_000, "slot": 0, "food": ["food-0"]}]
    for name, value in (("scene.json", scene), ("frames.json", frames), ("events.json", events),
                        ("receipt.json", {"runtime": {"rules": {"physics_dt": .0001}}})):
        (tmp_path / name).write_text(json.dumps(value))
    return tmp_path


def test_analysis_reports_inversion_recovery_wall_goal_drive_and_coverage(tmp_path):
    report = analyze_replay(_fixture(tmp_path))
    assert report["upright_fraction"] == pytest.approx(.5)
    assert report["first_inversion_time_s"] == pytest.approx(2.)
    assert report["inversion_episodes"] == [{"start_s": 2., "end_s": 4., "duration_s": 2.,
                                             "recovered": True, "recovery_duration_s": 2.}]
    assert report["wall_contact_timeline"] == [{"start_s": 1., "end_s": 2., "duration_s": 1.}]
    assert report["left_right_drive_before_inversion"]["left_mean"] == pytest.approx(.25)
    assert report["left_right_drive_before_inversion"]["right_mean"] == pytest.approx(.4)
    assert report["goal_contact"] == {"food_id": "food-0", "first_contact_time_s": 3.,
                                      "contact_count": 1, "reached": True}
    assert report["coverage"]["unique_xy_cells"] == 5
    assert report["coverage"]["path_length_mm"] == pytest.approx(4.)


def test_analysis_keeps_missing_goal_as_null_and_unrecovered_episode(tmp_path):
    root = _fixture(tmp_path)
    frames = json.loads((root / "frames.json").read_text())
    frames[-1]["poses"][0][3:7] = [0, 1, 0, 0]
    (root / "frames.json").write_text(json.dumps(frames))
    events = [{"type": "wall_contact", "tick": 10_000, "slot": 0}]
    (root / "events.json").write_text(json.dumps(events))
    report = analyze_replay(root)
    assert report["goal_contact"]["first_contact_time_s"] is None
    assert report["goal_contact"]["reached"] is False
    assert report["inversion_episodes"][0]["recovered"] is False
    assert report["inversion_episodes"][0]["recovery_duration_s"] is None
