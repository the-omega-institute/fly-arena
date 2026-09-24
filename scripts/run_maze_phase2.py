#!/usr/bin/env python3
"""Isolated, serialized issue-82 observations using the real match runner.

No public queue, Store, leaderboard, DB writes, calibration or steering. A
--dry-run is a real short simulation of both motors, never fabricated evidence.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import math
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time
import traceback
import uuid

from flyarena.common import DATA, VAR, digest, file_sha, write_json
from flyarena.contracts import MatchRequest
from flyarena.experiments.motor import MOTOR, RECOVERY_MOTOR, profile_identity
from flyarena.replay import LONG_POLICY

WT = "0c136a17a43c84c2eb32539454285783"
SEEDS = (42, 43, 44, 45, 46)
HORIZON = 180
BRIDGE = "sensorimotor-research-v2"
SENSORY = "engineered-kernel-contact-v1"
ARMS = ("baseline", "candidate")
SCHEMA = "maze-phase2/v1"


def read(path):
    return json.loads(Path(path).read_text())


def request_for(seed, horizon):
    return MatchRequest(fly_ids=[WT], map_id="labyrinth", mode="forage", sandbox=True,
                        bridge_profile=BRIDGE, sensory_profile=SENSORY,
                        duration_seconds=horizon, seed=seed)


def valid_metrics(run, horizon):
    if not run or run.get("status") != "complete":
        return False
    m = run.get("metrics", {})
    try:
        u, d, v, latency = (m[k] for k in ("upright_fraction", "inversion_duration_s",
                                           "coverage_cells", "first_inversion_time_s"))
        return (m["observed_seconds"] == horizon and all(math.isfinite(x) for x in (u, d, v))
                and 0 <= u <= 1 and 0 <= d <= horizon and v >= 1
                and ((latency is None and m["first_inversion_right_censored"] is True)
                     or (latency is not None and math.isfinite(latency) and 0 <= latency <= horizon
                         and m["first_inversion_right_censored"] is False)))
    except (KeyError, TypeError, ValueError):
        return False


def decision_rule(pairs, *, horizon=HORIZON, seeds=SEEDS, protocol_violations=()):
    """Pure preregistered joint rule, in the documented precedence order.

    Missing/invalid evidence is never a tie. Censored latency stays None; the
    comparison operates on the censor flags, without numeric sentinels.
    """
    rows = []
    violations = list(protocol_violations)
    for seed in seeds:
        pair = pairs.get(seed, {})
        b, c = pair.get("baseline"), pair.get("candidate")
        for arm, run in (("baseline", b), ("candidate", c)):
            violations.extend(f"seed {seed} {arm}: {v}" for v in (run or {}).get("protocol_violations", []))
        row = {"seed": seed, "classification": "incomplete", "comparisons": {}, "adverse_metrics": []}
        if (valid_metrics(b, horizon) and valid_metrics(c, horizon)
                and b.get("pair_binding") != c.get("pair_binding")):
            row.update(classification="invalid", adverse_metrics=["pair source/scene binding mismatch"])
        elif valid_metrics(b, horizon) and valid_metrics(c, horizon):
            bm, cm = b["metrics"], c["metrics"]
            for key, higher in (("upright_fraction", True), ("inversion_duration_s", False), ("coverage_cells", True)):
                delta = cm[key] - bm[key]
                row["comparisons"][key] = {"baseline": bm[key], "candidate": cm[key], "delta": delta,
                    "outcome": "tie" if delta == 0 else "improved" if (delta > 0) == higher else "worsened"}
            bl, cl = bm["first_inversion_time_s"], cm["first_inversion_time_s"]
            if bl is None or cl is None:
                outcome = "tie" if bl is None and cl is None else "improved" if cl is None else "worsened"
            else:
                outcome = "tie" if cl == bl else "improved" if cl > bl else "worsened"
            row["comparisons"]["first_inversion"] = {
                "baseline": bl, "candidate": cl, "baseline_right_censored": bl is None,
                "candidate_right_censored": cl is None, "outcome": outcome,
                "delta": cl - bl if cl is not None and bl is not None else None}
            row["adverse_metrics"] = [k for k, v in row["comparisons"].items() if v["outcome"] == "worsened"]
            row["classification"] = ("negative" if row["adverse_metrics"] else "improved"
                if row["comparisons"]["upright_fraction"]["outcome"] == "improved" else "null")
        elif valid_metrics(b, horizon) and c and c.get("status") in {"failed", "timed_out", "incomplete"}:
            row.update(classification="negative", adverse_metrics=["candidate-only failure"])
        rows.append(row)
    # Violating runs cannot be counted as improvements, even in an invalid study.
    if violations:
        for row in rows:
            if row["classification"] == "improved":
                row["classification"] = "invalid"
    counts = {kind: sum(r["classification"] == kind for r in rows)
              for kind in ("improved", "null", "negative", "incomplete", "invalid")}
    preregistered = horizon == HORIZON and len(seeds) == 5 and set(seeds) == set(SEEDS)
    if not preregistered:
        verdict, reason = None, "not the preregistered protocol"
    elif violations:
        verdict, reason = "null", "protocol violation"
    elif counts["negative"]:
        verdict, reason = "negative", "negative seed"
    elif counts["incomplete"] or counts["invalid"]:
        verdict, reason = "null", "incomplete"
    elif counts["improved"] >= 4:
        verdict, reason = "improvement", "at least four jointly improved seeds and no negative seed"
    else:
        verdict, reason = "null", "fewer than four jointly improved seeds"
    return {"verdict": verdict, "reason": reason, "preregistered": preregistered,
            "counts": counts, "seeds": rows, "protocol_violations": violations}


def load_wt(var):
    """Read an existing subject, without constructing Store or modifying SQLite."""
    db_path = (var / "arena.sqlite3").resolve()
    with sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT id,name,color,artifact_id,spec,report FROM flies WHERE id=?", (WT,)).fetchone()
    if row is None:
        raise ValueError(f"Frozen WT {WT} is missing from {db_path}")
    fly = dict(row)
    for key in ("spec", "report"):
        fly[key] = json.loads(fly[key])
    spec = fly["spec"]
    if (fly["report"]["budget_used"] != 0 or spec.get("edge_deltas") or spec.get("weight_mutations")
            or spec.get("interventions") or spec.get("plasticity") != "none"
            or spec.get("neuron_parameters") != {"tau_scale": 1., "threshold_shift_mv": 0.}):
        raise ValueError("Frozen WT has non-reference modifications")
    return fly


def selection(arm):
    profile = MOTOR["id"] if arm == "baseline" else RECOVERY_MOTOR["id"]
    return {"schema": "maze-phase2-motor-selection/v1", "arm": arm,
            "profile_id": profile, "identity": profile_identity(profile),
            "admission": "observation", "override": arm == "candidate"}


def seal(value):
    return {**value, "sha256": digest(value)}


def check_seal(value):
    if value.get("sha256") != digest({k: v for k, v in value.items() if k != "sha256"}):
        raise ValueError("manifest canonical digest mismatch")


def verify_run(folder, manifest):
    """Verify all receipt files and bindings before analysis or resume skipping."""
    from analyze_maze_locomotion import analyze_replay
    from flyarena.runner import observation_motor_manifest
    replay = folder / "replay"
    receipt = read(replay / "receipt.json")
    check_seal(receipt)
    required = {"scene.json", "frames.json", "events.json", "result.json", "physics.npz", "brain-0.npz"}
    if not required <= receipt.get("files", {}).keys():
        raise ValueError("receipt is missing full-run evidence")
    for name, expected in receipt["files"].items():
        if Path(name).name != name or file_sha(replay / name) != expected:
            raise ValueError(f"receipt file hash mismatch: {name}")
    expected_fly = {k: manifest["fly"][k] for k in ("id", "name", "color", "artifact_id")}
    if (receipt["request"] != manifest["request"] or receipt["flies"] != [expected_fly]
            or receipt["runtime"] != manifest["runtime"] or receipt["silence_output"] is not False
            or receipt["replay_policy"] != LONG_POLICY):
        raise ValueError("receipt request, subject, runtime or recording policy mismatch")
    hashes = manifest["runtime"].get("profile", {}).get("hashes", {})
    if hashes and (receipt["readout_sha256"] != hashes["readout_metadata"]
                   or receipt["connectome_sha256"] != hashes["connectome"]):
        raise ValueError("receipt readout/connectome binding mismatch")
    arm = manifest["motor_selection"]["arm"]
    if manifest["motor_selection"] != selection(arm):
        raise ValueError("motor identity changed")
    expected_motor = observation_motor_manifest(RECOVERY_MOTOR["id"]) if arm == "candidate" else None
    if receipt.get("observation_motor") != expected_motor:
        raise ValueError("receipt motor selection mismatch")
    horizon = manifest["request"]["duration_seconds"]
    frames, scene, result = (read(replay / f"{name}.json") for name in ("frames", "scene", "result"))
    if (receipt["final_tick"] != horizon * 10000 or result["final_tick"] != horizon * 10000
            or [f["tick"] for f in frames] != list(range(0, horizon * 10000 + 1, 500))
            or any(f["time"] != f["tick"] / 10000 for f in frames)
            or scene["replay_policy"] != LONG_POLICY):
        raise ValueError("incomplete or non-20Hz recording")
    for frame in frames:
        if any(not math.isfinite(v) or not 0 <= v <= 1.5 for drive in frame["drives"] for v in drive):
            raise ValueError("Protocol violation: unbounded recorded drive")
    analysis = analyze_replay(replay)
    metrics = {"observed_seconds": analysis["observed_seconds"], "upright_fraction": analysis["upright_fraction"],
               "first_inversion_time_s": analysis["first_inversion_time_s"],
               "first_inversion_right_censored": analysis["first_inversion_time_s"] is None,
               "inversion_duration_s": sum(e["duration_s"] for e in analysis["inversion_episodes"]),
               "coverage_cells": analysis["coverage"]["unique_xy_cells"]}
    analysis["phase2_censoring"] = {
        "first_inversion_right_censored": metrics["first_inversion_right_censored"],
        "goal_contact_right_censored": analysis["goal_contact"]["first_contact_time_s"] is None,
        "observation_end_s": horizon,
        "episode_recovery_right_censored": [not e["recovered"] for e in analysis["inversion_episodes"]]}
    write_json(folder / "analysis.json", analysis)
    return {"status": "complete", "metrics": metrics, "receipt_sha256": receipt["sha256"],
            "receipt_file_sha256": file_sha(replay / "receipt.json"),
            "scene_sha256": receipt["files"]["scene.json"], "analysis": analysis,
            "pair_binding": digest({"request": receipt["request"], "flies": receipt["flies"],
                                    "runtime": receipt["runtime"], "scene": receipt["files"]["scene.json"]}),
            "protocol_violations": [], "timing": receipt["timing"]}


def failure(status, error):
    return {"status": status, "error": error,
            **({"protocol_violations": [error]} if "Protocol violation:" in error else {})}


def worker(folder):
    """One real runner invocation. Journals survive failure, timeout and SIGKILL."""
    from flyarena.runner import runtime_manifest, simulate
    manifest = read(folder / "manifest.json")
    check_seal(manifest)
    data, var = Path(manifest["data"]), Path(manifest["var"])
    if runtime_manifest(data, BRIDGE, SENSORY) != manifest["runtime"]:
        raise ValueError("Runtime changed after study was frozen")
    def interrupted(signum, _frame):
        raise TimeoutError(f"observation worker interrupted by signal {signum}")
    signal.signal(signal.SIGTERM, interrupted)
    event_count = 0
    with (folder / "partial-frames.jsonl").open("x") as frames, (folder / "partial-events.jsonl").open("x") as events:
        def record(frame, all_events):
            nonlocal event_count
            frames.write(json.dumps(frame, allow_nan=False) + "\n")
            frames.flush()
            for event in all_events[event_count:]:
                events.write(json.dumps(event, allow_nan=False) + "\n")
            events.flush()
            event_count = len(all_events)
        try:
            simulate(MatchRequest.model_validate(manifest["request"]), [manifest["fly"]], folder / "replay",
                     data=data, var=var, observation_20hz=True, observation_record=record,
                     observation_motor_profile=RECOVERY_MOTOR["id"] if manifest["motor_selection"]["override"] else None)
        except BaseException as exc:
            write_json(folder / "error.json", {"error": f"{type(exc).__name__}: {exc}",
                                               "traceback": traceback.format_exc()})
            raise


def execute(folder, manifest, timeout, lock_fd=None):
    """Existing attempts are never rerun or overwritten, including failed ones."""
    if folder.exists():
        try:
            saved = read(folder / "manifest.json")
            check_seal(saved)
            if saved != manifest:
                raise ValueError("attempt manifest differs from frozen study")
            if (folder / "outcome.json").is_file() and read(folder / "outcome.json")["status"] != "complete":
                return {**read(folder / "outcome.json"), "resumed": True}
            if (folder / "replay/receipt.json").is_file():
                verified = verify_run(folder, manifest)
                if (folder / "outcome.json").is_file():
                    saved_outcome = read(folder / "outcome.json")
                    if saved_outcome.get("receipt_sha256") != verified["receipt_sha256"]:
                        raise ValueError("completed receipt differs from original outcome")
                return verified
            return {"status": "incomplete", "error": "Interrupted attempt without a complete receipt; preserved, not retried"}
        except Exception as exc:
            return failure("invalid", f"{type(exc).__name__}: {exc}")
    folder.mkdir(parents=True)
    write_json(folder / "manifest.json", manifest)
    start = time.perf_counter()
    status, error = None, None
    interrupted = False
    with (folder / "worker.log").open("x") as log:
        try:
            child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--worker", str(folder)],
                                     stdout=log, stderr=subprocess.STDOUT,
                                     pass_fds=() if lock_fd is None else (lock_fd,))
        except OSError as exc:
            outcome = failure("failed", f"{type(exc).__name__}: {exc}")
            outcome["measured_wall_seconds"] = time.perf_counter() - start
            write_json(folder / "outcome.json", outcome)
            return outcome
        try:
            code = child.wait(timeout=timeout)
            if code:
                status, error = "failed", f"worker exited {code}; see worker.log"
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
            child.terminate()
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
            status = "timed_out" if isinstance(exc, subprocess.TimeoutExpired) else "incomplete"
            interrupted = isinstance(exc, KeyboardInterrupt)
            error = f"{type(exc).__name__}: worker stopped; partial journals preserved"
    if status is None:
        try:
            outcome = verify_run(folder, manifest)
        except Exception as exc:
            outcome = failure("invalid", f"{type(exc).__name__}: {exc}")
    else:
        outcome = {"status": status, "error": error}
    if (folder / "error.json").is_file():
        outcome["worker_error"] = read(folder / "error.json")
        if "Protocol violation:" in outcome["worker_error"]["error"]:
            outcome["protocol_violations"] = [outcome["worker_error"]["error"]]
    outcome["measured_wall_seconds"] = time.perf_counter() - start
    if interrupted:
        outcome["interrupted"] = True
    write_json(folder / "outcome.json", outcome)
    return outcome


def paired_diagnostics(pair):
    b, c = (pair.get(arm, {}).get("analysis") for arm in ARMS)
    if not b or not c:
        return None
    def delta(x, y):
        return y - x if x is not None and y is not None else None
    drive = "left_right_drive_before_inversion"
    return {"inversion_episode_count": len(c["inversion_episodes"]) - len(b["inversion_episodes"]),
            "wall_contact_onset_count": len(c["wall_contact_onsets"]) - len(b["wall_contact_onsets"]),
            "wall_contact_sampled_seconds": delta(b["wall_contact_sampled_seconds"], c["wall_contact_sampled_seconds"]),
            "xy_path_length_mm": delta(b["coverage"]["path_length_mm"], c["coverage"]["path_length_mm"]),
            "drive_before_inversion": {k: delta(b[drive][k], c[drive][k]) for k in b[drive]},
            "goal_contact_time_s": delta(b["goal_contact"]["first_contact_time_s"], c["goal_contact"]["first_contact_time_s"]),
            "individual_recoveries": "Reported per run; episodes are not matched across runs"}


def write_report(output, study, pairs, errors=()):
    decision = decision_rule(pairs, horizon=study["horizon"], seeds=study["seeds"])
    report = {"schema": SCHEMA, "study_sha256": study["sha256"], "study": study,
              "decision": decision, "runs": pairs, "errors": list(errors),
              "paired_diagnostics": {seed: paired_diagnostics(pair) for seed, pair in pairs.items()},
              "limitations": "Recorded simulations of engineering body, neural and motor models; no biological righting or competition claim."}
    write_json(output / "paired-report.json", report)
    lines = ["# Issue #82 phase-2 paired observations", "",
             f"Decision: {decision['verdict'] or 'NO VERDICT'} / {decision['reason']}", "",
             f"Study digest: `{study['sha256']}`", "", report["limitations"], "",
             "Null inversion/goal times below are right-censored only for complete recordings.", "",
             "| Seed | Arm | Status | Upright fraction | First inversion (s) | Inverted burden (s) | Cells | Goal contact (s) | Pair |",
             "|---:|---|---|---:|---|---:|---:|---|---|"]
    def latency(value):
        return "null (right-censored)" if value is None else str(value)
    for row in decision["seeds"]:
        for arm in ARMS:
            run = pairs.get(row["seed"], {}).get(arm, {})
            m = run.get("metrics", {})
            a = run.get("analysis", {})
            lines.append(f"| {row['seed']} | {arm} | {run.get('status', 'missing')} | {m.get('upright_fraction', '—')} | "
                         f"{latency(m['first_inversion_time_s']) if m else '—'} | {m.get('inversion_duration_s', '—')} | "
                         f"{m.get('coverage_cells', '—')} | {latency(a['goal_contact']['first_contact_time_s']) if a else '—'} | {row['classification']} |")
    for row in decision["seeds"]:
        lines.extend(["", f"Seed {row['seed']} comparisons: `{json.dumps(row['comparisons'], sort_keys=True)}`. "
                      f"Adverse metrics: {', '.join(row['adverse_metrics']) or 'none measured'}.", ""])
    lines.extend(["", f"Counts: `{json.dumps(decision['counts'], sort_keys=True)}`", "",
                  "Full per-run episodes/recovery censoring, contact onsets and durations, drive mean/spread, XY path and paired differences: `paired-report.json`."])
    for error in errors:
        lines.extend(["", f"Error: {error}"])
    for seed, pair in pairs.items():
        for arm, run in pair.items():
            if run.get("error"):
                lines.extend(["", f"Seed {seed} {arm}: {run['error']}"])
    (output / "paired-report.md").write_text("\n".join(lines) + "\n")
    return decision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="real 2-second seed-42 pair by default; no protocol verdict")
    parser.add_argument("--horizon", type=int)
    parser.add_argument("--seeds", type=int, nargs="+")
    parser.add_argument("--output", type=Path, help="existing directory resumes without replacing attempts")
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--var", type=Path, default=VAR, help="read-only source of WT database and compiled artifact")
    parser.add_argument("--timeout", type=float, help="optional per-run wall-clock seconds; timeouts remain evidence")
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        try:
            worker(args.worker)
        except BaseException as exc:
            if not (args.worker / "error.json").exists():
                write_json(args.worker / "error.json", {"error": f"{type(exc).__name__}: {exc}",
                                                        "traceback": traceback.format_exc()})
            raise
        return 0
    def interrupted(_signum, _frame):
        raise KeyboardInterrupt("harness terminated")
    signal.signal(signal.SIGTERM, interrupted)
    horizon = args.horizon if args.horizon is not None else 2 if args.dry_run else HORIZON
    seeds = args.seeds if args.seeds is not None else [42] if args.dry_run else list(SEEDS)
    if (not 1 <= horizon <= 300 or len(set(seeds)) != len(seeds)
            or any(not 0 <= seed < 2**31 for seed in seeds)
            or (args.timeout is not None and (not math.isfinite(args.timeout) or args.timeout <= 0))):
        parser.error("use distinct int32 seeds, horizon 1–300, and a positive finite timeout")
    if args.dry_run and horizon == HORIZON and set(seeds) == set(SEEDS):
        parser.error("--dry-run must use a non-protocol horizon or seed set")
    output = (args.output or Path("var/research/issue82-phase2") / uuid.uuid4().hex).resolve()
    output.mkdir(parents=True, exist_ok=True)
    with (output / ".lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error("another harness owns this output directory")
        study = {"schema": SCHEMA, "horizon": horizon, "seeds": seeds,
                 "data": str(args.data.resolve()), "var": str(args.var.resolve()),
                 "harness_sha256": file_sha(Path(__file__)), "timeout_seconds": args.timeout,
                 "analyzer_sha256": file_sha(Path(__file__).with_name("analyze_maze_locomotion.py")),
                 "recording_policy": dict(LONG_POLICY), "motor_selections": {arm: selection(arm) for arm in ARMS}}
        pairs = {}
        started = time.perf_counter()
        try:
            from flyarena.runner import runtime_manifest
            study.update(fly=load_wt(args.var), runtime=runtime_manifest(args.data, BRIDGE, SENSORY))
            study = seal(study)
            if (output / "study.json").exists():
                if read(output / "study.json") != study:
                    raise ValueError("Frozen study differs: use its original runtime/arguments or a new output directory")
            else:
                write_json(output / "study.json", study)
        except Exception as exc:
            # Never overwrite an existing study/report on a mismatched resume.
            error = f"{type(exc).__name__}: {exc}"
            write_json(output / f"preflight-error-{uuid.uuid4().hex}.json", {"error": error})
            if not (output / "study.json").exists():
                study = seal(study)
                write_report(output, study, pairs, [error])
            print(f"Preflight failed: {error}\nEvidence: {output}", flush=True)
            return 1
        print(f"Evidence: {output}", flush=True)
        estimated = False
        for seed in seeds:
            pairs[seed] = {}
            for arm in ARMS:
                folder = output / f"seed-{seed}" / arm
                manifest = seal({"schema": "maze-phase2-run/v1", "study_sha256": study["sha256"],
                    "data": study["data"], "var": study["var"], "fly": study["fly"], "runtime": study["runtime"],
                    "request": request_for(seed, horizon).model_dump(), "motor_selection": selection(arm)})
                print(f"Seed {seed} {arm}: {manifest['motor_selection']['profile_id']}", flush=True)
                # Keep the lock alive in the worker even if the parent is SIGKILLed.
                outcome = execute(folder, manifest, args.timeout, lock.fileno())
                pairs[seed][arm] = {**outcome, "folder": str(folder), "manifest_sha256": manifest["sha256"],
                                    "motor_selection": manifest["motor_selection"]}
                if outcome["status"] == "complete" and not estimated:
                    seconds = outcome.get("measured_wall_seconds", outcome["timing"]["wall_seconds"])
                    remaining = len(seeds) * 2 - sum(len(p) for p in pairs.values())
                    print(f"Runtime estimate after first completed run: {seconds:.2f} wall s / {horizon} simulated s; "
                          f"remaining scheduled runs ~{remaining * seconds:.1f} s; full 10×180 s study ~{seconds / horizon * 1800:.1f} s. "
                          "Linear estimate only; startup/compilation and behavior affect cost.", flush=True)
                    estimated = True
                print(f"Seed {seed} {arm}: {outcome['status']}", flush=True)
                write_report(output, study, pairs)
                if outcome.get("interrupted") and not outcome.get("resumed"):
                    return 130
        decision = write_report(output, study, pairs)
        elapsed = time.perf_counter() - started
        write_json(output / f"invocation-{uuid.uuid4().hex}.json", {"wall_seconds": elapsed, "decision": decision})
        print(f"Measured invocation wall time: {elapsed:.2f} s\nDecision: {decision['verdict']} / {decision['reason']}", flush=True)
        return 0 if all(r["status"] == "complete" for p in pairs.values() for r in p.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
