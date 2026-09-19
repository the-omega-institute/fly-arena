"""Fixed, paired neural stimulus observations; no body or fitness estimate."""
from pathlib import Path
import json
import tempfile
import numpy as np

from .common import digest, file_sha
from .contracts import FlySpec
from .models import make_brain, profile
from .neural import PROFILE


# advance() uses the common 0.1 ms clock for both supported models.
SAMPLE_MS = 10
DURATION_MS = 120
ONSET_MS = 20
OFFSET_MS = 80


def motor_readout(graph):
    """Use the arena's frozen legacy readout, never fit it to the preview."""
    try:
        metadata = json.loads((graph.path / "readout.json").read_text())
        path = graph.path / "readout.npz"
        if (metadata["connectome_sha256"] != graph.manifest["sha256"] or
                metadata["neural_profile_sha256"] != digest(PROFILE) or
                metadata["readout_sha256"] != file_sha(path)):
            raise ValueError("Incompatible readout")
        with np.load(path, allow_pickle=False) as archive:
            neurons, weights = archive["neurons"].copy(), archive["weights"].copy()
        if (neurons.ndim != 1 or not len(neurons) or neurons.dtype.kind not in "iu" or
                np.any(neurons < 0) or np.any(neurons >= graph.n) or
                weights.shape != (len(neurons), 2) or not np.isfinite(weights).all()):
            raise ValueError("Invalid readout arrays")
    except FileNotFoundError:
        return None, {"available": False, "reason": "missing_readout"}
    except (ValueError, KeyError, OSError):
        return None, {"available": False, "reason": "incompatible_readout"}
    return (neurons, weights), {
        "available": True, "id": metadata.get("id", "descending-ridge-v1"),
        "bridge_profile": "legacy-v1", "readout_sha256": metadata["readout_sha256"],
        "calibration_model": PROFILE["id"], "neuron_count": len(neurons),
        "channels": ["left", "right"], "units": "dimensionless motor drive",
        "rate_scale_hz": 100, "clip": [0, 1.5], "previous_fraction": .85,
        "update_interval_ms": SAMPLE_MS,
        "scope": "Shared frozen arena decoder, calibrated on LIF; transfer to other models is unvalidated. "
                 "No body, world coordinates, reward or stimulus input enters the readout.",
    }


def preview_design(compiler, spec: FlySpec):
    graph = compiler.graph
    readout, motor = motor_readout(graph)
    reference = FlySpec(name="WT model reference", connectome_sha256=spec.connectome_sha256,
                        model_profile=spec.model_profile)
    with tempfile.TemporaryDirectory(prefix="arena-neural-preview-") as folder:
        root = Path(folder)
        reports = [compiler.compile(subject, publish=True, root=root) for subject in (spec, reference)]
        brains = [make_brain(subject.model_profile, graph,
                             compiler.load_weights(report["artifact_id"], root)[0],
                             subject.neuron_parameters.model_dump())
                  for subject, report in zip((spec, reference), reports)]
        rows = []
        for left, right in ((1., 0.), (0., 1.), (1., 1.), (0., 0.)):
            drives = np.zeros((2, 2))
            for brain in brains:
                brain.reset()
            samples = []
            for time_ms in range(0, DURATION_MS + SAMPLE_MS, SAMPLE_MS):
                # Inputs label the interval ending at this sample. At t=20 ms,
                # the baseline interval has just ended; the pulse begins next.
                active = ONSET_MS < time_ms <= OFFSET_MS
                inputs = {"left": left if active else 0., "right": right if active else 0.}
                outputs = []
                for slot, brain in enumerate(brains):
                    brain.stimulate(inputs["left"], inputs["right"])
                    if time_ms:
                        brain.advance(SAMPLE_MS * 10)
                    output = None
                    if readout is not None:
                        neurons, weights = readout
                        raw = brain.rates[neurons] / 100 @ weights
                        clipped = np.clip(raw, 0, 1.5)
                        # Same 10 ms legacy-v1 update as runner.simulate. t=0
                        # observes the reset state without taking a motor step.
                        if time_ms:
                            drives[slot] = .85 * drives[slot] + .15 * clipped
                        output = {"raw": raw.tolist(), "clipped": clipped.tolist(),
                                  "drive": drives[slot].tolist()}
                    outputs.append(output)
                samples.append({"time_ms": time_ms, "stimulus": inputs,
                                "motor": outputs[0], "reference_motor": outputs[1],
                                "circuits": brains[0].trace(), "reference_circuits": brains[1].trace(),
                                "total_spikes": spike_count(brains[0]),
                                "reference_total_spikes": spike_count(brains[1])})
            rows.append({"stimulus": {"left": left, "right": right},
                         "circuits": samples[-1]["circuits"],
                         "total_spikes": samples[-1]["total_spikes"], "samples": samples})
        return {"schema": "neural-design-preview/v3", "artifact_id": reports[0]["artifact_id"],
                "motor_readout": motor,
                "spec": spec.model_dump(), "report": reports[0],
                "reference": {"artifact_id": reports[1]["artifact_id"], "spec": reference.model_dump()},
                "model_profile": spec.model_profile, "model": profile(spec.model_profile),
                "connectome_sha256": graph.manifest["sha256"],
                "steps": DURATION_MS * 10, "clock_step_ms": .1,
                "protocol": {"duration_ms": DURATION_MS, "sample_interval_ms": SAMPLE_MS,
                             "onset_ms": ONSET_MS, "offset_ms": OFFSET_MS,
                             "encoder": "bilateral ORN current: 8 + 40 * concentration mV",
                             "reset": "Both models reset independently before each stimulus",
                             "input_alignment": "Each sample labels the input over the preceding interval"},
                "stimuli": rows,
                "scope": "Actual full retained-connectome dynamics; matched WT model and pulse protocol. "
                         "Engineered odor currents, including 8 mV tonic input at zero concentration; "
                         "optional frozen legacy arena motor commands from actual neuron rates; "
                         "no body, match score or biological equivalence claim."}


def spike_count(brain):
    return None if brain.total_spikes is None else int(brain.total_spikes)
