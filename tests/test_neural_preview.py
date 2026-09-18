"""The design preview must execute the submitted FlySpec through the retained graph."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from flyarena.api import create_app
from flyarena.auth import AuthConfig
from flyarena.common import DATA
from flyarena.store import Store


def test_neural_preview_returns_model_state_for_fixed_stimuli(tmp_path):
    manifest = json.loads((DATA / "connectome/manifest.json").read_text())
    with TestClient(create_app(with_worker=False, store=Store(Path(tmp_path)), auth_config=AuthConfig())) as client:
        identity = client.post("/api/v1/identities", json={"name": "preview tester"}).json()
        body = {
            "name": "preview candidate",
            "connectome_sha256": manifest["sha256"],
            "weight_mutations": [{"selector": "olfactory", "scale": 1.1}],
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
