import importlib.util
import json
import tarfile
from pathlib import Path

import pytest

from flyarena.common import digest, file_sha
from flyarena.behavior import behavior_metrics

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
               "drives": [[.2 + time / 10, .4]],
               "senses": [{"contact_environment": ["obstacle-0"] if time == 1. else []}]}
              for time, quat in zip(times, quaternions)]
    events = [{"type": "wall_contact", "tick": 10_000, "slot": 0},
              {"type": "food_contact", "tick": 30_000, "slot": 0, "food": ["food-0"]}]
    for name, value in (("scene.json", scene), ("frames.json", frames), ("events.json", events),
                        ("receipt.json", {"runtime": {"rules": {"physics_dt": .0001}}})):
        (tmp_path / name).write_text(json.dumps(value))
    _seal(tmp_path)
    return tmp_path


def _seal(root):
    receipt = json.loads((root / "receipt.json").read_text())
    receipt["files"] = {f"{name}.json": file_sha(root / f"{name}.json") for name in ("scene", "frames", "events")}
    receipt["sha256"] = digest({k: v for k, v in receipt.items() if k != "sha256"})
    (root / "receipt.json").write_text(json.dumps(receipt))
    return receipt


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
    _seal(root)
    report = analyze_replay(root)
    assert report["goal_contact"]["first_contact_time_s"] is None
    assert report["goal_contact"]["reached"] is False
    assert report["inversion_episodes"][0]["recovered"] is False
    assert report["inversion_episodes"][0]["recovery_duration_s"] is None


def test_initial_mesh_orientation_matches_existing_behavior_metric(tmp_path):
    root = _fixture(tmp_path)
    frames = json.loads((root / "frames.json").read_text())
    # The mesh's local Z points downward even in its initial reference pose.
    for i, frame in enumerate(frames):
        frame["poses"][0][3:7] = [0, 1, 0, 0] if i < 2 else [1, 0, 0, 0]
    (root / "frames.json").write_text(json.dumps(frames))
    _seal(root)
    report = analyze_replay(root)
    expected = behavior_metrics(json.loads((root / "scene.json").read_text()), frames, [], 1, .0001)[0]
    assert report["upright_fraction"] == expected["upright_fraction"] == .5
    assert report["first_inversion_time_s"] == expected["first_inversion_s"] == 2.


@pytest.mark.parametrize("name", ["scene", "frames", "events", "receipt"])
def test_rejects_tampered_evidence(tmp_path, name):
    root = _fixture(tmp_path)
    path = root / f"{name}.json"
    value = json.loads(path.read_text())
    if isinstance(value, list):
        value.append({})
    else:
        value["tampered"] = True
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="mismatch"):
        analyze_replay(root)


def test_release_gallery_and_tar_verify_match_bindings(tmp_path):
    root = _fixture(tmp_path)
    receipt = json.loads((root / "receipt.json").read_text())
    receipt.update(request={"fly_ids": ["fly-0"]}, flies=[{"id": "fly-0", "artifact_id": "artifact-0"}])
    (root / "receipt.json").write_text(json.dumps(receipt))
    receipt = _seal(root)
    match = {"status": "verified", "request": receipt["request"], "participants": receipt["flies"],
             "result": {"receipt_sha256": receipt["sha256"]},
             "source": {"receipt_sha256": receipt["sha256"], "receipt_file_sha256": file_sha(root / "receipt.json")}}
    (root / "match.json").write_text(json.dumps(match))
    for path in root.glob("*.json"):
        path.rename(root / f"example-{path.name}")
    assert analyze_replay(root)["verification"]["match_metadata_checked"] is True
    archive_path = root / "release.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for path in root.glob("*.json"):
            archive.add(path, arcname=f"gallery/{path.name}")
    extracted, temporary = _ANALYSIS._source_root(archive_path)
    try:
        assert analyze_replay(extracted)["first_inversion_time_s"] == 2.
    finally:
        temporary.cleanup()
    match["source"]["receipt_file_sha256"] = "incorrect"
    (root / "example-match.json").write_text(json.dumps(match))
    with pytest.raises(ValueError, match="match metadata"):
        analyze_replay(root)


def test_contact_onsets_do_not_invent_durations_or_mix_slots(tmp_path):
    root = _fixture(tmp_path)
    frames = json.loads((root / "frames.json").read_text())
    for i, frame in enumerate(frames):
        frame["senses"] = [{"contact_environment": ["fly-1"]}, {"contact_environment": ["obstacle-9"]}]
        if i >= 3:
            frame["senses"][0]["contact_environment"] = ["obstacle-2"]
    (root / "frames.json").write_text(json.dumps(frames))
    _seal(root)
    report = analyze_replay(root)
    assert report["wall_contact_onsets"] == [{"time_s": 1., "objects": []}]
    assert report["wall_contact_timeline"] == [{"start_s": 3., "end_s": 4., "duration_s": 1.}]
    assert report["wall_contact_sampled_seconds"] == 1.
    for frame in frames:
        del frame["senses"]
    (root / "frames.json").write_text(json.dumps(frames))
    _seal(root)
    report = analyze_replay(root)
    assert report["wall_contact_timeline"] == []
    assert report["wall_contact_missing_samples"] == 5
    assert report["wall_contact_sampled_seconds"] is None


def test_window_clips_intervals_and_missing_drive_stays_missing(tmp_path):
    root = _fixture(tmp_path)
    frames = json.loads((root / "frames.json").read_text())
    for frame, time in zip(frames, [44., 45., 46., 64., 66.]):
        frame["time"] = time
        frame["senses"][0]["contact_environment"] = ["obstacle-0"]
    del frames[1]["drives"]
    (root / "frames.json").write_text(json.dumps(frames))
    _seal(root)
    report = analyze_replay(root)
    window = report["wall_contact_window_45_65_s"]
    assert window["sampled_intervals"] == [{"start_s": 45., "end_s": 65., "duration_s": 20.}]
    assert window["contact_samples"] == window["frames"] == 3
    assert report["left_right_drive_before_inversion"]["samples"] == 1
    assert report["left_right_drive_before_inversion"]["missing_samples"] == 1
    assert report["left_right_drive_before_inversion"]["left_mean"] == .2


@pytest.mark.parametrize("key", ["positions", "drives"])
def test_rejects_nonfinite_observations(tmp_path, key):
    root = _fixture(tmp_path)
    frames = json.loads((root / "frames.json").read_text())
    frames[1][key][0][0] = float("nan")
    (root / "frames.json").write_text(json.dumps(frames))
    _seal(root)
    with pytest.raises(ValueError, match="finite"):
        analyze_replay(root)
