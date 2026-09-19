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
    assert result["schema"] == "neural-design-preview/v2"
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
