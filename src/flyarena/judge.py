"""Independent admission of a trusted worker's evidence, never its winner field."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np

from .common import digest, file_sha
from .contracts import MatchRequest
from .scenarios import RULES, receipt_scene
from .replay import LEGACY_RECEIPTS, REPLAY_RECEIPT, validate_policy


def _replay_cadence(receipt: dict, stored_scene: dict) -> int:
    """Dispatch recorded versions using frozen identities, never today's source hash."""
    runtime = receipt["runtime"]
    rules = runtime.get("rules")
    if (not isinstance(rules, dict) or rules.keys() != RULES.keys() or
            any(type(rules[k]) is not type(v) or rules[k] != v for k, v in RULES.items())):
        raise ValueError("Incompatible frozen replay rules")
    version = receipt.get("schema")
    if version == REPLAY_RECEIPT:
        for container in (receipt, runtime, stored_scene):
            validate_policy(container.get("replay_policy"), rules)
        sources = (runtime.get("closure", {}).get("sources", {})
                   if receipt["request"].get("bridge_profile") == "sensorimotor-research-v2"
                   else runtime.get("sources", {}))
        source = sources.get("replay.py")
        if not isinstance(source, str) or re.fullmatch(r"[0-9a-f]{64}", source) is None:
            raise ValueError("Replay policy source is not bound to runtime")
        return receipt["replay_policy"]["pose_ticks"]
    if isinstance(version, str) and version in LEGACY_RECEIPTS:
        if any("replay_policy" in c for c in (receipt, runtime, stored_scene)):
            raise ValueError("Legacy receipt cannot declare replay policy")
        return rules["snapshot_ticks"]
    raise ValueError("Unknown receipt version")


def _finite_array(value, shape: tuple, name: str) -> np.ndarray:
    try:
        array = np.asarray(value)
        if array.shape != shape or array.dtype.kind not in "fiu" or not np.isfinite(array).all():
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError(f"Invalid replay {name} shape or non-finite data") from None
    return array


