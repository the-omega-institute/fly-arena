"""Fixed, paired neural stimulus observations; no body or fitness estimate."""
from pathlib import Path
import tempfile

from .contracts import FlySpec
from .models import make_brain, profile


# advance() uses the common 0.1 ms clock for both supported models.
SAMPLE_MS = 10
DURATION_MS = 120
ONSET_MS = 20
OFFSET_MS = 80


def preview_design(compiler, spec: FlySpec):
    graph = compiler.graph
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
            for brain in brains:
                brain.reset()
            samples = []
            for time_ms in range(0, DURATION_MS + SAMPLE_MS, SAMPLE_MS):
                # Inputs label the interval ending at this sample. At t=20 ms,
                # the baseline interval has just ended; the pulse begins next.
                active = ONSET_MS < time_ms <= OFFSET_MS
                inputs = {"left": left if active else 0., "right": right if active else 0.}
                for brain in brains:
                    brain.stimulate(inputs["left"], inputs["right"])
                    if time_ms:
                        brain.advance(SAMPLE_MS * 10)
                samples.append({"time_ms": time_ms, "stimulus": inputs,
                                "circuits": brains[0].trace(), "reference_circuits": brains[1].trace(),
                                "total_spikes": spike_count(brains[0]),
                                "reference_total_spikes": spike_count(brains[1])})
            rows.append({"stimulus": {"left": left, "right": right},
                         "circuits": samples[-1]["circuits"],
                         "total_spikes": samples[-1]["total_spikes"], "samples": samples})
        return {"schema": "neural-design-preview/v2", "artifact_id": reports[0]["artifact_id"],
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
                         "no body, trained motor readout, match score or biological equivalence claim."}


def spike_count(brain):
    return None if brain.total_spikes is None else int(brain.total_spikes)
