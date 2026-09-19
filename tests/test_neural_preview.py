"""The design preview must execute the submitted FlySpec through the retained graph."""
import json
import pytest
from pathlib import Path

from fastapi.testclient import TestClient

import flyarena.api as api_module
from flyarena.auth import AuthConfig
from flyarena.connectome import Connectome
from flyarena.api import create_app
from flyarena.store import Store
from test_replay_parity import tiny_assets


@pytest.mark.parametrize("model", ["malecns-lif-cpu-v1", "malecns-rate-cpu-v1"])
def test_neural_preview_returns_model_state_for_fixed_stimuli(tmp_path, monkeypatch, model):
    data, _, _ = tiny_assets(tmp_path / "assets")
    manifest = json.loads((data / "connectome/manifest.json").read_text())
    # CI intentionally does not ship the 165k-neuron research data bundle. The
    # four-node fixture still exercises the same endpoint and Brain implementation.
    monkeypatch.setattr(api_module, "Connectome", lambda: Connectome(data))
    with TestClient(create_app(with_worker=False, store=Store(Path(tmp_path)), auth_config=AuthConfig())) as client:
        identity = client.post("/api/v1/identities", json={"name": "preview tester"}).json()
        body = {
            "name": "preview candidate",
            "model_profile": model,
            "neuron_parameters": {"tau_scale": 1.1, "threshold_shift_mv": .2},
            "connectome_sha256": manifest["sha256"],
            "weight_mutations": [{"selector": "olfactory", "scale": 1.01}],
        }
        response = client.post("/api/v1/flies/preview", json=body,
                              headers={"Authorization": "Bearer " + identity["token"]})
    assert response.status_code == 200
    result = response.json()
    assert result["schema"] == "neural-design-preview/v3"
    assert result["motor_readout"]["available"] is True
    assert result["connectome_sha256"] == manifest["sha256"]
    assert result["model_profile"] == model
    assert len(result["stimuli"]) == 4
    assert result["stimuli"][0]["stimulus"] == {"left": 1.0, "right": 0.0}
    assert result["stimuli"][-1]["stimulus"] == {"left": 0.0, "right": 0.0}
    assert result["reference"]["spec"]["weight_mutations"] == []
    assert result["reference"]["spec"]["neuron_parameters"] == {"tau_scale": 1., "threshold_shift_mv": 0.}
    assert result["reference"]["spec"]["model_profile"] == model
    for row in result["stimuli"]:
        samples = row["samples"]
        assert [sample["time_ms"] for sample in samples] == list(range(0, 121, 10))
        assert all(v == 0 for v in samples[0]["circuits"].values())
        assert all(v == 0 for v in samples[0]["reference_circuits"].values())
        assert samples[2]["stimulus"] == {"left": 0., "right": 0.}
        assert samples[3]["stimulus"] == row["stimulus"]
        assert samples[8]["stimulus"] == row["stimulus"]
        assert samples[9]["stimulus"] == {"left": 0., "right": 0.}
        if model == "malecns-rate-cpu-v1":
            assert all(sample["total_spikes"] is None and sample["reference_total_spikes"] is None for sample in samples)
        else:
            assert samples[0]["total_spikes"] == samples[0]["reference_total_spikes"] == 0
            assert samples[-1]["total_spikes"] > 0
    # All four trials must start from the same resting state and baseline.
    assert all(row["samples"][:3] == result["stimuli"][0]["samples"][:3] for row in result["stimuli"])


def test_canonical_design_matches_wt_at_every_sample(tmp_path):
    from flyarena.compiler import Compiler
    from flyarena.contracts import FlySpec
    from flyarena.neural_preview import preview_design
    data, _, _ = tiny_assets(tmp_path / "assets")
    graph = Connectome(data)
    result = preview_design(Compiler(graph), FlySpec(name="canonical", connectome_sha256=graph.manifest["sha256"]))
    assert result["artifact_id"] == result["reference"]["artifact_id"]
    for row in result["stimuli"]:
        for sample in row["samples"]:
            assert sample["circuits"] == sample["reference_circuits"]
            assert sample["total_spikes"] == sample["reference_total_spikes"]
            assert sample["motor"] == sample["reference_motor"]


def test_motor_preview_reads_neurons_and_resets_each_trial(tmp_path):
    import numpy as np
    from flyarena.common import file_sha
    from flyarena.compiler import Compiler
    from flyarena.contracts import FlySpec
    from flyarena.models import make_brain
    from flyarena.neural_preview import preview_design
    data, _, _ = tiny_assets(tmp_path / "assets")
    folder = data / "connectome"
    # Asymmetric signed readout makes raw, clipped and filtered stages distinct.
    neurons = np.array([0, 3])
    weights = np.array([[2., -1.], [.1, .2]])
    np.savez(folder / "readout.npz", neurons=neurons, weights=weights)
    metadata = json.loads((folder / "readout.json").read_text())
    metadata["readout_sha256"] = file_sha(folder / "readout.npz")
    (folder / "readout.json").write_text(json.dumps(metadata))
    graph = Connectome(data)
    spec = FlySpec(name="canonical", connectome_sha256=graph.manifest["sha256"])
    result = preview_design(Compiler(graph), spec)
    brain = make_brain(spec.model_profile, graph, graph.baseline_weights(), spec.neuron_parameters.model_dump())
    for trial in result["stimuli"]:
        brain.reset()
        drive = np.zeros(2)
        for sample in trial["samples"]:
            brain.stimulate(sample["stimulus"]["left"], sample["stimulus"]["right"])
            if sample["time_ms"]:
                brain.advance(100)
            # Independently calculate the runner's projection and recurrence.
            raw = np.array([sum(brain.rates[n] * weights[i, channel] / 100
                                for i, n in enumerate(neurons)) for channel in (0, 1)])
            clipped = np.minimum(1.5, np.maximum(0, raw))
            if sample["time_ms"]:
                drive = .85 * drive + .15 * clipped
            np.testing.assert_allclose(sample["motor"]["raw"], raw)
            np.testing.assert_allclose(sample["motor"]["clipped"], clipped)
            np.testing.assert_allclose(sample["motor"]["drive"], drive)
    assert any(s["motor"]["raw"][1] < 0 for s in result["stimuli"][0]["samples"])


@pytest.mark.parametrize("failure", ["missing", "wrong_connectome", "changed_weights"])
def test_motor_unavailable_preserves_neural_observations(tmp_path, failure):
    from flyarena.compiler import Compiler
    from flyarena.contracts import FlySpec
    from flyarena.neural_preview import preview_design
    data, _, _ = tiny_assets(tmp_path / "assets")
    folder = data / "connectome"
    if failure == "missing":
        (folder / "readout.npz").unlink()
    elif failure == "changed_weights":
        (folder / "readout.npz").write_bytes(b"invalid")
    else:
        metadata = json.loads((folder / "readout.json").read_text())
        metadata["connectome_sha256"] = "other graph"
        (folder / "readout.json").write_text(json.dumps(metadata))
    graph = Connectome(data)
    result = preview_design(Compiler(graph), FlySpec(name="canonical", connectome_sha256=graph.manifest["sha256"]))
    assert result["motor_readout"]["available"] is False
    for trial in result["stimuli"]:
        assert any(s["total_spikes"] > 0 for s in trial["samples"])
        assert all(s["motor"] is None and s["reference_motor"] is None for s in trial["samples"])
