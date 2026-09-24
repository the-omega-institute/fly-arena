"""Synthetic decision/receipt fixtures; no invented observations used as evidence."""
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest

from flyarena.common import file_sha, write_json
from flyarena.replay import LONG_POLICY

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("run_maze_phase2", SCRIPTS / "run_maze_phase2.py")
p2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p2)


def complete(u=.5, latency=20., burden=90., cells=100, horizon=180):
    return {"status": "complete", "metrics": {"upright_fraction": u,
        "first_inversion_time_s": latency, "first_inversion_right_censored": latency is None,
        "inversion_duration_s": burden, "coverage_cells": cells, "observed_seconds": horizon}}


def pairs():
    return {seed: {"baseline": complete(), "candidate": complete(.75, 40., 45., 101)} for seed in p2.SEEDS}


def test_four_improved_and_fifth_tie_pass_but_three_do_not():
    runs = pairs()
    runs[46]["candidate"] = complete()
    result = p2.decision_rule(runs)
    assert result["verdict"] == "improvement"
    assert result["counts"]["improved"] == 4 and result["counts"]["null"] == 1
    runs[45]["candidate"] = complete()
    assert p2.decision_rule(runs)["verdict"] == "null"


@pytest.mark.parametrize("latencies,outcome", [((20., None), "improved"), ((None, None), "tie"),
    ((None, 180.), "worsened"), ((20., 20.), "tie"), ((20., 19.), "worsened"), ((20., 21.), "improved")])
def test_latency_censoring_and_endpoint_are_not_numeric_sentinels(latencies, outcome):
    runs = pairs()
    for arm, latency in zip(p2.ARMS, latencies):
        runs[42][arm]["metrics"]["first_inversion_time_s"] = latency
        runs[42][arm]["metrics"]["first_inversion_right_censored"] = latency is None
    comparison = p2.decision_rule(runs)["seeds"][0]["comparisons"]["first_inversion"]
    assert comparison["outcome"] == outcome
    assert comparison["baseline"] == latencies[0] and comparison["candidate"] == latencies[1]
    if None in latencies:
        assert comparison["delta"] is None


def test_two_inversion_free_runs_are_null_and_goal_is_descriptive():
    runs = {seed: {arm: complete(1., None, 0.) for arm in p2.ARMS} for seed in p2.SEEDS}
    runs[42]["candidate"]["goal_contact"] = None
    result = p2.decision_rule(runs)
    assert result["verdict"] == "null" and result["counts"]["null"] == 5


@pytest.mark.parametrize("key,value", [("upright_fraction", .4), ("first_inversion_time_s", 19.),
                                       ("inversion_duration_s", 91.), ("coverage_cells", 99)])
def test_negative_fifth_seed_overrides_four_improvements(key, value):
    runs = pairs()
    runs[46]["candidate"]["metrics"][key] = value
    result = p2.decision_rule(runs)
    assert result["verdict"] == "negative" and result["counts"]["improved"] == 4
    assert result["seeds"][-1]["adverse_metrics"]


@pytest.mark.parametrize("status", ["failed", "timed_out", "incomplete"])
def test_candidate_only_failure_is_negative(status):
    runs = pairs()
    runs[46]["candidate"] = {"status": status}
    result = p2.decision_rule(runs)
    assert result["verdict"] == "negative"
    assert result["seeds"][-1]["adverse_metrics"] == ["candidate-only failure"]


@pytest.mark.parametrize("change", ["missing_seed", "missing_arm", "baseline_failed", "both_failed",
                                   "invalid", "truncated", "false_censor", "nan"])
