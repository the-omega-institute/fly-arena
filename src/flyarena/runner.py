from __future__ import annotations

import json
import platform
import time
from pathlib import Path
from typing import Callable

import mujoco
import numpy as np

from .body import Bodies
from .common import DATA, ROOT, VAR, digest, file_sha, write_json
from .compiler import Compiler
from .connectome import Connectome
from .contracts import MatchRequest
from .neural import Brain, PROFILE
from .models import PROFILES, make_brain, require_model_bridge
from .scenarios import RULES, arena_scene
from .replay import POLICY, REPLAY_RECEIPT


def runtime_manifest(data: Path = DATA, bridge_profile: str = "legacy-v1",
                     sensory_profile: str = "odor-only-v1") -> dict:
    from .experiments.embodied_sensor import PROFILE as MULTIMODAL_PROFILE, validate_profile
    validate_profile(bridge_profile, sensory_profile)
    sensory = {"id": sensory_profile}
    if sensory_profile == MULTIMODAL_PROFILE["id"]:
        sensory = dict(MULTIMODAL_PROFILE)
    if bridge_profile == "sensorimotor-research-v2":
        from .experiments.probes import profile_manifest, runtime_closure
        profile = profile_manifest(data)
        if not profile["ready"]:
            raise ValueError(f"Research bridge unavailable: {profile.get('reason')}")
        return {"schema": "arena-runtime/v2", "bridge_profile": bridge_profile,
                "profile": profile, "closure": runtime_closure(), "rules": RULES,
                "replay_policy": dict(POLICY),
                "scene_version": "arena-offaxis-v2", "actual_backend": "cpu-numba",
                "sensory_profile": sensory,
                "sensors": {"olfaction": "analytic_bilateral_v2",
                             "vision": "raycast_engineered_observation_v1",
                             "touch": "mujoco_food_contact_observation_v1"}}
    if bridge_profile != "legacy-v1":
        raise ValueError("Unknown arena bridge profile")
    files = ["body.py", "runner.py", "neural.py", "scenarios.py", "judge.py", "compiler.py", "contracts.py", "replay.py", "models.py", "rate.py", "experiments/embodied_sensor.py"]
    return {"sources": {name: file_sha(ROOT / "src/flyarena" / name) for name in files
                        if (ROOT / "src/flyarena" / name).exists()},
            "lock_sha256": file_sha(ROOT / "uv.lock"), "model": PROFILE, "models": PROFILES, "rules": RULES,
            "replay_policy": dict(POLICY),
            "sensory_profile": sensory,
            "sensors": {"olfaction": "analytic_bilateral_v1",
                        "vision": "raycast_engineered_observation_v1",
                        "touch": "mujoco_food_contact_observation_v1"},
            "connectome_sha256": json.loads((data / "connectome/manifest.json").read_text())["sha256"],
            "readout_weights_sha256": file_sha(data / "connectome/readout.npz"),
            "mujoco": mujoco.__version__, "python": platform.python_version(),
            "platform": platform.platform(), "machine": platform.machine()}


