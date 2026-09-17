"""Real full-retained-graph / solo MuJoCo probes with verified evidence receipts."""
from __future__ import annotations
import importlib.metadata
import json
import platform
import time
from pathlib import Path
import mujoco
import numpy as np
from ..backend import CPUBrainBackend, V2_IDS, CAPABILITIES
from ..body import Bodies
from ..common import DATA, ROOT, VAR, digest, file_sha, write_json
from ..compiler import Compiler
from ..connectome import Connectome
from ..neural import Brain, PROFILE
from .decoder import Decoder, READOUT_ID, training_identity
from .sensor import SENSOR, encode_odor
from .motor import MOTOR, MotorTransfer, identity as motor_identity
from .checkpoints import verify_probe_checkpoints

PROFILE_ID = "sensorimotor-research-v2"
DT = .01
LIMITATIONS = ["Engineered current-based LIF sensorimotor approximation, not biological behavior validation.",
              "Two bilateral locomotion action channels; no added physical degrees of freedom.",
              "Chemical concentration only; vision, airflow, contact feedback, learning and memory qualification unavailable.",
              "Analytic local chemical fixture penetrates walls; not odor diffusion or line-of-sight transport.",
              "Game energy is an accounting proxy, not metabolism; persistent motion is not evidence of memory."]

def probe_catalog() -> list[dict]:
    return [{"id": pid, "name": name, "description": desc, "capabilities": ["bilateral_chemical", "solo_mujoco", "full_retained_graph", "measured_contacts"],
             "scenario": {"geometry_id": geometry, "stimulus_id": stimulus, "task_id": task},
             "limitations": LIMITATIONS}
            for pid, name, desc, geometry, stimulus, task in [
                ("gradient-v2", "Off-axis chemical gradient", "A Gaussian chemical source starts to one side of the fly's heading; seed pairs mirror the source.", "open-plane-v2", "gaussian-local-v2", "approach-food-v2"),
                ("bifurcation-v2", "Traversable chemical bifurcation", "Wide passages around a central barrier; a food-centered Gaussian chemical source biases one branch.", "wide-fork-v2", "gaussian-branch-source-v3", "branch-choice-v2"),
                ("delayed-cue-v2", "Delayed and disappearing cue", "Cue is absent until 0.25 s, present until 1.0 s, then exactly absent; post-cue activity is measured without claiming memory.", "open-plane-v2", "timed-gaussian-v2", "cue-offset-response-v2")]]

def profile_manifest(data: Path = DATA) -> dict:
    result = {"id": PROFILE_ID, **V2_IDS, "motor_id": MOTOR["id"], "protocol_id": "probe-protocol-v3", "actual_backend": "cpu-numba", "ready": False, "hashes": {},
              "capabilities": sorted(CAPABILITIES | {"bilateral_chemical", "two_bilateral_actions", "solo_mujoco"}),
              "limitations": LIMITATIONS, "unavailable": ["cuda", "biological_validation", "memory_qualification"]}
    try:
        folder = data / "connectome/research-v2"
        meta = json.loads((folder / "readout.json").read_text())
        graph = json.loads((data / "connectome/manifest.json").read_text())
        if digest({k:v for k,v in meta.items() if k != "sha256"}) != meta["sha256"]:
            raise ValueError("readout metadata digest mismatch")
        if digest({k:v for k,v in graph.items() if k != "sha256"}) != graph["sha256"]:
            raise ValueError("connectome manifest digest mismatch")
        if meta["id"] != READOUT_ID or meta["training_identity"] != training_identity():
            raise ValueError("unknown or incompatible scientific readout version")
        if meta["connectome_sha256"] != graph["sha256"] or meta["readout_sha256"] != file_sha(folder / "readout.npz"):
            raise ValueError("readout hash or graph identity mismatch")
        result["hashes"] = {"connectome": graph["sha256"], "readout": meta["readout_sha256"], "readout_metadata": meta["sha256"],
                            "sensor": digest(SENSOR), "model": digest(PROFILE),
                            "motor": digest(motor_identity()), "runtime_closure": digest(runtime_closure())}
        result["quality_gates"] = meta["quality_gates"]
        result["ready"] = meta["ready"] and bool(meta["quality_gates"]) and all(meta["quality_gates"].values())
        if not result["ready"]: result["reason"] = "readout quality gates failed"
    except (OSError, ValueError, KeyError) as exc:
        result["reason"] = str(exc)
    return result