def test_missing_or_invalid_evidence_is_incomplete_not_a_tie(change):
    runs = pairs()
    if change == "missing_seed":
        del runs[46]
    elif change == "missing_arm":
        del runs[46]["candidate"]
    elif change == "baseline_failed":
        runs[46]["baseline"] = {"status": "failed"}
    elif change == "both_failed":
        runs[46] = {arm: {"status": "failed"} for arm in p2.ARMS}
    elif change == "invalid":
        runs[46]["candidate"] = {"status": "invalid"}
    else:
        m = runs[46]["candidate"]["metrics"]
        m[{"truncated": "observed_seconds", "false_censor": "first_inversion_time_s", "nan": "upright_fraction"}[change]] = {
            "truncated": 179., "false_censor": None, "nan": float("nan")}[change]
    result = p2.decision_rule(runs)
    assert (result["verdict"], result["reason"]) == ("null", "incomplete")
    assert result["counts"]["null"] == 0


def test_precedence_protocol_violation_then_negative_then_incomplete():
    runs = pairs()
    del runs[45]
    runs[46]["candidate"] = {"status": "failed", "protocol_violations": ["unbounded drive"]}
    result = p2.decision_rule(runs)
    assert (result["verdict"], result["reason"]) == ("null", "protocol violation")
    assert result["counts"]["improved"] == 0
    del runs[46]["candidate"]["protocol_violations"]
    assert p2.decision_rule(runs)["verdict"] == "negative"
    assert p2.decision_rule(runs, protocol_violations=["pose intervention"])["reason"] == "protocol violation"


@pytest.mark.parametrize("horizon,seeds", [(2, [42]), (180, [42]), (179, p2.SEEDS), (180, [42, 43, 44, 45, 45])])
def test_nonprotocol_studies_never_receive_a_verdict(horizon, seeds):
    result = p2.decision_rule(pairs(), horizon=horizon, seeds=seeds)
    assert result["verdict"] is None and result["reason"] == "not the preregistered protocol"


def test_strict_unrounded_upright_improvement_and_partial_favorable_null():
    runs = pairs()
    runs[42]["candidate"] = complete(.5 + 1e-15, 20., 90., 100)
    assert p2.decision_rule(runs)["seeds"][0]["classification"] == "improved"
    runs[42]["candidate"] = complete(.5, 21., 89., 101)
    assert p2.decision_rule(runs)["seeds"][0]["classification"] == "null"


def fixture_run(folder, arm="baseline"):
    """Explicit tiny replay fixture, with all receipt-bound files present."""
    from flyarena.runner import observation_motor_manifest
    fly = {"id": p2.WT, "name": "synthetic fixture", "color": "mint", "artifact_id": "a" * 64}
    manifest = p2.seal({"request": p2.request_for(42, 2).model_dump(), "fly": fly,
                        "runtime": {}, "motor_selection": p2.selection(arm)})
    replay = folder / "replay"
    replay.mkdir(parents=True)
    scene = {"body": {"geoms": [{"slot": 0, "name": "fly-0/c_thorax"}]}, "replay_policy": LONG_POLICY}
    frames = [{"tick": tick, "time": tick / 10000, "poses": [[0, 0, 1, 1, 0, 0, 0]],
               "positions": [[0, 0, 1]], "drives": [[0., 0.]], "senses": [{"contact_environment": []}]}
              for tick in range(0, 20001, 500)]
    for name, value in (("scene", scene), ("frames", frames), ("events", []), ("result", {"final_tick": 20000})):
        write_json(replay / f"{name}.json", value)
    for name in ("brain-0.npz", "physics.npz"):
        np.savez(replay / name, fixture=np.array([1]))
    receipt = {"request": manifest["request"], "flies": [fly], "runtime": {}, "silence_output": False,
               "replay_policy": LONG_POLICY, "final_tick": 20000, "timing": {"wall_seconds": .1},
               "files": {p.name: file_sha(p) for p in replay.iterdir()}}
    if arm == "candidate":
        receipt["observation_motor"] = observation_motor_manifest(p2.RECOVERY_MOTOR["id"])
    write_json(replay / "receipt.json", p2.seal(receipt))
    write_json(folder / "manifest.json", manifest)
    return manifest


