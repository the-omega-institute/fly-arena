"""Independent admission of a trusted worker's evidence, never its winner field."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from .common import digest, file_sha
from .contracts import MatchRequest
from .scenarios import RULES, scenario


def verify(folder: Path, *, expected_request: dict | None = None,
           expected_artifacts: list[str] | None = None, expected_runtime_hash: str | None = None) -> dict:
    receipt = json.loads((folder / "receipt.json").read_text())
    if digest({k: v for k, v in receipt.items() if k != "sha256"}) != receipt["sha256"]:
        raise ValueError("Receipt digest mismatch")
    required = {"scene.json", "frames.json", "events.json", "result.json", "physics.npz"}
    required |= {f"brain-{i}.npz" for i in range(len(receipt["flies"]))}
    if set(receipt["files"]) != required:
        raise ValueError("Incomplete or unexpected evidence manifest")
    for name, sha in receipt["files"].items():
        if Path(name).name != name or file_sha(folder / name) != sha:
            raise ValueError(f"Evidence hash mismatch: {name}")
    request = MatchRequest.model_validate(receipt["request"])
    if expected_runtime_hash is not None and digest(receipt["runtime"]) != expected_runtime_hash:
        raise ValueError("Execution backend differs from admitted runtime")
    if expected_request is not None and request.model_dump() != expected_request:
        raise ValueError("Run does not match the admitted request")
    artifacts = [f["artifact_id"] for f in receipt["flies"]]
    if expected_artifacts is not None and artifacts != expected_artifacts:
        raise ValueError("Run used different contestant artifacts")
    if receipt["silence_output"]:
        raise ValueError("Ablation runs cannot enter competition rankings")
    frames = json.loads((folder / "frames.json").read_text())
    events = json.loads((folder / "events.json").read_text())
    result = json.loads((folder / "result.json").read_text())
    scene = scenario(request.map_id, request.seed)
    stored_scene = json.loads((folder / "scene.json").read_text())
    if any(stored_scene.get(k) != v for k, v in scene.items()):
        raise ValueError("Scenario digest mismatch")
    end = receipt["final_tick"]
    for i in range(len(artifacts)):
        with np.load(folder / f"brain-{i}.npz", allow_pickle=False) as checkpoint:
            if int(checkpoint["tick"]) != end:
                raise ValueError("Neural and physical clocks differ")
            if not all(np.isfinite(checkpoint[k]).all() for k in checkpoint.files):
                raise ValueError("Invalid neural checkpoint")
    if end <= 0 or end > request.duration_seconds * 10000 or end % RULES["sense_ticks"]:
        raise ValueError("Invalid simulation endpoint")
    ticks = list(range(0, end + 1, RULES["snapshot_ticks"]))
    if ticks[-1] != end:
        ticks.append(end)
    if [f["tick"] for f in frames] != ticks or result["final_tick"] != end:
        raise ValueError("Replay is missing ticks or final state")
    for frame in frames:
        if abs(frame["time"] - frame["tick"] * RULES["physics_dt"]) > 1e-9:
            raise ValueError("Replay clock mismatch")
        for key in ["poses", "positions", "scores", "energy", "food", "drives"]:
            if not np.isfinite(np.asarray(frame[key])).all():
                raise ValueError("Non-finite replay data")
    n, nf = len(artifacts), len(scene["food"])
    scores, eaten = np.zeros(n), np.zeros(nf)
    exits = [None] * n
    prior_tick = 0
    seen_intake = set()
    for event in events:
        tick = event["tick"]
        if type(tick) is not int or not prior_tick <= tick <= end:
            raise ValueError("Event ordering or tick invalid")
        prior_tick = tick
        if event["type"] == "intake":
            slot, food, amount = event["slot"], event["food"], event["amount"]
            if request.mode == "sumo" or not (0 <= slot < n and 0 <= food < nf) or not math.isfinite(amount) or amount <= 0:
                raise ValueError("Invalid intake event")
            key = (tick, slot, food)
            if key in seen_intake:
                raise ValueError("Duplicate intake event")
            seen_intake.add(key)
            if amount > RULES["food_intake_per_second"] * .05 + 1e-8:
                raise ValueError("Intake rate exceeded")
            scores[slot] += amount
            eaten[food] += amount
        elif event["type"] == "exit":
            slot = event["slot"]
            if not 0 <= slot < n or exits[slot] is not None:
                raise ValueError("Invalid/duplicate exit event")
            exits[slot] = tick
        elif event["type"] == "contact":
            if n != 2 or event["slots"] != [0, 1]:
                raise ValueError("Invalid contact event")
        else:
            raise ValueError("Unknown event type")
    initial = np.array([f["initial"] for f in scene["food"]])
    if np.any(eaten > initial + 1e-7) or not np.allclose(initial - eaten, result["food_remaining"], atol=1e-7):
        raise ValueError("Food conservation failed")
    if not np.allclose(scores, result["scores"], atol=1e-7) or not np.allclose(scores, frames[-1]["scores"], atol=1e-5):
        raise ValueError("Event-derived score differs from result")
    if exits != result["exit_ticks"]:
        raise ValueError("Exit history differs from result")
    expected_end = request.duration_seconds * 10000
    first_exit = min((v for v in exits if v is not None), default=None)
    if request.mode == "sumo" and first_exit is not None:
        expected_end = ((first_exit + RULES["sense_ticks"] - 1) // RULES["sense_ticks"]) * RULES["sense_ticks"]
    if end != expected_end:
        raise ValueError("Run ended before the required endpoint")
    with np.load(folder / "physics.npz", allow_pickle=False) as checkpoint:
        if int(checkpoint["tick"]) != end or not all(np.isfinite(checkpoint[k]).all() for k in checkpoint.files):
            raise ValueError("Invalid physical checkpoint")
    if request.mode == "sumo":
        first = min((v for v in exits if v is not None), default=None)
        losers = [i for i, v in enumerate(exits) if v == first] if first is not None else []
        winner = 1 - losers[0] if len(losers) == 1 else None
    elif n == 1:
        winner = None
    else:
        winner = int(np.argmax(scores)) if abs(scores[0] - scores[1]) > 1e-6 else None
    return {"status": "verified", "winner_slot": winner, "scores": scores.round(6).tolist(),
            "outcome": "solo" if n == 1 else "draw" if winner is None else "win",
            "receipt_sha256": receipt["sha256"], "final_tick": end,
            "judge": "event-conservation-v1"}