def make_scene(probe_id: str, seed: int) -> dict:
    if probe_id not in {p["id"] for p in probe_catalog()}:
        raise ValueError(f"unknown scientific probe: {probe_id}")
    if type(seed) is not int or not 0 <= seed <= 2**31-1: raise ValueError("seed must be nonnegative int32")
    rng = np.random.default_rng(seed // 2)
    mirror = 1 if seed % 2 == 0 else -1
    food = [7.+float(rng.uniform(-.2,.2)), mirror*(5.+float(rng.uniform(-.2,.2))), .15]
    scene = {"id": probe_id, "size": 80, "spawns": [[0.,0.,0.]], "obstacles": [],
             "food": [{"id": "food-0", "position": food, "initial": 10.}], "mirror": mirror,
             "chemical_policy": "analytic local fixture; penetrates walls; no diffusion simulation",
             "odor_sigma_xy_mm": [9.,6.] if probe_id == "bifurcation-v2" else [6.,6.],
             "cue_on_seconds": .25 if probe_id == "delayed-cue-v2" else 0.,
             "cue_off_seconds": 1. if probe_id == "delayed-cue-v2" else None}
    if probe_id == "bifurcation-v2":
        scene["obstacles"] = [{"position": [10.,0.,1.5], "size": [1.,5.,3.]},
                              {"position": [8.,16.,1.5], "size": [30.,1.,3.]},
                              {"position": [8.,-16.,1.5], "size": [30.,1.,3.]}]
        scene["food"][0]["position"] = [14., mirror*8., .15]
    return scene

def sample_odor(scene: dict, antennae, seconds: float, remaining: float, stimulus: str = "normal") -> np.ndarray:
    if stimulus == "blank" or seconds < scene["cue_on_seconds"] or (scene["cue_off_seconds"] is not None and seconds >= scene["cue_off_seconds"]):
        return np.zeros(2)
    sources = np.array([f["position"][:2] for f in scene["food"]])
    return np.array([np.exp(-.5*np.sum(((sources-a[:2])/np.array(scene.get("odor_sigma_xy_mm",[6.,6.])))**2,axis=1)).sum() for a in antennae])*remaining/10.

def runtime_closure() -> dict:
    sources = [str(p.relative_to(ROOT / "src/flyarena")) for p in sorted((ROOT / "src/flyarena").rglob("*.py"))]
    dependencies = {}
    for name in ("flygym", "mujoco", "numpy", "numba", "scipy"):
        dist = importlib.metadata.distribution(name)
        # Freeze body/controller code AND packaged mesh/configuration assets.
        files = {}
        if name == "flygym":
            for f in sorted(dist.files or [], key=str):
                path = Path(dist.locate_file(f))
                if path.is_file() and path.suffix not in {".pyc"} and "__pycache__" not in str(path):
                    files[str(f)] = file_sha(path)
        dependencies[name] = {"version": dist.version, "files_sha256": digest(files), "file_count": len(files)}
    return {"sources": {f:file_sha(ROOT/"src/flyarena"/f) for f in sources},
            "dependencies": dependencies, "lock_sha256": file_sha(ROOT/"uv.lock"),
            "python": platform.python_version(), "platform": platform.platform(),
            "physics_dt": .0001, "sense_dt": DT, "neural_dt_ms": .1,
            "intake_policy": "mouth distance <=1.1mm and height<2.5mm at each 10ms boundary, 8 units/s",
            "drive_filter": MOTOR, "energy": "100 initial, 2*mean(drive) units/s; intake replenishes"}

def measured_metrics(trajectory, trace, scene):
    positions = np.array([[r["x"],r["y"]] for r in trajectory]); times=np.array([r["time"] for r in trajectory])
    yaw = np.unwrap([r["yaw"] for r in trajectory]); horizon=times[-1]
    path=float(np.linalg.norm(np.diff(positions,axis=0),axis=1).sum())
    goal=np.array(scene["food"][0]["position"][:2]); drive=np.array([[r["drive_left"],r["drive_right"]] for r in trace])
    latency=next((r["time"] for r in trace if r["food_intake"] > 0), None)
    choice=0
    if scene["id"] == "bifurcation-v2":
        for row in trajectory:
            if row["x"] >= 9.5 and abs(row["y"]) >= 3.5:
                choice=1 if row["y"] > 0 else -1; break
    post=[r for r in trace if scene["cue_off_seconds"] is not None and r["time"] >= scene["cue_off_seconds"]+.3]
    return {"path_length_mm":path, "displacement_mm":float(np.linalg.norm(positions[-1]-positions[0])),
            "mean_speed_mm_s":path/horizon, "yaw_delta_rad":float(yaw[-1]-yaw[0]),
            "absolute_turn_rad":float(abs(np.diff(yaw)).sum()), "food_latency_seconds":latency,
            "food_intake":trace[-1]["food_intake"], "final_distance_to_food_mm":float(np.linalg.norm(positions[-1]-goal)),
            "progress_to_food_mm":float(np.linalg.norm(positions[0]-goal)-np.linalg.norm(positions[-1]-goal)),
            "wall_contact_seconds":float(sum(r["wall_contact_ticks"] for r in trace)*.0001),
            "opponent_contact_seconds":0., "game_energy_final":trace[-1]["game_energy"],
            "mean_drive":float(drive[1:].mean()), "branch_choice":choice,
            "correct_branch":float(choice == scene["mirror"]) if choice else None,
            "post_cue_mean_drive":float(np.mean([.5*(r["drive_left"]+r["drive_right"]) for r in post])) if post else None}

def verify_evidence(output: Path, report: dict | None = None) -> dict:
    receipt=json.loads((output/"receipt.json").read_text())
    if digest({k:v for k,v in receipt.items() if k != "sha256"}) != receipt["sha256"]:
        raise ValueError("receipt digest mismatch")
    if set(receipt["files"]) != {"scene.json", "evidence.json", "events.json", "brain.npz", "physics.npz"}:
        raise ValueError("incomplete receipt evidence set")
    for name, sha in receipt["files"].items():
        if Path(name).name != name or not (output/name).is_file() or file_sha(output/name) != sha:
            raise ValueError(f"evidence file mismatch: {name}")
    evidence=json.loads((output/"evidence.json").read_text()); scene=json.loads((output/"scene.json").read_text())
    if digest(receipt["conditions"]) != evidence["condition_key"]:
        raise ValueError("condition key mismatch")
    if receipt["conditions"]["scene"] != scene or receipt["subject"]["artifact_id"] != evidence["artifact_id"]:
        raise ValueError("scene or subject mismatch")
    expected=np.arange(round(evidence["duration_seconds"]/DT)+1)*DT
    for rows in (evidence["trajectory"], evidence["neural_trace"]):
        if len(rows)!=len(expected) or not np.allclose([r["time"] for r in rows], expected, atol=1e-10, rtol=0):
            raise ValueError("incomplete evidence time grid")
    if digest(receipt["subject"]["phenotype"]) != evidence["artifact_id"]:
        raise ValueError("subject phenotype digest mismatch")
    verify_probe_checkpoints(output, receipt, evidence["neural_trace"][-1])
    if measured_metrics(evidence["trajectory"], evidence["neural_trace"], scene) != evidence["metrics"]:
        raise ValueError("reported metrics disagree with emitted evidence")
    conditions = receipt["conditions"]
    if any(evidence[k] != conditions[k] for k in ("seed", "duration_seconds", "probe_id", "profile")):
        raise ValueError("evidence differs from frozen scientific conditions")
    if receipt["subject"]["fly_id"] != evidence["fly_id"]:
        raise ValueError("subject fly identity mismatch")
    if conditions["profile"].get("protocol_id") == "probe-protocol-v3":
        if "scene" not in evidence:
            raise ValueError("versioned report requires receipted scene")
        if conditions["profile"]["hashes"]["runtime_closure"] != digest(conditions["runtime"]):
            raise ValueError("profile scientific source closure mismatch")
    if "scene" in evidence and evidence["scene"] != scene:
        raise ValueError("report scene disagrees with receipt")
    if report is not None:
        if any(report.get(k)!=v for k,v in evidence.items()) or report.get("receipt_sha256") != receipt["sha256"]:
            raise ValueError("report disagrees with emitted evidence")
    return evidence

def run_probe(fly: dict, probe_id: str, seed: int, duration_seconds: int, output: Path, *, data=DATA, var=VAR,
              ablation: str | None = None, stimulus: str = "normal", decoder_version: str = "v2") -> dict:
    if type(duration_seconds) is not int or not 1 <= duration_seconds <= 30:
        raise ValueError("duration must be integer seconds in [1,30]")
    if ablation not in (None,"output"): raise ValueError("unknown ablation")
    if stimulus not in ("normal","blank"): raise ValueError("unknown stimulus")
    if decoder_version not in ("v1","v2"): raise ValueError("unknown decoder")
    profile=profile_manifest(data)
    if not profile["ready"]: raise RuntimeError(f"research profile unavailable: {profile.get('reason')}")
    scene=make_scene(probe_id, seed)
    output=Path(output); output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()): raise FileExistsError("probe evidence directory must be empty; immutable run")
    started=time.perf_counter(); graph=Connectome(data, verify=True)
    weights, artifact=Compiler(graph).load_weights(fly["artifact_id"],var)
    params=artifact["phenotype"]["neuron_parameters"]
    backend=CPUBrainBackend(Brain(graph,weights,params["tau_scale"],params["threshold_shift_mv"]))
    backend.prepare(V2_IDS | {"capabilities": sorted(CAPABILITIES)})
    backend.reset(seed)
    decoder=Decoder(data/"connectome/research-v2/readout.npz")
    legacy=None
    if decoder_version == "v1":
        legacy=dict(np.load(data/"connectome/readout.npz",allow_pickle=False))
        profile=profile | {"id":"legacy-bridge-diagnostic-v1", "sensor_id":"legacy-bilateral-odor-v1", "readout_id":"descending-ridge-v1"}
        profile["hashes"] = profile["hashes"] | {"legacy_readout":file_sha(data/"connectome/readout.npz")}
    motor=MotorTransfer()
    body=Bodies(scene,1,seed)
    wall_ids={i for i in range(body.model.ngeom) if (mujoco.mj_id2name(body.model,mujoco.mjtObj.mjOBJ_GEOM,i) or "").startswith("obstacle-")}
    conditions={"profile":profile,"runtime":runtime_closure(),"scene":scene,"seed":seed,"duration_seconds":duration_seconds,
                "probe_id":probe_id,"ablation":ablation,"stimulus":stimulus,"decoder_version":decoder_version}
    key=digest(conditions); trajectory=[]; trace=[]; events=[]; drives=np.zeros(2); energy=100.; intake=0.; remaining=10.
    def record(raw, encoded, command, contacts):
        position,rot=body.pose(0); t=round(body.tick*.0001,8)
        trajectory.append({"time":t,"x":float(position[0]),"y":float(position[1]),"yaw":float(np.arctan2(rot[1,0],rot[0,0]))})
        trace.append({"time":t,"z":float(position[2]),"upright_z":float(rot[2,2]),**backend.metrics(),"raw_odor_left":float(raw[0]),"raw_odor_right":float(raw[1]),
                      "encoded_odor_left":float(encoded[0]),"encoded_odor_right":float(encoded[1]),
                      "command_left":float(command[0]),"command_right":float(command[1]),
                      "drive_left":float(drives[0]),"drive_right":float(drives[1]),"game_energy":float(energy),
                      "food_intake":float(intake),"wall_contact_ticks":contacts})
    record(np.zeros(2),np.zeros(2),np.zeros(2),0)
    for block in range(round(duration_seconds/DT)):
        raw=sample_odor(scene,body.antennae(0),block*DT,remaining,stimulus)
        encoded=encode_odor(*raw)
        if legacy is None:
            backend.stimulate(*encoded)
        else:
            clipped=np.clip(raw,0,1); contrast=(clipped[0]-clipped[1])/(sum(clipped)+.05)
            encoded=np.clip([np.mean(clipped)+2*contrast,np.mean(clipped)-2*contrast],0,1)
            backend.brain.stimulate(*encoded)
        backend.advance(100)
        command=decoder.command(backend.neural_output(decoder.neurons)) if legacy is None else np.clip(backend.neural_output(legacy["neurons"])/100@legacy["weights"],0,1.5)
        drives=motor.advance(command) if legacy is None else (.85*drives+.15*command)
        if ablation == "output" or energy <= 0: drives[:]=0
        contacts=0
        for _ in range(100):
            body.step(drives[None,:])
            pairs=set()
            if wall_ids:
                for c in body.data.contact:
                    a,b=int(c.geom1),int(c.geom2)
                    if c.dist<=0 and ((a in wall_ids and b in body.geom_slots) or (b in wall_ids and a in body.geom_slots)):
                        pairs.add((min(a,b),max(a,b)))
            if pairs:
                contacts+=1
                events.append({"tick":body.tick,"type":"wall_contact","geom_pairs":[list(p) for p in sorted(pairs)]})
        energy=max(0.,energy-float(drives.mean())*2*DT)
        mouth=body.mouth(0); goal=np.array(scene["food"][0]["position"])
        if np.linalg.norm(mouth[:2]-goal[:2])<=1.1 and mouth[2]<2.5:
            gained=min(remaining,8*DT); remaining-=gained; intake+=gained; energy=min(100.,energy+gained)
        record(raw,encoded,command,contacts)
    metrics=measured_metrics(trajectory,trace,scene)
    evidence={"schema_version":"probe-report/v2","fly_id":fly["id"],"artifact_id":fly["artifact_id"],"condition_key":key,
              "probe_id":probe_id,"seed":seed,"duration_seconds":duration_seconds,"trajectory":trajectory,
              "metrics":metrics,"neural_trace":trace,"profile":profile,"scene":scene}
    write_json(output/"scene.json",scene);write_json(output/"evidence.json",evidence);write_json(output/"events.json",events)
    np.savez_compressed(output/"brain.npz",**backend.checkpoint());np.savez_compressed(output/"physics.npz",**body.checkpoint())
    receipt={"schema_version":"probe-receipt/v2","conditions":conditions,"subject":{"fly_id":fly["id"],"artifact_id":fly["artifact_id"],"weights_sha256":artifact["phenotype"]["weights_sha256"],"phenotype":artifact["phenotype"]},
             "neuron_count":graph.n,"edge_count":graph.e,"final_tick":body.tick,"total_spikes":backend.brain.total_spikes,
             "wall_seconds":time.perf_counter()-started,"files":{n:file_sha(output/n) for n in ["scene.json","evidence.json","events.json","brain.npz","physics.npz"]}}
    receipt["sha256"]=digest(receipt);write_json(output/"receipt.json",receipt)
    report=evidence | {"receipt_sha256":receipt["sha256"]}
    verify_evidence(output,report)
    report["status"]="complete";write_json(output/"report.json",report)
    return report