@pytest.mark.parametrize("arm", p2.ARMS)
def test_verified_receipts_resume_without_launching_worker(tmp_path, monkeypatch, arm):
    folder = tmp_path / "run"
    manifest = fixture_run(folder, arm)
    monkeypatch.setattr(p2.subprocess, "Popen", lambda *a, **k: pytest.fail("completed run was restarted"))
    before = file_sha(folder / "replay/receipt.json")
    outcome = p2.execute(folder, manifest, None)
    assert outcome["status"] == "complete"
    assert outcome["metrics"]["first_inversion_time_s"] is None
    assert outcome["analysis"]["phase2_censoring"]["first_inversion_right_censored"] is True
    assert file_sha(folder / "replay/receipt.json") == before


@pytest.mark.parametrize("target", ["frames.json", "brain-0.npz", "physics.npz", "receipt.json"])
def test_tampered_completed_evidence_is_preserved_and_not_skipped_as_valid(tmp_path, monkeypatch, target):
    folder = tmp_path / "run"
    manifest = fixture_run(folder)
    path = folder / "replay" / target
    path.write_bytes(path.read_bytes() + b"tamper")
    monkeypatch.setattr(p2.subprocess, "Popen", lambda *a, **k: pytest.fail("invalid run was replaced"))
    outcome = p2.execute(folder, manifest, None)
    assert outcome["status"] == "invalid" and outcome["error"]
    assert path.read_bytes().endswith(b"tamper")


@pytest.mark.parametrize("status", ["failed", "timed_out", "incomplete"])
def test_failed_attempt_is_never_silently_replaced(tmp_path, monkeypatch, status):
    folder = tmp_path / "run"
    manifest = fixture_run(folder)
    outcome = {"status": status, "error": "synthetic failure"}
    write_json(folder / "outcome.json", outcome)
    monkeypatch.setattr(p2.subprocess, "Popen", lambda *a, **k: pytest.fail("failed run was replaced"))
    assert p2.execute(folder, manifest, None) == {**outcome, "resumed": True}


def test_receipt_motor_override_is_required_only_for_candidate(tmp_path):
    folder = tmp_path / "run"
    manifest = fixture_run(folder, "candidate")
    receipt = p2.read(folder / "replay/receipt.json")
    del receipt["observation_motor"]
    del receipt["sha256"]
    write_json(folder / "replay/receipt.json", p2.seal(receipt))
    with pytest.raises(ValueError, match="motor selection"):
        p2.verify_run(folder, manifest)


def test_recovery_state_reads_local_rates_and_filters_real_contacts(monkeypatch):
    from types import SimpleNamespace
    from flyarena import runner
    def contact(a, b, z=1., height=0., dist=0.):
        return SimpleNamespace(geom1=a, geom2=b, frame=[0., 0., z], pos=[0., 0., height], dist=dist)
    body = SimpleNamespace(body_ids=[0], model=None, geom_slots={1: 0, 2: 0, 3: 0, 4: 0, 9: 1}, food_geom_ids={"food": 8},
        data=SimpleNamespace(xpos=np.array([[0., 0., 1.]]), xmat=np.eye(3).reshape(1, 9),
            contact=[contact(0, 1), contact(0, 1), contact(2, 0, -1.), contact(0, 3, height=2.),
                     contact(8, 1), contact(9, 1), contact(0, 4), contact(0, 3, dist=.1)]))
    monkeypatch.setattr(runner.mujoco, "mj_id2name", lambda _m, _t, i: {1: "fly-0/lf_tarsus1", 2: "fly-0/rh_tarsus5",
                                                                                  3: "fly-0/lm_tarsus1", 4: "fly-0/c_thorax"}[i])
    def velocity(_m, _d, _t, _id, out, local):
        assert local == 1
        out[:] = [2., -3., 4., 5., 6., 7.]
    monkeypatch.setattr(runner.mujoco, "mj_objectVelocity", velocity)
    assert runner.recovery_body_state(body, 0) == {"upright_z": 1., "roll_rate": 2., "pitch_rate": -3.,
                                                  "support_left": 1 / 3, "support_right": 1 / 3}


