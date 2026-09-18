"""The design preview must execute the submitted FlySpec through the retained graph."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

import flyarena.api as api_module
from flyarena.auth import AuthConfig
from flyarena.connectome import Connectome
from flyarena.api import create_app
from flyarena.store import Store
from test_replay_parity import tiny_assets


def test_neural_preview_returns_model_state_for_fixed_stimuli(tmp_path, monkeypatch):
    data, _, _ = tiny_assets(tmp_path / "assets")
    manifest = json.loads((data / "connectome/manifest.json").read_text())
    # CI intentionally does not ship the 165k-neuron research data bundle. The
    # four-node fixture still exercises the same endpoint and Brain implementation.
    monkeypatch.setattr(api_module, "Connectome", lambda: Connectome(data))
    with TestClient(create_app(with_worker=False, store=Store(Path(tmp_path)), auth_config=AuthConfig())) as client:
        identity = client.post("/api/v1/identities", json={"name": "preview tester"}).json()
        body = {
            "name": "preview candidate",
            "connectome_sha256": manifest["sha256"],
            "weight_mutations": [{"selector": "olfactory", "scale": 1.01}],
        }
        response = client.post("/api/v1/flies/preview", json=body,
                              headers={"Authorization": "Bearer " + identity["token"]})
    assert response.status_code == 200
    result = response.json()
    assert result["schema"] == "neural-design-preview/v1"
    assert result["connectome_sha256"] == manifest["sha256"]
    assert result["model_profile"] == "malecns-lif-cpu-v1"
    assert len(result["stimuli"]) == 4
    assert result["stimuli"][0]["stimulus"] == {"left": 1.0, "right": 0.0}
    assert result["stimuli"][0]["total_spikes"] > 0
    assert result["stimuli"][-1]["stimulus"] == {"left": 0.0, "right": 0.0}
    assert result["stimuli"][-1]["total_spikes"] == 0
