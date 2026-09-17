"""Complete probe checkpoint contracts, selected by recorded scientific versions.

These layouts describe the existing emitters, including historical receipts. Never
infer a layout from the submitted arrays or from today's installed body model.
A changed model/body/dependency layout needs a new explicit dispatch entry.
"""
from pathlib import Path

import numpy as np


def require_checkpoint_versions(profile: dict, runtime: dict) -> None:
    dependencies = runtime.get("dependencies", {})
    version = (profile.get("model_id"), profile.get("embodiment_id"),
               dependencies.get("flygym", {}).get("version"),
               dependencies.get("mujoco", {}).get("version"))
    if version != ("malecns-lif-cpu-v1", "neurofly-mujoco-v1", "2.1.0", "3.9.0"):
        raise ValueError("Unsupported checkpoint model/body/dependency version")


def _arrays(path: Path, fields: dict) -> dict:
    with np.load(path, allow_pickle=False) as archive:
        if len(archive.files) != len(fields) or set(archive.files) != set(fields):
            raise ValueError(f"Invalid {path.name} checkpoint fields")
        state = {}
        for name, (shape, dtype) in fields.items():
            try:
                value = archive[name]
            except ValueError as error:
                raise ValueError(f"Invalid {path.name} checkpoint array: {name}") from error
            if value.shape != shape or value.dtype != np.dtype(dtype):
                raise ValueError(f"Invalid {path.name} checkpoint shape/dtype: {name}")
            if not np.isfinite(value).all():
                raise ValueError(f"Nonfinite {path.name} checkpoint: {name}")
            state[name] = value
    return state


def verify_probe_checkpoints(output: Path, receipt: dict, final_trace: dict) -> None:
    conditions = receipt["conditions"]
    if receipt.get("schema_version") != "probe-receipt/v2":
        raise ValueError("Unsupported checkpoint receipt version")
    require_checkpoint_versions(conditions["profile"], conditions["runtime"])
    for name in ("neuron_count", "final_tick", "total_spikes"):
        if type(receipt[name]) is not int or receipt[name] < (1 if name == "neuron_count" else 0):
            raise ValueError(f"Invalid checkpoint receipt integer: {name}")
    seconds = conditions["duration_seconds"]
    if type(seconds) is not int or not 1 <= seconds <= 30:
        raise ValueError("Invalid checkpoint duration integer")
    n = receipt["neuron_count"]
    brain_fields = {name: ((n,), "float64") for name in ("v", "current", "external", "rates")}
    brain_fields.update(refractory=((n,), "int32"), delay=((19, n), "float64"),
                        tick=((), "int64"), total_spikes=((), "int64"))
    # Solo neurofly-mujoco-v1, FlyGym 2.1.0 / MuJoCo 3.9.0:
    # mjSTATE_INTEGRATION = time plus 751 per-body state values. Static probe
    # obstacles add no state. Each hybrid controller has six legs/CPG channels.
    physics_fields = {"integration": ((752,), "float64"), "tick": ((), "int64"),
                      "drives": ((1, 2), "float64")}
    physics_fields.update({f"0_{name}": ((6,), "float64") for name in
                           ("retraction_correction", "stumbling_correction", "phases", "magnitudes")})
    physics_fields["0_retraction_persistence_counter"] = ((6,), "int64")
    brain = _arrays(output / "brain.npz", brain_fields)
    physics = _arrays(output / "physics.npz", physics_fields)
    ticks = seconds * 10000
    if brain["tick"].item() != ticks or physics["tick"].item() != ticks or receipt["final_tick"] != ticks:
        raise ValueError("checkpoint horizon mismatch")
    if (brain["total_spikes"].item() != receipt["total_spikes"]
            or type(final_trace["total_spikes"]) not in (int, float)
            or final_trace["total_spikes"] != receipt["total_spikes"]):
        raise ValueError("neural checkpoint trace mismatch")
    if (np.any(brain["refractory"] < 0) or np.any(brain["refractory"] > 22)
            or np.any(brain["rates"] < 0)):
        raise ValueError("Invalid neural checkpoint state bounds")
    if not np.isclose(physics["integration"][0], seconds, rtol=0, atol=1e-8):
        raise ValueError("physical checkpoint integration clock mismatch")
    if (np.any(physics["drives"] < 0) or np.any(physics["drives"] > 1.5)
            or np.any(physics["0_retraction_persistence_counter"] < 0)):
        raise ValueError("Invalid physical checkpoint state bounds")
    drives = [final_trace["drive_left"], final_trace["drive_right"]]
    if any(type(v) not in (int, float) for v in drives) or not np.array_equal(physics["drives"][0], drives):
        raise ValueError("physical checkpoint drive trace mismatch")