def test_pair_binding_mismatch_cannot_be_improved():
    runs = pairs()
    runs[42]["baseline"]["pair_binding"] = "one scene/runtime"
    runs[42]["candidate"]["pair_binding"] = "another scene/runtime"
    result = p2.decision_rule(runs)
    assert result["reason"] == "incomplete" and result["counts"]["invalid"] == 1


def test_unbounded_recording_is_a_protocol_violation_even_on_resume(tmp_path):
    folder = tmp_path / "run"
    manifest = fixture_run(folder)
    path = folder / "replay/frames.json"
    frames = p2.read(path)
    frames[1]["drives"] = [[1.6, 0.]]
    write_json(path, frames)
    receipt = p2.read(folder / "replay/receipt.json")
    receipt["files"]["frames.json"] = file_sha(path)
    del receipt["sha256"]
    write_json(folder / "replay/receipt.json", p2.seal(receipt))
    outcome = p2.execute(folder, manifest, None)
    assert outcome["status"] == "invalid" and outcome["protocol_violations"]


def test_timeout_preserves_partial_evidence_and_worker_error(tmp_path, monkeypatch):
    folder = tmp_path / "timeout"
    class Process:
        stopped = False
        def __init__(self, *args, **kwargs):
            write_json(folder / "error.json", {"error": "TimeoutError: stopped", "traceback": "fixture"})
            (folder / "partial-frames.jsonl").write_text('{"tick":0}\n')
        def wait(self, timeout=None):
            if not self.stopped:
                raise p2.subprocess.TimeoutExpired("fixture", timeout)
            return -15
        def terminate(self):
            self.stopped = True
    monkeypatch.setattr(p2.subprocess, "Popen", Process)
    outcome = p2.execute(folder, p2.seal({"fixture": True}), .01)
    assert outcome["status"] == "timed_out" and outcome["worker_error"]["error"] == "TimeoutError: stopped"
    assert (folder / "partial-frames.jsonl").read_text() == '{"tick":0}\n'
    assert p2.read(folder / "outcome.json") == outcome


def test_report_retains_unrecovered_episode_burden_and_null_latency(tmp_path):
    folder = tmp_path / "run"
    manifest = fixture_run(folder)
    path = folder / "replay/frames.json"
    frames = p2.read(path)
    for frame in frames[20:]:
        frame["poses"][0][3:7] = [0, 1, 0, 0]
    write_json(path, frames)
    receipt = p2.read(folder / "replay/receipt.json")
    receipt["files"]["frames.json"] = file_sha(path)
    del receipt["sha256"]
    write_json(folder / "replay/receipt.json", p2.seal(receipt))
    outcome = p2.verify_run(folder, manifest)
    assert outcome["metrics"]["inversion_duration_s"] == 1.
    episode = outcome["analysis"]["inversion_episodes"][0]
    assert episode["recovery_duration_s"] is None and episode["duration_s"] == 1.
    assert outcome["analysis"]["phase2_censoring"]["episode_recovery_right_censored"] == [True]


def test_spawn_failure_is_durable_and_study_lock_is_inherited(tmp_path, monkeypatch):
    def unavailable(*args, **kwargs):
        assert kwargs["pass_fds"] == (17,)
        raise OSError("synthetic process launch failure")
    monkeypatch.setattr(p2.subprocess, "Popen", unavailable)
    folder = tmp_path / "failed-spawn"
    outcome = p2.execute(folder, p2.seal({"fixture": True}), None, lock_fd=17)
    assert outcome["status"] == "failed" and "process launch failure" in outcome["error"]
    assert p2.read(folder / "outcome.json") == outcome