def simulate(request: MatchRequest, flies: list[dict], output: Path,
             progress: Callable[[float], None] | None = None, *, silence_output: bool = False,
             data: Path = DATA, var: Path = VAR) -> dict:
    start = time.perf_counter()
    output.mkdir(parents=True, exist_ok=True)
    if any(p.name != "worker.log" for p in output.iterdir()):
        raise FileExistsError("Arena evidence directory must be empty; immutable run")
    v2 = request.bridge_profile == "sensorimotor-research-v2"
    frozen_runtime = runtime_manifest(data, request.bridge_profile, request.sensory_profile)
    graph = Connectome(data, verify=True)
    compiler = Compiler(graph)
    sensory_encoder = None
    if request.sensory_profile == "engineered-multimodal-v1":
        from .experiments.embodied_sensor import EmbodiedSensor
        sensory_encoder = EmbodiedSensor(graph)
    readout, ro = None, None
    if not v2:
        readout = json.loads((data / "connectome/readout.json").read_text())
        if (readout["connectome_sha256"] != graph.manifest["sha256"] or
            readout["neural_profile_sha256"] != digest(PROFILE) or
            readout["readout_sha256"] != file_sha(data / "connectome/readout.npz")):
            raise ValueError("Frozen motor readout is incompatible or corrupted")
        ro = np.load(data / "connectome/readout.npz", allow_pickle=False)
    brains = []
    for fly in flies:
        weights, artifact = compiler.load_weights(fly["artifact_id"], var)
        params = artifact["phenotype"]["neuron_parameters"]
        model_id=artifact['phenotype']['model']['id']
        if fly.get('spec',{}).get('model_profile',model_id)!=model_id:raise ValueError('Fly and artifact model mismatch')
        require_model_bridge(model_id,request.bridge_profile)
        brains.append(make_brain(model_id,graph,weights,params))
    backends, motors = [], []
    decoder = None
    if v2:
        from .backend import CPUBrainBackend, V2_IDS, CAPABILITIES
        from .experiments.decoder import Decoder
        from .experiments.sensor import encode_odor
        from .experiments.motor import MotorTransfer
        decoder = Decoder(data / "connectome/research-v2/readout.npz")
        readout = json.loads((data / "connectome/research-v2/readout.json").read_text())
        for brain in brains:
            backend = CPUBrainBackend(brain)
            backend.prepare(V2_IDS | {"capabilities": sorted(CAPABILITIES)})
            backend.reset(request.seed)
            backends.append(backend)
            motors.append(MotorTransfer())
    scene = arena_scene(request.map_id, request.seed, request.bridge_profile)
    scene["replay_policy"] = dict(POLICY)
    if sensory_encoder:
        scene["sensory_encoder"] = sensory_encoder.manifest
    bodies = Bodies(scene, len(flies), request.seed)
    scene["body"] = bodies.rendering_manifest()
    scene["flies"] = [{k: f[k] for k in ["id", "name", "color", "artifact_id"]} for f in flies]
    write_json(output / "scene.json", scene)
    remaining = np.array([f["initial"] for f in scene["food"]])
    food_xy = np.array([f["position"][:2] for f in scene["food"]])
    scores = np.zeros(len(flies))
    energy = np.full(len(flies), 100.)
    drives = np.zeros((len(flies), 2))
    eliminated = np.zeros(len(flies), dtype=bool)
    exit_ticks = [None for _ in flies]
    frames, events = [], []
    senses = [{"odor": [0.0, 0.0], "visual": [0.0, 0.0], "visual_status": "raycast_engineered_observation",
               "touch": 0.0, "touch_status": "mujoco_food_contact_observation_v1", "contact_food": [],
               "nearest_food": None, "mouth_distance": None,
               "sensory_profile": request.sensory_profile} for _ in flies]
    sensory_latches = [{"odor": False, "visual": False, "touch": False} for _ in flies]
    contact_ticks = 0
    # These are food-contact observations, kept separate from ``contact_ticks``
    # which counts fly-to-fly physical contact in sumo/contest matches.  Store
    # the event ticks in the result as well as events.json so API consumers do
    # not have to guess which contact a legacy field meant.
    food_contact_ticks = [[] for _ in flies]
    intake_ticks = [[] for _ in flies]
    last_contact = False
    duration_ticks = request.duration_seconds * 10000
    consumption = np.zeros((len(flies), len(remaining)))

    # Choose display nodes once per run.  The simulation still runs the complete
    # connectome; this fixed, labelled sample keeps the brain view comparable
    # from frame to frame and makes a missing value different from zero activity.
    sample_nodes = []
    for circuit in graph.manifest.get("circuits", []):
        circuit_id = circuit["id"]
        group = np.asarray(graph.groups.get(circuit_id, []), dtype=np.int64)
        if len(group):
            # The browser's canonical neuron endpoint exposes the first
            # ``limit`` members of each group.  Keep the fixed replay sample
            # inside that same deterministic window so recorded activity can
            # always be joined to the real metadata and local edge display.
            sample_nodes.extend(group[:min(6, len(group))].tolist())
    if not sample_nodes:
        sample_nodes = np.linspace(0, graph.n - 1, min(48, graph.n), dtype=int).tolist()
    sample_nodes = list(dict.fromkeys(int(i) for i in sample_nodes))[:48]

    def neural_sample(brain):
        rates = np.asarray(brain.rates)
        sampled = [{"id": str(int(graph.ids[i])), "activity": float(rates[i])}
                   for i in sample_nodes]
        return {"circuits": brain.trace(), "sampled_nodes": sampled,
                # Keep the old field for clients that still read v0.4.2 data.
                "top_nodes": sampled,
                "sampling": {"kind": "fixed-circuit-sample", "count": len(sampled)}}

    def snapshot():
        frame = bodies.snapshot()
        frame.update(scores=scores.round(6).tolist(), energy=energy.round(4).tolist(),
                     food=remaining.round(6).tolist(), drives=drives.round(4).tolist(),
                     traces=[b.trace() for b in brains],
                     brain=[neural_sample(b) for b in brains],
                     senses=[dict(s, odor=list(s["odor"]), visual=list(s["visual"])) for s in senses],
                     eliminated=eliminated.tolist())
        frames.append(frame)

    snapshot()
    simulation_started = time.perf_counter()
    for block in range(duration_ticks // RULES["sense_ticks"]):
        for slot, brain in enumerate(brains):
            antennae = bodies.antennae(slot)
            sources = food_xy
            strength = remaining / 10
            if request.mode == "sumo":
                sources = np.array([bodies.pose(j)[0][:2] for j in range(len(flies)) if j != slot])
                strength = np.ones(len(sources))
            odor = []
            for antenna in antennae:
                distance2 = np.sum((sources - antenna[:2]) ** 2, axis=1)
                raw = float(np.sum(strength * np.exp(-distance2 / (2 * RULES["odor_sigma_mm"]**2))))
                odor.append(raw if v2 else float(np.clip(raw, 0, 1)))
            position, rotation = bodies.pose(slot)
            nearest = None
            for source, amount_at_source in zip(food_xy, strength):
                delta = source - position[:2]
                distance = float(np.linalg.norm(delta))
                nearest = distance if nearest is None else min(nearest, distance)
            visual = [0.0, 0.0] if request.mode == "sumo" else bodies.visual_food(slot, remaining)
            mouth = bodies.mouth(slot)
            mouth_distance = float(np.min(np.linalg.norm(food_xy - mouth[:2], axis=1))) if len(food_xy) else None
            contact_food = [] if request.mode == "sumo" else bodies.food_contacts(slot)
            touch = float(bool(contact_food))
            senses[slot] = {"odor": [float(odor[0]), float(odor[1])], "visual": visual,
                            "visual_status": "raycast_engineered_observation",
                            "touch": touch, "touch_status": "mujoco_food_contact_observation_v1",
                            "contact_food": contact_food, "nearest_food": nearest,
                            "mouth_distance": mouth_distance,
                            "sensory_profile": request.sensory_profile}
            if sum(odor) > .04 and not sensory_latches[slot]["odor"]:
                events.append({"type": "odor_detected", "tick": bodies.tick, "slot": slot,
                               "values": [float(odor[0]), float(odor[1])]})
            sensory_latches[slot]["odor"] = sum(odor) > .04
            if max(visual) > .05 and not sensory_latches[slot]["visual"]:
                events.append({"type": "visual_target_detected", "tick": bodies.tick, "slot": slot,
                               "values": visual, "observation": "raycast_engineered_geometry"})
            sensory_latches[slot]["visual"] = max(visual) > .05
            if touch and not sensory_latches[slot]["touch"]:
                events.append({"type": "food_contact", "tick": bodies.tick, "slot": slot,
                               "mouth_distance": mouth_distance,
                               "food": contact_food,
                               "observation": "mujoco_food_contact"})
                food_contact_ticks[slot].append(bodies.tick)
            sensory_latches[slot]["touch"] = bool(touch)
            if v2:
                backend = backends[slot]
                encoded = encode_odor(*odor)
                backend.stimulate(float(encoded[0]), float(encoded[1]))
                backend.advance(RULES["sense_ticks"])
                command = decoder.command(backend.neural_output(decoder.neurons))
                drives[slot] = motors[slot].advance(command)
            else:
                # Bilateral sensory contrast gain uses only the fly's two local sensors.
                contrast = (odor[0] - odor[1]) / (sum(odor) + .05)
                common = (odor[0] + odor[1]) / 2
                encoded = np.clip([common + 2 * contrast, common - 2 * contrast], 0, 1)
                if sensory_encoder:
                    senses[slot]["neural_input"] = sensory_encoder.apply(
                        brain, float(encoded[0]), float(encoded[1]),
                        float(visual[0]), float(visual[1]), touch)
                else:
                    brain.stimulate(float(encoded[0]), float(encoded[1]))
                brain.advance(RULES["sense_ticks"])
                command = brain.rates[ro["neurons"]] / 100 @ ro["weights"]
                # Fixed low-pass decoder; no access to food or world coordinates.
                drives[slot] = .85 * drives[slot] + .15 * np.clip(command, 0, 1.5)
            if silence_output or eliminated[slot] or energy[slot] <= 0:
                drives[slot] = 0
        for _ in range(RULES["sense_ticks"]):
            bodies.step(drives)
            energy[:] = np.maximum(0, energy - drives.mean(axis=1) * 2 * RULES["physics_dt"])
            if request.mode != "sumo":
                mouths = np.array([bodies.mouth(i) for i in range(len(flies))])
                eligible = np.linalg.norm(mouths[:, None, :2] - food_xy[None, :, :], axis=2) <= RULES["mouth_radius_mm"]
                eligible &= (mouths[:, 2] < 2.5)[:, None] & (~eliminated)[:, None]
                counts = eligible.sum(axis=0)
                # Split a single source's intake capacity equally; conserve resources.
                amount = np.minimum(remaining, RULES["food_intake_per_second"] * RULES["physics_dt"])
                uptake = eligible * (amount / np.maximum(1, counts))[None, :]
                remaining -= uptake.sum(axis=0)
                gained = uptake.sum(axis=1)
                scores += gained
                energy[:] = np.minimum(100, energy + gained)
                consumption += uptake
            exits = []
            for slot in range(len(flies)):
                position, _ = bodies.pose(slot)
                outside = np.linalg.norm(position[:2]) > scene.get("ring_radius", 1000) if request.mode == "sumo" else np.max(np.abs(position[:2])) > scene["size"] / 2
                if outside and not eliminated[slot]:
                    exits.append(slot)
            # Same-tick boundary events are collected before any elimination is applied.
            for slot in exits:
                eliminated[slot] = True
                drives[slot] = 0
                exit_ticks[slot] = bodies.tick
                events.append({"type": "exit", "tick": bodies.tick, "slot": slot})
            touching = bodies.contact_between_flies()
            if touching:
                contact_ticks += 1
            if touching and not last_contact:
                events.append({"type": "contact", "tick": bodies.tick, "slots": [0, 1]})
            last_contact = touching
        # Intake/progress retain their historical 20 Hz clock. Pose recording
        # is independent and samples the already-stepped MuJoCo state at 100 Hz.
        if (bodies.tick % POLICY["pose_ticks"] == 0 and
                bodies.tick % RULES["snapshot_ticks"] != 0 and
                (not frames or frames[-1]["tick"] != bodies.tick)):
            snapshot()
        if bodies.tick % RULES["snapshot_ticks"] == 0:
            for slot in range(len(flies)):
                for food in range(len(remaining)):
                    if consumption[slot, food] > 0:
                        events.append({"type": "intake", "tick": bodies.tick, "slot": slot,
                                       "food": food, "amount": float(consumption[slot, food])})
                        intake_ticks[slot].append(bodies.tick)
            consumption.fill(0)
            snapshot()
            if progress:
                progress(bodies.tick / duration_ticks)
        if request.mode == "sumo" and eliminated.any():
            break
    # Flush accounting independently: the terminal pose may already be recorded.
    for slot in range(len(flies)):
        for food in range(len(remaining)):
            if consumption[slot, food] > 0:
                events.append({"type": "intake", "tick": bodies.tick, "slot": slot,
                               "food": food, "amount": float(consumption[slot, food])})
                intake_ticks[slot].append(bodies.tick)
    if frames[-1]["tick"] != bodies.tick:
        snapshot()
    for slot, brain in enumerate(brains):
        np.savez_compressed(output / f"brain-{slot}.npz", **brain.checkpoint())
    np.savez_compressed(output / "physics.npz", **bodies.checkpoint())
    write_json(output / "frames.json", frames)
    write_json(output / "events.json", events)
    write_json(output / "result.json", {"scores": scores.tolist(), "exit_ticks": exit_ticks,
               "final_tick": bodies.tick, "food_remaining": remaining.tolist(),
               "contact_ticks": contact_ticks,
               "food_contact_ticks": food_contact_ticks,
               "intake_ticks": intake_ticks})
    receipt = {"schema": REPLAY_RECEIPT, "replay_policy": dict(POLICY), "request": request.model_dump(),
               "flies": scene["flies"], "connectome_sha256": graph.manifest["sha256"],
               "neuron_count": graph.n, "edge_count": graph.e,
               "readout_sha256": readout["sha256"], "runtime": frozen_runtime,
               "silence_output": silence_output, "final_tick": bodies.tick,
               "total_spikes": [b.total_spikes for b in brains],
               "model_profiles": [PROFILES["malecns-rate-cpu-v1"] if b.total_spikes is None else PROFILE for b in brains],
               "timing": {"wall_seconds": time.perf_counter() - start,
                          "simulation_wall_seconds": time.perf_counter() - simulation_started,
                          "simulated_seconds": bodies.tick * RULES["physics_dt"]},
               "files": {name: file_sha(output / name) for name in sorted(
                   ["scene.json", "frames.json", "events.json", "result.json", "physics.npz"] +
                   [f"brain-{i}.npz" for i in range(len(brains))])}}
    receipt["sha256"] = digest(receipt)
    write_json(output / "receipt.json", receipt)
    return receipt