def _validate_frames(frames: list, scene: dict, end: int, cadence: int, n: int) -> None:
    ticks = list(range(0, end + 1, cadence))
    if ticks[-1] != end:
        ticks.append(end)
    if (not isinstance(frames, list) or any(not isinstance(f, dict) or
            type(f.get("tick")) is not int for f in frames) or
            [f["tick"] for f in frames] != ticks):
        raise ValueError("Replay is missing ticks or final state")
    geoms = scene.get("body", {}).get("geoms")
    if (not isinstance(geoms, list) or not geoms or any(not isinstance(g, dict) or
            type(g.get("id")) is not int or g["id"] < 0 or
            type(g.get("slot")) is not int or not 0 <= g["slot"] < n or
            g.get("mesh") not in scene["body"].get("meshes", {}) for g in geoms) or
            len({g["id"] for g in geoms}) != len(geoms)):
        raise ValueError("Invalid replay geometry manifest")
    for frame in frames:
        seconds = frame.get("time")
        if (type(seconds) not in (int, float) or not math.isfinite(seconds) or
                abs(seconds - frame["tick"] * RULES["physics_dt"]) > 1e-9):
            raise ValueError("Replay clock mismatch")
        for key, shape in (("poses", (len(geoms), 7)), ("positions", (n, 3)),
                           ("scores", (n,)), ("energy", (n,)),
                           ("food", (len(scene["food"]),)), ("drives", (n, 2))):
            values = _finite_array(frame.get(key), shape, key)
            if key == "poses" and not np.allclose(np.linalg.norm(values[:, 3:], axis=1),
                                                  1, rtol=0, atol=2e-6):
                raise ValueError("Invalid replay pose quaternion")


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
    # Check the recorded horizon against the immutable endpoint before applying
    # the public admission bounds.  An adversary can resign a receipt with a
    # longer horizon; reporting the truncated endpoint makes that evidence
    # failure explicit instead of hiding it behind Pydantic's range error.
    raw_request = receipt["request"]
    raw_duration = raw_request.get("duration_seconds") if isinstance(raw_request, dict) else None
    raw_end = receipt.get("final_tick")
    if (type(raw_duration) is int and raw_duration > 30 and type(raw_end) is int
            and raw_end != raw_duration * 10000):
        raise ValueError("Run ended before the required endpoint")
    request = MatchRequest.model_validate(raw_request)
    stored_scene = json.loads((folder / "scene.json").read_text())
    runtime_sensory = receipt["runtime"].get("sensory_profile", {"id": "odor-only-v1"})
    if runtime_sensory.get("id") != request.sensory_profile:
        raise ValueError("Receipt sensory profile mismatch")
    if request.sensory_profile in ("engineered-multimodal-v1", "engineered-multimodal-v2"):
        encoder = stored_scene.get("sensory_encoder", {})
        if encoder.get("profile") != runtime_sensory or not encoder.get("groups"):
            raise ValueError("Receipt sensory encoder manifest mismatch")
    pose_ticks = _replay_cadence(receipt, stored_scene)
    if expected_runtime_hash is not None and digest(receipt["runtime"]) != expected_runtime_hash:
        raise ValueError("Execution backend differs from admitted runtime")
    if expected_request is not None and request.model_dump() != MatchRequest.model_validate(expected_request).model_dump():
        raise ValueError("Run does not match the admitted request")
    if request.bridge_profile == "sensorimotor-research-v2":
        runtime = receipt["runtime"]
        if (receipt["schema"] not in ("run-receipt/v2", REPLAY_RECEIPT) or runtime.get("bridge_profile") != request.bridge_profile
            or runtime.get("actual_backend") != "cpu-numba"
            or runtime.get("profile", {}).get("id") != request.bridge_profile
            or receipt["readout_sha256"] != runtime["profile"]["hashes"]["readout_metadata"]):
            raise ValueError("Receipt bridge/backend/readout identity mismatch")
        # Compare frozen identities internally; historical evidence never requires today's sources.
        if digest(runtime["closure"]) != runtime["profile"]["hashes"]["runtime_closure"]:
            raise ValueError("Receipt scientific closure mismatch")
    artifacts = [f["artifact_id"] for f in receipt["flies"]]
    if expected_artifacts is not None and artifacts != expected_artifacts:
        raise ValueError("Run used different contestant artifacts")
    if receipt["silence_output"]:
        raise ValueError("Ablation runs cannot enter competition rankings")
    frames = json.loads((folder / "frames.json").read_text())
    events = json.loads((folder / "events.json").read_text())
    result = json.loads((folder / "result.json").read_text())
    scene = receipt_scene(request.map_id, request.seed, request.bridge_profile,
                          receipt["runtime"].get("sources", {}).get("scenarios.py"))
    if any(stored_scene.get(k) != v for k, v in scene.items()):
        raise ValueError("Scenario digest mismatch")
    end = receipt["final_tick"]
    if type(end) is not int or end <= 0 or end > request.duration_seconds * 10000 or end % RULES["sense_ticks"]:
        raise ValueError("Invalid simulation endpoint")
    for i in range(len(artifacts)):
        with np.load(folder / f"brain-{i}.npz", allow_pickle=False) as checkpoint:
            if int(checkpoint["tick"]) != end:
                raise ValueError("Neural and physical clocks differ")
            if not all(np.isfinite(checkpoint[k]).all() for k in checkpoint.files):
                raise ValueError("Invalid neural checkpoint")
    if type(result["final_tick"]) is not int or result["final_tick"] != end:
        raise ValueError("Replay is missing ticks or final state")
    _validate_frames(frames, stored_scene, end, pose_ticks, len(artifacts))
    if request.sensory_profile in ("engineered-multimodal-v1", "engineered-multimodal-v2"):
        encoder_sha = digest(stored_scene["sensory_encoder"])
        for frame in frames[1:]:
            senses = frame.get("senses", [])
            if len(senses) != len(artifacts):
                raise ValueError("Missing neural input observations")
            for sense in senses:
                encoded = sense.get("neural_input", {})
                if (sense.get("sensory_profile") != request.sensory_profile or
                        encoded.get("profile") != request.sensory_profile or
                        encoded.get("group_manifest_sha256") != encoder_sha):
                    raise ValueError("Recorded neural input identity mismatch")
                values = encoded.get("values", {})
                channels = ("odor_left", "odor_right", "visual_left", "visual_right", "touch")
                currents = _finite_array([values.get(k) for k in channels], (5,), "neural input")
                if np.any(currents < 0) or np.any(currents > 1):
                    raise ValueError("Recorded neural input outside [0,1]")
                if request.sensory_profile == "engineered-multimodal-v2":
                    contacts = sense.get("contact_environment")
                    targets = {f"obstacle-{i}" for i in range(len(scene["obstacles"]))}
                    targets.update(f"fly-{i}" for i in range(len(artifacts)))
                    if (not isinstance(contacts, list) or
                            any(not isinstance(c, str) or c not in targets for c in contacts) or
                            sense["touch"] != float(bool(sense.get("contact_food") or contacts))):
                        raise ValueError("Environmental touch differs from contact observations")
                if not np.array_equal(currents[2:], [*sense["visual"], sense["touch"]]):
                    raise ValueError("Neural input differs from embodied observations")
    n, nf = len(artifacts), len(scene["food"])
    environment_targets = {f"obstacle-{i}" for i in range(len(scene["obstacles"]))}
    environment_targets.update(f"fly-{i}" for i in range(n))
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
        elif event["type"] in {"odor_detected", "visual_target_detected"}:
            slot, values = event.get("slot"), event.get("values")
            if not isinstance(slot, int) or not 0 <= slot < n or not isinstance(values, list) or len(values) != 2:
                raise ValueError("Invalid sensory detection event")
            if not all(isinstance(value, (int, float)) and math.isfinite(value) and value >= 0 for value in values):
                raise ValueError("Invalid sensory detection values")
        elif event["type"] == "environment_contact":
            slot, objects = event.get("slot"), event.get("objects")
            if (request.sensory_profile != "engineered-multimodal-v2" or
                    not isinstance(slot, int) or not 0 <= slot < n or
                    not isinstance(objects, list) or not objects or
                    any(not isinstance(obj, str) or obj not in environment_targets or obj == f"fly-{slot}"
                        for obj in objects)):
                raise ValueError("Invalid environment contact event")
        elif event["type"] == "food_contact":
            slot, distance = event.get("slot"), event.get("mouth_distance")
            if (not isinstance(slot, int) or not 0 <= slot < n or
                    not isinstance(distance, (int, float)) or not math.isfinite(distance) or distance < 0):
                raise ValueError("Invalid food contact event")
        else:
            raise ValueError("Unknown event type")
    initial = np.array([f["initial"] for f in scene["food"]])
    # New runner results expose the event clocks explicitly.  Validate them
    # against the immutable ledger when present, while accepting older
    # receipts that only had the fly-to-fly ``contact_ticks`` counter.
    if "food_contact_ticks" in result:
        expected_food_contacts = [[] for _ in range(n)]
        for event in events:
            if event["type"] == "food_contact":
                expected_food_contacts[event["slot"]].append(event["tick"])
        if result["food_contact_ticks"] != expected_food_contacts:
            raise ValueError("Food contact history differs from event ledger")
    if "intake_ticks" in result:
        expected_intakes = [[] for _ in range(n)]
        for event in events:
            if event["type"] == "intake":
                expected_intakes[event["slot"]].append(event["tick"])
        if result["intake_ticks"] != expected_intakes:
            raise ValueError("Intake history differs from event ledger")
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
